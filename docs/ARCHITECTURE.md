# Telegram-Wonder Engine Bot — Architecture

## Overview

A thin routing layer between Telegram and the Wonder Engine stack. It does two things:
1. Classify every message as a question or information (via Ollama)
2. Route accordingly — questions through the Three Gates, information into Watcher

The bot has no storage, no state, no database. It is a pure message router.

---

## Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Telegram                                 │
│         @roberts_clawd_bot (user ID: 1991846232)            │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTPS (Telegram Bot API)
                         │ python-telegram-bot v21+ (long polling)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│            TelegramOllamaBot (NSSM service)                 │
│            E:\telegram-ollama-bot\bot.py                    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Message Router                         │    │
│  │                                                     │    │
│  │  classify_intent(text)                              │    │
│  │    └── POST /api/generate ──────────────────────────────► Ollama (11434)
│  │          temperature=0, max_tokens=10               │    │   qwen2.5:14b
│  │          → "QUESTION" or "INFORMATION"              │    │
│  │                                                     │    │
│  │  if QUESTION:                                       │    │
│  │    query_wonder(text)                               │    │
│  │      └── POST /query ───────────────────────────────────► Wonder Engine (9600)
│  │           {query, include_gate_log: false}          │    │   Gate 1 → Gate 2 → Gate 3
│  │           timeout: 120s                             │    │
│  │           → {response, classification, latency_ms}  │    │
│  │           format: "[CLASSIFICATION]\n\ntext"        │    │
│  │                                                     │    │
│  │  if INFORMATION:                                    │    │
│  │    store_in_watcher(text)                           │    │
│  │      └── POST /events ──────────────────────────────────► Watcher (9100)
│  │           {source: "manual", event_type: "note"}    │    │
│  │           → stored as episode                       │    │
│  │                                                     │    │
│  │  /remember <text>:                                  │    │
│  │    store_in_watcher(text) — bypasses classification │    │
│  │                                                     │    │
│  │  /start, /status:                                   │    │
│  │    GET /health ─────────────────────────────────────────► Wonder Engine (9600)
│  │    GET /axioms ─────────────────────────────────────────► Wonder Engine (9600)
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

## Message Lifecycle — Text Message (Question Path)

```
User sends: "What is a wet vent?"
    │
    ▼
Telegram delivers to bot via long polling
    │
    ▼
handle_message(update, context)
    │
    ├── is_authorized(user_id)?
    │     No → "Sorry, this bot is private." → stop
    │     Yes → continue
    │
    ├── update.message.chat.send_action("typing")
    │     User sees "typing..." indicator
    │
    ├── classify_intent("What is a wet vent?")
    │     POST http://localhost:11434/api/generate
    │     model: qwen2.5:14b-instruct
    │     prompt: "Classify as QUESTION or INFORMATION\n\nMessage: What is a wet vent?\n\nReply with one word:"
    │     temperature: 0.0, num_predict: 10
    │     → "QUESTION"
    │     (falls back to "question" on timeout/error)
    │
    ├── intent == "question" → query_wonder("What is a wet vent?")
    │     POST http://localhost:9600/query
    │     {query: "What is a wet vent?", include_gate_log: false}
    │     timeout: 120s
    │     → Wonder Engine runs Gate 1 → Gate 2 → Gate 3
    │     → {response: "GROUNDED: ...", classification: "partially_grounded", latency_ms: 11200}
    │
    ├── format_wonder_response(data)
    │     → "[PARTIALLY GROUNDED]\n\nGROUNDED: According to the plumbing code..."
    │
    └── split_message(text) → send each part
          (long responses split at newline boundaries to fit 4096 char limit)
```

---

## Message Lifecycle — Text Message (Information Path)

```
User sends: "The Olsan foundation pour is scheduled for March 15"
    │
    ▼
classify_intent(...)
    → "INFORMATION"
    │
    ▼
store_in_watcher("The Olsan foundation pour is scheduled for March 15")
    POST http://localhost:9100/events
    {
      "source": "manual",
      "event_type": "note",
      "content": "The Olsan foundation pour is scheduled for March 15",
      "metadata": {"via": "telegram", "author": "robert"}
    }
    → HTTP 200 → True
    │
    ▼
Reply: "Noted."
```

---

## /start and /status Lifecycle

```
User sends: /start
    │
    ▼
check_wonder_health()
    GET http://localhost:9600/health
    → {status: "healthy", services: {lor: "up", watcher: "up", ollama: "up"}, axioms_intact: true}
    │
    ▼
Reply:
  "Wonder Engine ONLINE
   Axioms intact: True

   Services:
     [+] lor: up
     [+] watcher: up
     [+] ollama: up

   Commands:
   /status - Engine info + axioms
   /remember - Store a note in Watcher
   /help - Show this message

   Ask a question -> routes through the Three Gates
   State a fact -> stored in Watcher automatically"
```

```
User sends: /status
    │
    ├── check_wonder_health()
    │     GET http://localhost:9600/health
    │
    └── GET http://localhost:9600/axioms
          → [{statement: "Ground truth exists.", gate: "Gate 1: Grounding", ...}, ...]

Reply:
  "Wonder Engine: healthy
   Endpoint: http://localhost:9600
   Timeout: 120s

   Dependencies:
     lor: up
     watcher: up
     ollama: up

   The Three Axioms:
     1. Ground truth exists.
     2. Ground truth is discoverable.
     3. Discovery is relational."
```

---

## Intent Classification Design

The classifier is minimal by design:

```python
prompt = (
    "Classify this message as either QUESTION or INFORMATION.\n"
    "QUESTION = the user is asking something, seeking an answer, or wants to know something.\n"
    "INFORMATION = the user is stating a fact, reporting something, sharing a note, or entering data.\n\n"
    f"Message: {text}\n\n"
    "Reply with exactly one word: QUESTION or INFORMATION"
)
options = {"temperature": 0.0, "num_predict": 10}
```

- `temperature: 0.0` — deterministic, no creativity needed
- `num_predict: 10` — one word response, stop early
- `timeout: 15s` — shorter than Wonder Engine timeout
- Falls back to `"question"` on any failure

**Classification accuracy notes:**
- Clear questions → reliable QUESTION classification
- Clear statements → reliable INFORMATION classification
- Ambiguous (e.g., "tell me about wet vents") → likely QUESTION (correct behavior)
- Error/Ollama down → always QUESTION (safer default than losing information)

---

## Degradation Behavior

| Dependency down | Effect |
|-----------------|--------|
| Wonder Engine | Questions return error message to user. Information path unaffected. |
| Watcher | Information messages return "Failed to store". Questions unaffected. |
| Ollama | Intent classification fails → everything treated as question → sent to Wonder Engine |
| Ollama + Wonder Engine | All messages return error message |

---

## Design Decisions

### Why classify intent at all?

The CLAUDE.md for Wonder Engine explains it: "When Robert is entering information, it bypasses
the gates (no point grounding a statement Robert is asserting). When Robert is asking a question,
it goes through all three gates."

The three gates enforce epistemic standards on answers. They make no sense applied to statements.
If Robert says "The foundation pour is March 15," Wonder Engine would try to find sources that
confirm or deny that — which is absurd.

### Why Ollama for classification, not a simpler heuristic?

Regex patterns for question detection are notoriously fragile. "Tell me about X" is a question
without a question mark. "Who is responsible for the structural drawings?" ends with a question
mark. "I need to know if the inspection passed." is a question. "The inspection passed." is
information. A 14B model with zero temperature handles these edge cases reliably.

### Why no conversation history?

The bot is a gateway to Wonder Engine, which is stateless. Wonder Engine builds its context
from LOR and Watcher on every query. The bot's job is to route — not to maintain context.
Session context is handled by LOR's session compaction when queries arrive at `/api/query`.

### Why long polling instead of webhooks?

The bot runs on a local Windows machine without a public IP. Long polling requires no
external infrastructure — it works from behind a NAT. For a single-user bot, the polling
latency (~1–2 seconds) is acceptable.

### Why single-file design?

335 lines covering the entire bot. There is no need to split a bot this size. If the bot
grows (multiple backends, multiple users, persistent storage), decomposition becomes worthwhile.
At the current size, a single file is easier to maintain than a package.
