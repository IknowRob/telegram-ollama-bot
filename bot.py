#!/usr/bin/env python
"""
Telegram Bot — Second (Memory Pipeline)

Routes messages through LOR + Watcher for RAG context, responds via qwen3:14b.
Stores conversation exchanges in Watcher for persistent memory.

Author: Robert (HF Builders)
Location: E:\telegram-ollama-bot\bot.py
"""

import asyncio
import logging
import os

from dotenv import load_dotenv
import httpx
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# =============================================================================
# CONFIGURATION
# =============================================================================

load_dotenv()

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
AUTHORIZED_USER_ID = int(os.getenv("AUTHORIZED_USER_ID", "1991846232"))

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
WATCHER_URL = os.getenv("WATCHER_URL", "http://localhost:9100")
LOR_URL = os.getenv("LOR_URL", "http://localhost:9000")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:14b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))

MAX_MESSAGE_LENGTH = 4096  # Telegram hard limit
MAX_HISTORY_TURNS = 5      # In-memory conversation turns kept per chat
MAX_WATCHER_CHARS = 1400   # Budget for Watcher episodic context (priority)
MAX_LOR_CHARS = 1000       # Budget for LOR knowledge context
MIN_RELEVANCE_SCORE = 0.4  # Discard search results below this

SYSTEM_PROMPT = (
    "You are Second, a locally run assistant configured by Robert.\n"
    "Be direct, grounded, truth-seeking. Prefer clarity over persuasion.\n"
    "If uncertain, say you're uncertain and propose how to verify."
)

# =============================================================================
# LOGGING
# =============================================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# =============================================================================
# STATE
# =============================================================================

conversation_history: dict[int, list[dict]] = {}
_background_tasks: set[asyncio.Task] = set()

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def is_authorized(user_id: int) -> bool:
    return user_id == AUTHORIZED_USER_ID


def split_message(text: str) -> list[str]:
    """Split long messages to fit Telegram's limit."""
    if len(text) <= MAX_MESSAGE_LENGTH:
        return [text]

    parts = []
    while text:
        if len(text) <= MAX_MESSAGE_LENGTH:
            parts.append(text)
            break

        split_at = text.rfind('\n', 0, MAX_MESSAGE_LENGTH)
        if split_at == -1:
            split_at = text.rfind(' ', 0, MAX_MESSAGE_LENGTH)
        if split_at == -1:
            split_at = MAX_MESSAGE_LENGTH

        parts.append(text[:split_at])
        text = text[split_at:].lstrip()

    return parts


def _truncate_at_sentence(text: str, max_chars: int) -> str:
    """Truncate text at a sentence boundary within max_chars."""
    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]
    # Find last sentence-ending punctuation
    for end in ['. ', '.\n', '! ', '!\n', '? ', '?\n']:
        pos = truncated.rfind(end)
        if pos > max_chars // 2:
            return truncated[:pos + 1]
    # Fallback: cut at last space
    pos = truncated.rfind(' ')
    if pos > max_chars // 2:
        return truncated[:pos] + "..."
    return truncated + "..."


# =============================================================================
# CONTEXT RETRIEVAL (RAG)
# =============================================================================


async def search_watcher(query: str) -> list[dict]:
    """Search Watcher episodic memory. Returns filtered results."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(
                f"{WATCHER_URL}/query/search",
                json={"query": query, "limit": 5},
            )
            response.raise_for_status()
            results = response.json()
            return [r for r in results if r.get("score", 0) >= MIN_RELEVANCE_SCORE]
    except Exception as e:
        logger.warning(f"Watcher search failed: {e}")
        return []


async def search_lor(query: str) -> list[dict]:
    """Search LOR knowledge base. Returns filtered results."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(
                f"{LOR_URL}/api/search",
                json={"query": query, "top_k": 3},
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            return [r for r in results if r.get("score", 0) >= MIN_RELEVANCE_SCORE]
    except Exception as e:
        logger.warning(f"LOR search failed: {e}")
        return []


async def retrieve_context(query: str) -> tuple[str, str, bool]:
    """Retrieve RAG context from Watcher and LOR in parallel.

    Returns (context_text, source_summary, had_errors).
    """
    watcher_result, lor_result = await asyncio.gather(
        search_watcher(query),
        search_lor(query),
        return_exceptions=True,
    )

    watcher_error = isinstance(watcher_result, Exception)
    lor_error = isinstance(lor_result, Exception)
    had_errors = watcher_error and lor_error

    if watcher_error:
        logger.error(f"Watcher search exception: {watcher_result}")
        watcher_result = []
    if lor_error:
        logger.error(f"LOR search exception: {lor_result}")
        lor_result = []

    context_parts = []
    sources = []

    # Watcher episodes (priority — budget: MAX_WATCHER_CHARS)
    if watcher_result:
        watcher_chars = 0
        watcher_lines = []
        for ep in watcher_result:
            content = ep.get("content", "")
            truncated = _truncate_at_sentence(content, 300)
            if watcher_chars + len(truncated) > MAX_WATCHER_CHARS:
                break
            watcher_lines.append(f"[Memory] {truncated}")
            watcher_chars += len(truncated)
        if watcher_lines:
            context_parts.extend(watcher_lines)
            sources.append(f"watcher:{len(watcher_lines)}")

    # LOR passages (budget: MAX_LOR_CHARS)
    if lor_result:
        lor_chars = 0
        lor_lines = []
        for chunk in lor_result:
            text = chunk.get("text", "")
            collection = chunk.get("collection", "docs")
            label = "[Books]" if collection == "books" else "[Docs]"
            truncated = _truncate_at_sentence(text, 400)
            if lor_chars + len(truncated) > MAX_LOR_CHARS:
                break
            lor_lines.append(f"{label} {truncated}")
            lor_chars += len(truncated)
        if lor_lines:
            context_parts.extend(lor_lines)
            sources.append(f"lor:{len(lor_lines)}")

    context_text = "\n".join(context_parts) if context_parts else ""
    source_summary = ", ".join(sources) if sources else "none"

    return context_text, source_summary, had_errors


# =============================================================================
# LLM INTERACTION
# =============================================================================


async def query_llm(messages: list[dict]) -> str:
    """Send messages to Ollama chat API and return the response."""
    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": 0.4,
                        "repeat_penalty": 1.1,
                        "num_predict": 512,
                        "num_ctx": 2560,
                    },
                },
            )
            response.raise_for_status()
            return response.json().get("message", {}).get("content", "No response.")
    except httpx.TimeoutException:
        raise Exception("Ollama timed out. Model may be loading or busy.")
    except httpx.ConnectError:
        raise Exception("Cannot reach the language model. Is Ollama running?")
    except Exception as e:
        raise Exception(f"Ollama error: {str(e)}")


def build_messages(
    system: str,
    context: str,
    history: list[dict],
    user_msg: str,
    had_errors: bool = False,
) -> list[dict]:
    """Assemble the full message list for the LLM.

    Order: system prompt -> conversation history -> user message with RAG context.
    Truncation drops oldest pairs first (never orphan a user message without its response).
    """
    messages = [{"role": "system", "content": system}]

    # Add conversation history (budget ~2400 chars, drop oldest pairs first)
    history_budget = 2400
    history_chars = 0
    trimmed_history = []

    # Walk from newest to oldest pairs, then reverse for chronological order
    for i in range(len(history) - 1, 0, -2):
        pair_chars = len(history[i - 1].get("content", "")) + len(history[i].get("content", ""))
        if history_chars + pair_chars > history_budget:
            break
        trimmed_history = [history[i - 1], history[i]] + trimmed_history
        history_chars += pair_chars

    messages.extend(trimmed_history)

    # Build final user message with RAG context prepended
    final_parts = []
    if context:
        final_parts.append("--- Relevant Context ---")
        final_parts.append(context)
        final_parts.append("")
        final_parts.append(
            "Use the above context to inform your response. "
            "If the context doesn't cover the question, say so — don't fabricate."
        )
        final_parts.append("")

    if had_errors:
        final_parts.append(
            "(Knowledge base temporarily unavailable — responding from conversation only)"
        )
        final_parts.append("")

    final_parts.append(user_msg)

    messages.append({"role": "user", "content": "\n".join(final_parts)})

    return messages


# =============================================================================
# CONVERSATION HISTORY
# =============================================================================


def add_to_history(chat_id: int, user_msg: str, assistant_msg: str) -> None:
    """Add a user/assistant exchange to in-memory history."""
    if chat_id not in conversation_history:
        conversation_history[chat_id] = []

    history = conversation_history[chat_id]
    history.append({"role": "user", "content": user_msg})
    history.append({"role": "assistant", "content": assistant_msg})

    # Trim to MAX_HISTORY_TURNS pairs (each pair = 2 messages)
    max_messages = MAX_HISTORY_TURNS * 2
    if len(history) > max_messages:
        conversation_history[chat_id] = history[-max_messages:]


def get_history(chat_id: int) -> list[dict]:
    """Get conversation history for a chat."""
    return conversation_history.get(chat_id, [])


# =============================================================================
# WATCHER STORAGE
# =============================================================================


async def store_conversation(
    user_msg: str,
    assistant_msg: str,
    context_sources: str,
    chat_id: int,
    message_id: int,
) -> None:
    """Store a conversation exchange in Watcher as an episode."""
    try:
        content = f"Q: {user_msg}\nA: {assistant_msg}"
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{WATCHER_URL}/events",
                json={
                    "source": "telegram",
                    "event_type": "conversation",
                    "content": content,
                    "metadata": {
                        "user_message": user_msg[:500],
                        "assistant_response": assistant_msg[:500],
                        "context_sources": context_sources,
                        "chat_id": str(chat_id),
                        "message_id": str(message_id),
                        "decay_policy": "standard",
                    },
                },
            )
            if response.status_code == 200:
                logger.info(f"Stored conversation in Watcher (sources: {context_sources})")
            else:
                logger.warning(f"Watcher storage returned {response.status_code}")
    except Exception as e:
        logger.error(f"Failed to store conversation in Watcher: {e}")


async def store_in_watcher(content: str) -> bool:
    """Store a note in Watcher (for /remember command)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{WATCHER_URL}/events",
                json={
                    "source": "telegram",
                    "event_type": "note",
                    "content": content,
                    "metadata": {"via": "telegram", "author": "robert"},
                },
            )
            return response.status_code == 200
    except Exception as e:
        logger.error(f"Failed to store in Watcher: {e}")
        return False


# =============================================================================
# BACKGROUND TASK HELPERS
# =============================================================================


def _log_task_exception(task: asyncio.Task) -> None:
    """Callback for background tasks — logs exceptions."""
    _background_tasks.discard(task)
    if not task.cancelled() and task.exception():
        logger.error(f"Background task failed: {task.exception()}")


async def send_typing_loop(chat, done_event: asyncio.Event) -> None:
    """Send typing indicator every 4s until done_event is set."""
    try:
        while not done_event.is_set():
            await chat.send_action("typing")
            try:
                await asyncio.wait_for(done_event.wait(), timeout=4.0)
            except asyncio.TimeoutError:
                pass
    except Exception as e:
        logger.debug(f"Typing loop ended: {e}")


# =============================================================================
# HEALTH CHECK
# =============================================================================


async def check_services_health() -> dict[str, str]:
    """Check health of Ollama, Watcher, and LOR in parallel."""

    async def check_ollama():
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{OLLAMA_URL}/api/tags")
                return "up" if r.status_code == 200 else "degraded"
        except Exception:
            return "down"

    async def check_watcher():
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{WATCHER_URL}/health")
                return "up" if r.status_code == 200 else "degraded"
        except Exception:
            return "down"

    async def check_lor():
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{LOR_URL}/health")
                return "up" if r.status_code == 200 else "degraded"
        except Exception:
            return "down"

    ollama, watcher, lor = await asyncio.gather(
        check_ollama(), check_watcher(), check_lor()
    )

    return {"ollama": ollama, "watcher": watcher, "lor": lor}


# =============================================================================
# TELEGRAM HANDLERS
# =============================================================================


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    if not is_authorized(user.id):
        await update.message.reply_text("Sorry, this bot is private.")
        logger.warning(f"Unauthorized access attempt from user {user.id} ({user.username})")
        return

    services = await check_services_health()
    all_up = all(s == "up" for s in services.values())

    status_lines = []
    for svc, state in services.items():
        icon = "+" if state == "up" else "!"
        status_lines.append(f"  [{icon}] {svc}: {state}")

    await update.message.reply_text(
        f"Second {'ONLINE' if all_up else 'DEGRADED'}\n"
        f"Model: {OLLAMA_MODEL}\n\n"
        f"Services:\n" + "\n".join(status_lines) + "\n\n"
        f"Commands:\n"
        f"/status - Service health\n"
        f"/remember - Store a note in memory\n"
        f"/clear - Reset conversation history\n"
        f"/help - Show this message\n\n"
        f"Send any message to chat."
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    if not is_authorized(user.id):
        return

    services = await check_services_health()
    all_up = all(s == "up" for s in services.values())

    lines = [
        f"Second: {'healthy' if all_up else 'degraded'}",
        f"Model: {OLLAMA_MODEL}",
        f"LLM timeout: {OLLAMA_TIMEOUT}s",
        f"History: {MAX_HISTORY_TURNS} turns (in-memory)",
        "",
        "Services:",
    ]
    for svc, state in services.items():
        lines.append(f"  {svc}: {state}")

    chat_id = update.effective_chat.id
    history_len = len(get_history(chat_id)) // 2
    lines.append(f"\nConversation: {history_len} turns cached")

    await update.message.reply_text("\n".join(lines))


async def remember_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    if not is_authorized(user.id):
        return

    text = update.message.text.replace("/remember", "", 1).strip()
    if not text:
        await update.message.reply_text("Usage: /remember <something to store>")
        return

    await update.message.chat.send_action("typing")

    stored = await store_in_watcher(text)
    if stored:
        await update.message.reply_text("Remembered.")
        logger.info(f"Stored via /remember: {text[:80]}...")
    else:
        await update.message.reply_text("Failed to store. Is Watcher running?")


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    if not is_authorized(user.id):
        return

    chat_id = update.effective_chat.id
    had_history = chat_id in conversation_history and len(conversation_history[chat_id]) > 0
    conversation_history[chat_id] = []

    if had_history:
        await update.message.reply_text("Conversation history cleared.")
    else:
        await update.message.reply_text("No history to clear.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message_text = update.message.text

    if not is_authorized(user.id):
        await update.message.reply_text("Sorry, this bot is private.")
        return

    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    logger.info(f"Message from {user.id}: {message_text[:80]}...")

    # Start typing indicator loop
    done_event = asyncio.Event()
    typing_task = asyncio.create_task(send_typing_loop(update.message.chat, done_event))

    try:
        # Retrieve RAG context (parallel Watcher + LOR search)
        context_text, source_summary, had_errors = await retrieve_context(message_text)
        logger.info(f"Context retrieved: [{source_summary}]")

        # Build message list
        history = get_history(chat_id)
        messages = build_messages(SYSTEM_PROMPT, context_text, history, message_text, had_errors)

        # Query LLM
        response_text = await query_llm(messages)

        # Stop typing indicator
        done_event.set()
        await typing_task

        # Reply to user
        for part in split_message(response_text):
            await update.message.reply_text(part)

        logger.info(f"Response sent: {len(response_text)} chars")

        # Update in-memory history
        add_to_history(chat_id, message_text, response_text)

        # Store conversation in Watcher (background)
        store_task = asyncio.create_task(
            store_conversation(message_text, response_text, source_summary, chat_id, message_id)
        )
        _background_tasks.add(store_task)
        store_task.add_done_callback(_log_task_exception)

    except Exception as e:
        done_event.set()
        error_msg = str(e)
        logger.error(f"Error processing message: {error_msg}")
        await update.message.reply_text(f"Error: {error_msg}")


# =============================================================================
# MAIN
# =============================================================================


def main() -> None:
    logger.info("Starting Telegram Bot (Second)...")
    logger.info(f"Authorized user: {AUTHORIZED_USER_ID}")
    logger.info(f"Model: {OLLAMA_MODEL} via {OLLAMA_URL}")
    logger.info(f"Watcher: {WATCHER_URL} | LOR: {LOR_URL}")

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("remember", remember_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is running. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
