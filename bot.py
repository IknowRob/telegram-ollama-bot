#!/usr/bin/env python
"""
Telegram-Wonder Engine Bot
Routes questions through Wonder Engine's Three Gates.
Stores information in Watcher when Robert is telling, not asking.

Author: Robert (HF Builders)
Location: E:\telegram-ollama-bot\bot.py
"""

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
AUTHORIZED_USER_ID = 1991846232  # Robert's Telegram ID

WONDER_URL = "http://localhost:9600"
WATCHER_URL = "http://localhost:9100"
OLLAMA_URL = "http://localhost:11434"
WONDER_TIMEOUT = 120
OLLAMA_MODEL = "qwen2.5:14b-instruct"

MAX_MESSAGE_LENGTH = 4096  # Telegram's limit

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


def format_wonder_response(data: dict) -> str:
    """Format Wonder Engine response for Telegram — clean, no gate log."""
    classification = data.get("classification", "unknown").upper().replace("_", " ")
    response_text = data.get("response", "No response.")
    return f"[{classification}]\n\n{response_text}"


# =============================================================================
# INTENT DETECTION
# =============================================================================

async def classify_intent(text: str) -> str:
    """Use Ollama to classify whether the message is a question or information.
    Returns 'question' or 'information'."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": (
                        "Classify this message as either QUESTION or INFORMATION.\n"
                        "QUESTION = the user is asking something, seeking an answer, or wants to know something.\n"
                        "INFORMATION = the user is stating a fact, reporting something, sharing a note, or entering data.\n\n"
                        f"Message: {text}\n\n"
                        "Reply with exactly one word: QUESTION or INFORMATION"
                    ),
                    "stream": False,
                    "options": {"temperature": 0.0, "num_predict": 10},
                },
            )
            response.raise_for_status()
            result = response.json().get("response", "").strip().upper()
            if "INFORMATION" in result:
                return "information"
            return "question"
    except Exception as e:
        logger.warning(f"Intent classification failed: {e}, defaulting to question")
        return "question"


# =============================================================================
# WONDER ENGINE INTEGRATION
# =============================================================================

async def query_wonder(query: str) -> dict:
    """Query Wonder Engine and return the full response."""
    try:
        async with httpx.AsyncClient(timeout=WONDER_TIMEOUT) as client:
            response = await client.post(
                f"{WONDER_URL}/query",
                json={"query": query, "include_gate_log": False},
            )
            response.raise_for_status()
            return response.json()

    except httpx.TimeoutException:
        raise Exception("Wonder Engine timed out. Gates may be processing a complex query.")
    except httpx.ConnectError:
        raise Exception("Cannot connect to Wonder Engine. Is it running on port 9600?")
    except Exception as e:
        raise Exception(f"Wonder Engine error: {str(e)}")


async def store_in_watcher(content: str, source: str = "telegram") -> bool:
    """Store information in Watcher as an episode."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{WATCHER_URL}/events",
                json={
                    "source": "manual",
                    "event_type": "note",
                    "content": content,
                    "metadata": {"via": "telegram", "author": "robert"},
                },
            )
            return response.status_code == 200
    except Exception as e:
        logger.error(f"Failed to store in Watcher: {e}")
        return False


async def check_wonder_health() -> tuple[bool, dict]:
    """Check Wonder Engine health and return dependency status."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{WONDER_URL}/health")
            response.raise_for_status()
            data = response.json()
            healthy = data.get("status") == "healthy"
            return healthy, data
    except Exception as e:
        return False, {"error": str(e)}


# =============================================================================
# TELEGRAM HANDLERS
# =============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    if not is_authorized(user.id):
        await update.message.reply_text("Sorry, this bot is private.")
        logger.warning(f"Unauthorized access attempt from user {user.id} ({user.username})")
        return

    healthy, data = await check_wonder_health()
    services = data.get("services", {})
    axioms_intact = data.get("axioms_intact", False)

    status_lines = []
    for svc, state in services.items():
        icon = "+" if state == "up" else "!"
        status_lines.append(f"  [{icon}] {svc}: {state}")

    await update.message.reply_text(
        f"Wonder Engine {'ONLINE' if healthy else 'DEGRADED'}\n"
        f"Axioms intact: {axioms_intact}\n\n"
        f"Services:\n" + "\n".join(status_lines) + "\n\n"
        f"Commands:\n"
        f"/status - Engine info + axioms\n"
        f"/remember - Store a note in Watcher\n"
        f"/help - Show this message\n\n"
        f"Ask a question -> routes through the Three Gates\n"
        f"State a fact -> stored in Watcher automatically"
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    if not is_authorized(user.id):
        return

    healthy, health_data = await check_wonder_health()

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{WONDER_URL}/axioms")
            axioms = r.json() if r.status_code == 200 else []
    except Exception:
        axioms = []

    lines = [
        f"Wonder Engine: {'healthy' if healthy else 'degraded'}",
        f"Endpoint: {WONDER_URL}",
        f"Timeout: {WONDER_TIMEOUT}s",
        "",
    ]

    services = health_data.get("services", {})
    if services:
        lines.append("Dependencies:")
        for svc, state in services.items():
            lines.append(f"  {svc}: {state}")
        lines.append("")

    if axioms:
        lines.append("The Three Axioms:")
        for i, a in enumerate(axioms, 1):
            statement = a if isinstance(a, str) else a.get("statement", str(a))
            lines.append(f"  {i}. {statement}")

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
        await update.message.reply_text(f"Remembered.")
        logger.info(f"Stored via /remember: {text[:80]}...")
    else:
        await update.message.reply_text("Failed to store. Is Watcher running?")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message_text = update.message.text

    if not is_authorized(user.id):
        await update.message.reply_text("Sorry, this bot is private.")
        return

    logger.info(f"Message from {user.id}: {message_text[:80]}...")

    await update.message.chat.send_action("typing")

    try:
        intent = await classify_intent(message_text)
        logger.info(f"Intent: {intent}")

        if intent == "information":
            stored = await store_in_watcher(message_text)
            if stored:
                await update.message.reply_text("Noted.")
                logger.info(f"Auto-stored as information: {message_text[:80]}...")
            else:
                await update.message.reply_text("Failed to store. Is Watcher running?")
        else:
            data = await query_wonder(message_text)
            response_text = format_wonder_response(data)

            for part in split_message(response_text):
                await update.message.reply_text(part)

            classification = data.get("classification", "?")
            latency = data.get("latency_ms", 0)
            logger.info(f"Response sent: {classification}, {latency}ms")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error processing message: {error_msg}")
        await update.message.reply_text(f"Error: {error_msg}")

# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    logger.info("Starting Telegram-Wonder Engine Bot...")
    logger.info(f"Authorized user: {AUTHORIZED_USER_ID}")
    logger.info(f"Wonder Engine: {WONDER_URL}")

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("remember", remember_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is running. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
