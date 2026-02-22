# Telegram Bot — Second (Memory Pipeline) — CLAUDE.md

## What This Is

Robert's personal Telegram interface to Second, a locally run assistant powered by `qwen3:14b`.
Every message goes through a RAG pipeline — Watcher episodic memory and LOR knowledge base provide
context, the LLM responds, and the exchange is stored back in Watcher for persistent memory.

Single user. Single model. No cloud LLM. Conversation history (in-memory) + persistent memory (Watcher).

---

## Version

**Current:** v3 (Memory Pipeline — Watcher + LOR RAG)
**Previous:** v2 (Wonder Engine backend — intent classification, Three Gates routing)
**Telegram Bot:** `@roberts_clawd_bot`

---

## Look at These Files

Single-file bot with RAG context retrieval and conversation memory.

| File | What it does |
|------|--------------|
| `bot.py` | The entire bot. All handlers, RAG pipeline, LLM client, Watcher storage. |
| `bot.py:29–51` | Configuration — env vars, model settings, context budgets, system prompt. |
| `bot.py:69–72` | State — `conversation_history` (in-memory per chat), `_background_tasks` (GC protection). |
| `bot.py:78–106` | `is_authorized()`, `split_message()`, `_truncate_at_sentence()` — utility functions. |
| `bot.py:113–180` | RAG pipeline — `search_watcher()`, `search_lor()`, `retrieve_context()`. Parallel search with budget-based assembly. |
| `bot.py:187–247` | LLM interaction — `query_llm()` (Ollama chat API) and `build_messages()` (system + history + RAG context + user message). |
| `bot.py:254–270` | Conversation history — `add_to_history()`, `get_history()`. In-memory, 5 turns, lost on restart. |
| `bot.py:277–316` | Watcher storage — `store_conversation()` (background, Q+A format), `store_in_watcher()` (for /remember). |
| `bot.py:323–342` | Background helpers — `_log_task_exception()`, `send_typing_loop()` (repeats every 4s). |
| `bot.py:349–380` | `check_services_health()` — parallel health check of Ollama, Watcher, LOR. |
| `bot.py:387–430` | `/start` and `/status` handlers — service health display. |
| `bot.py:433–460` | `/remember` and `/clear` handlers. |
| `bot.py:466–517` | `handle_message()` — main message handler (RAG retrieve → build messages → LLM → reply → store). |
| `bot.py:524–543` | `main()` — register handlers, start polling. |
| `install_service.bat` | NSSM service setup. Log rotation at 10MB. |
| `requirements.txt` | 3 packages: `python-telegram-bot`, `httpx`, `python-dotenv`. |
| `.env` | Token and model override. In `.gitignore`. |

---

## Service Info

| Item | Value |
|------|-------|
| **Service name** | `TelegramOllamaBot` |
| **Telegram bot** | `@roberts_clawd_bot` |
| **Authorized user** | ID `1991846232` (Robert) |
| **Model** | `qwen3:14b` via Ollama (port 11434) |
| **RAG sources** | Watcher (port 9100) + LOR (port 9000) |
| **Storage** | Watcher (port 9100) — `source: "telegram"` |
| **Logs** | `E:\telegram-ollama-bot\logs\bot.log` (10MB rotation) |

---

## Dependencies (MUST be running)

```
Startup order:
1. Ollama (11434)         — LLM inference
2. Qdrant (6333)          — Watcher + LOR vector search
3. LOR (9000)             — knowledge base RAG context (optional — degrades gracefully)
4. Watcher (9100)         — episodic memory RAG context + conversation storage (optional — degrades gracefully)
5. TelegramOllamaBot      — this service
```

**Note:** Only Ollama is a hard dependency. If Watcher and/or LOR are down, the bot still
responds using conversation history alone (with a note to the user if both are unavailable).

Degradation behavior:
- Watcher down → No episodic context, storage fails (logged). LLM still responds.
- LOR down → No knowledge base context. LLM still responds.
- Both down → Final user message notes unavailability. LLM responds with history only.
- Ollama down → User-friendly error: "Cannot reach the language model. Is Ollama running?"

---

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Service health (Ollama, Watcher, LOR) + command list |
| `/status` | Health details + model info + conversation turns cached |
| `/remember <text>` | Store text in Watcher explicitly (`source: "telegram"`, `event_type: "note"`) |
| `/clear` | Reset in-memory conversation history for this chat |
| `/help` | Same as `/start` |
| Any text | RAG context retrieval → LLM response → store exchange in Watcher |

---

## Message Flow

```
User message
  |
  +-- start typing loop (repeats every 4s)
  |
  +-- retrieve_context(message)              <-- asyncio.gather (parallel, 5s each)
  |     +-- search_watcher(message)          <-- POST /query/search, filter by score >= 0.4
  |     +-- search_lor(message)              <-- POST /api/search, filter by score >= 0.4
  |
  +-- build_messages(SYSTEM_PROMPT, context, history, message)
  |     -> [system (3 lines), ...history pairs (chronological), user msg with RAG context]
  |
  +-- query_llm(messages)                    <-- POST /api/chat (120s, num_ctx=2560)
  |
  +-- stop typing loop
  +-- reply to user
  |
  +-- add_to_history(chat_id, user + assistant)
  |
  +-- store_conversation(...)                <-- background task with GC protection
        -> POST /events {source: "telegram", event_type: "conversation"}
        -> exception callback logs failures
```

Context is injected into the **final user message** (not the system prompt):
```
--- Relevant Context ---
[Memory] episodic content from Watcher...
[Books] passage from LOR books...

Use the above context to inform your response. If the context doesn't cover the question, say so — don't fabricate.

User's actual question here
```

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

## Configuration

All config is loaded from environment variables. Secret values use `os.environ` (fail-fast),
non-secret values use `os.getenv` with defaults. The `.env` file in the project root is
loaded by `python-dotenv` at startup.

| Env Var | Default | Notes |
|---------|---------|-------|
| `TELEGRAM_TOKEN` | *(none — required)* | Loaded from `.env`, fail-fast if missing |
| `AUTHORIZED_USER_ID` | `1991846232` | Robert's Telegram ID |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API |
| `WATCHER_URL` | `http://localhost:9100` | Watcher episodic memory |
| `LOR_URL` | `http://localhost:9000` | LOR knowledge base |
| `OLLAMA_MODEL` | `qwen3:14b` | LLM model for all responses |
| `OLLAMA_TIMEOUT` | `120` | Seconds — model loading can take time |
| `MAX_MESSAGE_LENGTH` | `4096` | Telegram hard limit — not configurable |

### LLM Options (hardcoded in bot.py)

| Option | Value | Rationale |
|--------|-------|-----------|
| `temperature` | `0.4` | Reduce hallucination |
| `repeat_penalty` | `1.1` | Reduce repetitive output |
| `num_predict` | `512` | Cap response length |
| `num_ctx` | `2560` | 25% buffer over estimated usage |

### Context Budgets (hardcoded in bot.py)

| Budget | Value | Notes |
|--------|-------|-------|
| `MAX_HISTORY_TURNS` | `5` | In-memory conversation turns per chat |
| `MAX_WATCHER_CHARS` | `1400` | Watcher episodic context (priority) |
| `MAX_LOR_CHARS` | `1000` | LOR knowledge context |
| `MIN_RELEVANCE_SCORE` | `0.4` | Discard results below this threshold |
| History budget | `~2400 chars` | Conversation history in message list |

---

## Known Limitations (v3)

| Issue | Severity | Notes |
|-------|----------|-------|
| Watcher returns 200-char truncated content | LOW | Episodes may lose detail. LOR returns 500 chars which compensates. Follow-up: add `max_content_length` param to Watcher search. |
| Token budget is char-estimated, not counted | LOW | ~3.5 chars/token approximation. `num_ctx=2560` with 25% buffer. Follow-up: add tokenizer counting. |
| Cold start loses conversation history | MEDIUM | In-memory history empty on restart. Watcher search partially recovers context. Follow-up: seed from recent telegram episodes on startup. |
| Short messages ("yes", "ok") produce poor RAG | LOW | No query expansion. Follow-up: expand using conversation context. |
| No upper bounds on dependency pins | LOW | `requirements.txt` has no version pins. |

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No response | Check Ollama: `curl http://localhost:11434/api/tags` |
| Timeout | Model may be loading. First message after idle takes longer. |
| "Sorry, this bot is private" | User ID doesn't match `AUTHORIZED_USER_ID` |
| "Failed to store" | Check Watcher: `curl http://localhost:9100/health` |
| No RAG context in logs | Check LOR: `curl http://localhost:9000/health` |
| Service won't start | Check `E:\telegram-ollama-bot\logs\bot.log` |
