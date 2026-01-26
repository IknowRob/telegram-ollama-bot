# Telegram-Ollama Bot

A lightweight Python Telegram bot that connects directly to a local Ollama instance.

## Why This Exists (vs Clawdbot)

**Clawdbot** is a full-featured AI messaging gateway with many capabilities, but its local Ollama integration has bugs. This simple bot fills that gap.

### Clawdbot Capabilities (what it CAN do)
- Multi-channel support (Telegram, WhatsApp, Discord, Slack, Signal, etc.)
- Cloud LLM providers (Anthropic, OpenRouter, OpenAI, etc.)
- Agent system with tools and skills
- Web dashboard at http://127.0.0.1:18789/
- Device pairing and authentication
- Scheduled tasks (cron)
- Memory and conversation management
- Browser automation
- Canvas for visual outputs

### Clawdbot Limitations (why we built this)
- **Ollama integration is broken** - Crashes with "Unhandled API in mapOptionsForApi" error
- Requires API keys even for local models
- Complex configuration for simple use cases
- Heavy resource usage (~1GB RAM)

### This Bot's Scope (intentionally minimal)
- **Single purpose**: Telegram ↔ Ollama bridge
- **Single user**: Only Robert (ID: 1991846232)
- **Single model**: qwen2.5:14b-instruct
- **No cloud dependencies**: 100% local inference
- **Simple**: ~250 lines of Python, single file

## Configuration

All config is in `bot.py`:

```python
TELEGRAM_TOKEN = "..."           # Bot token from @BotFather
AUTHORIZED_USER_ID = 1991846232  # Your Telegram user ID
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:14b-instruct"
OLLAMA_TIMEOUT = 120             # seconds
MAX_CONTEXT_MESSAGES = 10        # conversation memory
```

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome + Ollama health check |
| `/clear` | Clear conversation history |
| `/model` | Show current model info |
| `/help` | Show help |
| Any text | Chat with Ollama |

## Files

```
E:\telegram-ollama-bot\
├── bot.py              # Main bot (~250 lines)
├── requirements.txt    # Dependencies
├── start_bot.bat       # Manual start
├── install_service.bat # NSSM service setup (run as Admin)
├── logs\               # Log files (created by service)
└── venv\               # Python environment
```

## Running

### Manual
```cmd
cd /d E:\telegram-ollama-bot
call venv\Scripts\activate.bat
python bot.py
```

### As Windows Service
Run `install_service.bat` as Administrator.

Service commands:
```cmd
sc query TelegramOllamaBot
sc stop TelegramOllamaBot
sc start TelegramOllamaBot
```

## Dependencies

- Python 3.11+
- python-telegram-bot (async Telegram API)
- httpx (async HTTP client for Ollama)
- Ollama running on localhost:11434

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No response | Check Ollama: `curl http://localhost:11434/api/tags` |
| Timeout | Model loading into VRAM (~5-10s first query) |
| "Unauthorized" | Check your Telegram user ID matches config |
| Service won't start | Check `E:\telegram-ollama-bot\logs\bot.log` |

## Future Enhancements

- [ ] Multiple model support (`/switch <model>`)
- [ ] LOR integration (`/lor <query>`)
- [ ] Persistent conversation history (SQLite)
- [ ] Image support (when Ollama adds vision)
