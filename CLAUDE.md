# Telegram-Wonder Engine Bot — CLAUDE.md

## What This Is

Robert's personal Telegram interface to the Wonder Engine. Every message is classified as
a question or information, then routed accordingly:
- **Question** → Wonder Engine → Three Gates → grounded response
- **Information** → Watcher directly → stored as episode

Single user. Single purpose. No cloud LLM. No conversation history.

---

## Version

**Current:** v2 (Wonder Engine backend)
**Previous:** v1 (direct Ollama backend — original CLAUDE.md described this)
**Telegram Bot:** `@roberts_clawd_bot`

---

## Look at These Files

This is a 335-line single-file bot. There is not much to navigate.

| File | What it does |
|------|--------------|
| `bot.py` | The entire bot. All handlers, intent classification, Wonder Engine client, Watcher client. |
| `bot.py:27` | **CRITICAL** — `TELEGRAM_TOKEN` hardcoded. This is a live token. Must move to env. |
| `bot.py:53–77` | `is_authorized()` — single-user gate. `split_message()` — handles Telegram's 4096 char limit. |
| `bot.py:80–84` | `format_wonder_response()` — formats Wonder Engine response for Telegram. Prepends `[CLASSIFICATION]`. |
| `bot.py:91–118` | `classify_intent()` — calls Ollama directly with `temperature=0.0, num_predict=10` to classify as QUESTION or INFORMATION. Falls back to "question" on failure. |
| `bot.py:125–141` | `query_wonder()` — `POST /query` to Wonder Engine with `include_gate_log: False`. |
| `bot.py:144–160` | `store_in_watcher()` — `POST /events` to Watcher. `source: "manual"`, `event_type: "note"`. |
| `bot.py:163–173` | `check_wonder_health()` — `GET /health` to Wonder Engine. Used by `/start` and `/status`. |
| `bot.py:180–207` | `/start` handler — health check + service status + command list. |
| `bot.py:210–245` | `/status` handler — health + dependencies + axioms display. |
| `bot.py:248–266` | `/remember` handler — explicit Watcher storage. Usage: `/remember <text>`. |
| `bot.py:269–271` | `/help` handler — delegates to `start()`. |
| `bot.py:273–310` | `handle_message()` — main handler. Intent → route to Wonder or Watcher. |
| `bot.py:316–334` | `main()` — register handlers, start polling. |
| `install_service.bat` | NSSM service setup. Sets dep on Ollama (not WonderEngine — known gap). Log rotation at 10MB. |
| `requirements.txt` | 2 packages: `python-telegram-bot>=21.0`, `httpx>=0.25.0`. No upper bounds. |

---

## Service Info

| Item | Value |
|------|-------|
| **Service name** | `TelegramOllamaBot` |
| **Telegram bot** | `@roberts_clawd_bot` |
| **Authorized user** | ID `1991846232` (Robert) |
| **Backend** | Wonder Engine (port 9600) |
| **Intent classifier** | Ollama (port 11434) |
| **Storage** | Watcher (port 9100) |
| **Logs** | `E:\telegram-ollama-bot\logs\bot.log` (10MB rotation) |

---

## Dependencies (MUST be running)

```
Startup order:
1. Ollama (11434)         — intent classification calls
2. Qdrant (6333)          — Watcher depends on it
3. LOR (9000)             — Wonder Engine depends on it
4. Watcher (9100)         — storage for information messages + /remember
5. Wonder Engine (9600)   — query backend for question messages
6. TelegramOllamaBot      — this service
```

**Note:** NSSM service dependency is set to `Ollama` only. If Wonder Engine is down, the bot
starts but all question routing fails with a `ConnectError`. Wonder Engine should be added
as a dependency but is not currently managed by NSSM.

Degradation behavior:
- Wonder Engine down → questions return error message to user
- Watcher down → information messages return "Failed to store" to user
- Ollama down → intent classification fails → everything treated as a question

---

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Wonder Engine health + dependency status + command list |
| `/status` | Health details + dependency states + Three Axioms |
| `/remember <text>` | Store text in Watcher explicitly (skips intent classification) |
| `/help` | Same as `/start` |
| Any text | Classify intent → route to Wonder Engine (question) or Watcher (information) |

---

## Running

### Manual
```cmd
cd /d E:\telegram-ollama-bot
call venv\Scripts\activate.bat
python bot.py
```

### Service
```cmd
sc query TelegramOllamaBot
sc stop TelegramOllamaBot
sc start TelegramOllamaBot
```

Re-install service (run as Administrator):
```cmd
install_service.bat
```

Logs: `E:\telegram-ollama-bot\logs\bot.log`

---

## Configuration (ALL in bot.py — known issue)

| Constant | Value | Notes |
|----------|-------|-------|
| `TELEGRAM_TOKEN` | (redacted) | **CRITICAL: hardcoded live token** |
| `AUTHORIZED_USER_ID` | `1991846232` | Robert's Telegram ID |
| `WONDER_URL` | `http://localhost:9600` | Wonder Engine |
| `WATCHER_URL` | `http://localhost:9100` | Watcher |
| `OLLAMA_URL` | `http://localhost:11434` | For intent classification |
| `WONDER_TIMEOUT` | `120` seconds | Long — gate pipeline can take 60–90s |
| `OLLAMA_MODEL` | `qwen2.5:14b-instruct` | Intent classifier model |
| `MAX_MESSAGE_LENGTH` | `4096` | Telegram's hard limit |

---

## Known Issues (See `docs/REFACTORING.md`)

| Issue | Location | Severity |
|-------|----------|----------|
| Telegram token hardcoded in source | `bot.py:27` | CRITICAL |
| All config hardcoded (no env vars) | `bot.py:27–35` | HIGH |
| NSSM service dependency missing WonderEngine | `install_service.bat:43` | MEDIUM |
| No upper bounds on dependency pins | `requirements.txt` | LOW |
| CLAUDE.md described old v1 Ollama bot (now fixed) | — | LOW |

---

## Message Routing Logic

```
Any non-command text message
    │
    ▼
classify_intent(text) ─► Ollama (temperature=0, max 10 tokens)
    │
    ├── "INFORMATION" → store_in_watcher(text)
    │                   → Reply: "Noted."
    │
    └── "QUESTION" (default) → query_wonder(text)
                                → format_wonder_response()
                                → Reply: "[CLASSIFICATION]\n\nresponse text"
```

Intent classification fails silently — any error defaults to "question".
This means information messages may end up routed to Wonder Engine if Ollama is slow/down.
The Wonder Engine handles it gracefully (just gates the information like a query).

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No response | Check Wonder Engine: `curl http://localhost:9600/health` |
| Timeout | Gate pipeline slow (boundary/probe path can take 60–90s) |
| "Sorry, this bot is private" | User ID doesn't match `AUTHORIZED_USER_ID` |
| "Failed to store" | Check Watcher: `curl http://localhost:9100/health` |
| Intent always "question" | Check Ollama: `curl http://localhost:11434/api/tags` |
| Service won't start | Check `E:\telegram-ollama-bot\logs\bot.log` |
