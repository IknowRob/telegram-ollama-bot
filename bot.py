#!/usr/bin/env python
"""
Telegram-Ollama Bot
A lightweight bot connecting Telegram to local Ollama instance.

Author: Robert (HF Builders)
Location: E:\telegram-ollama-bot\bot.py
"""

import asyncio
import logging
from datetime import datetime

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

TELEGRAM_TOKEN = "8530568052:AAHh3anh3Xu2t-CJFrBC-nK49_7_nUeJyyA"
AUTHORIZED_USER_ID = 1991846232  # Robert's Telegram ID

OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:14b-instruct"
OLLAMA_TIMEOUT = 120
OLLAMA_CONTEXT_SIZE = 8192

MAX_CONTEXT_MESSAGES = 10
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
# CONVERSATION STORAGE
# =============================================================================

conversations: dict[int, list[dict]] = {}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def is_authorized(user_id: int) -> bool:
    """Check if user is authorized to use the bot."""
    return user_id == AUTHORIZED_USER_ID


def get_conversation(user_id: int) -> list[dict]:
    """Get or create conversation history for a user."""
    if user_id not in conversations:
        conversations[user_id] = []
    return conversations[user_id]


def add_message(user_id: int, role: str, content: str) -> None:
    """Add a message to conversation history, maintaining max limit."""
    conv = get_conversation(user_id)
    conv.append({"role": role, "content": content, "timestamp": datetime.now().isoformat()})

    # Keep only last N message pairs
    if len(conv) > MAX_CONTEXT_MESSAGES * 2:
        conversations[user_id] = conv[-(MAX_CONTEXT_MESSAGES * 2):]


def format_prompt(messages: list[dict]) -> str:
    """Format conversation for Ollama prompt."""
    system = """You are a helpful AI assistant running locally on Robert's server.
You are powered by qwen2.5:14b-instruct via Ollama on an RTX 5070 Ti.
Be concise but thorough. Robert is a contractor who builds custom homes."""

    formatted = [system, ""]
    for msg in messages:
        role = "User" if msg["role"] == "user" else "Assistant"
        formatted.append(f"{role}: {msg['content']}")

    formatted.append("Assistant:")
    return "\n".join(formatted)


def split_message(text: str) -> list[str]:
    """Split long messages to fit Telegram's limit."""
    if len(text) <= MAX_MESSAGE_LENGTH:
        return [text]

    parts = []
    while text:
        if len(text) <= MAX_MESSAGE_LENGTH:
            parts.append(text)
            break

        # Find a good split point
        split_at = text.rfind('\n', 0, MAX_MESSAGE_LENGTH)
        if split_at == -1:
            split_at = text.rfind(' ', 0, MAX_MESSAGE_LENGTH)
        if split_at == -1:
            split_at = MAX_MESSAGE_LENGTH

        parts.append(text[:split_at])
        text = text[split_at:].lstrip()

    return parts

# =============================================================================
# OLLAMA INTEGRATION
# =============================================================================

async def query_ollama(prompt: str) -> str:
    """Query Ollama and return the response."""
    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_ctx": OLLAMA_CONTEXT_SIZE,
                        "temperature": 0.7,
                    }
                }
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "No response generated.")

    except httpx.TimeoutException:
        raise Exception("Ollama request timed out. Model may be loading or GPU is busy.")
    except httpx.ConnectError:
        raise Exception("Cannot connect to Ollama. Is it running?")
    except Exception as e:
        raise Exception(f"Ollama error: {str(e)}")


async def check_ollama_health() -> tuple[bool, str]:
    """Check if Ollama is running and model is available."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            response.raise_for_status()
            models = response.json().get("models", [])
            model_names = [m["name"] for m in models]

            if OLLAMA_MODEL in model_names:
                return True, f"Model {OLLAMA_MODEL} ready"
            else:
                return False, f"Model {OLLAMA_MODEL} not found"
    except Exception as e:
        return False, f"Ollama error: {str(e)}"

# =============================================================================
# TELEGRAM HANDLERS
# =============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user = update.effective_user

    if not is_authorized(user.id):
        await update.message.reply_text("Sorry, this bot is private.")
        logger.warning(f"Unauthorized access attempt from user {user.id} ({user.username})")
        return

    healthy, status = await check_ollama_health()

    await update.message.reply_text(
        f"Hello Robert!\n\n"
        f"Connected to local Ollama.\n"
        f"Model: {OLLAMA_MODEL}\n"
        f"Status: {status}\n\n"
        f"Commands:\n"
        f"/clear - Start fresh conversation\n"
        f"/model - Show model info\n"
        f"/help - Show this message\n\n"
        f"Just send me a message to chat!"
    )


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /clear command."""
    user = update.effective_user

    if not is_authorized(user.id):
        return

    conversations[user.id] = []
    await update.message.reply_text("Conversation cleared. Let's start fresh!")


async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /model command."""
    user = update.effective_user

    if not is_authorized(user.id):
        return

    healthy, status = await check_ollama_health()
    conv_len = len(get_conversation(user.id))

    await update.message.reply_text(
        f"Model: {OLLAMA_MODEL}\n"
        f"Endpoint: {OLLAMA_URL}\n"
        f"Context Size: {OLLAMA_CONTEXT_SIZE} tokens\n"
        f"Timeout: {OLLAMA_TIMEOUT}s\n"
        f"Messages in memory: {conv_len}\n\n"
        f"Status: {status}"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    await start(update, context)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages."""
    user = update.effective_user
    message_text = update.message.text

    if not is_authorized(user.id):
        await update.message.reply_text("Sorry, this bot is private.")
        return

    logger.info(f"Message from {user.id}: {message_text[:50]}...")

    # Add user message to history
    add_message(user.id, "user", message_text)

    # Show typing indicator
    await update.message.chat.send_action("typing")

    try:
        # Build prompt with context
        conversation = get_conversation(user.id)
        prompt = format_prompt(conversation)

        # Query Ollama
        response = await query_ollama(prompt)

        # Add assistant response to history
        add_message(user.id, "assistant", response)

        # Send response (split if too long)
        for part in split_message(response):
            await update.message.reply_text(part)

        logger.info(f"Response sent: {response[:50]}...")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error processing message: {error_msg}")
        await update.message.reply_text(f"Error: {error_msg}")

# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    """Start the bot."""
    logger.info("Starting Telegram-Ollama Bot...")
    logger.info(f"Authorized user: {AUTHORIZED_USER_ID}")
    logger.info(f"Ollama endpoint: {OLLAMA_URL}")
    logger.info(f"Model: {OLLAMA_MODEL}")

    # Create application
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("model", model_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Run the bot
    logger.info("Bot is running. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
