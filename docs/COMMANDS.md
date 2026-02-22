# Telegram-Wonder Engine Bot — Command Reference

**Bot:** `@roberts_clawd_bot`
**Access:** Single user — Robert (Telegram ID: 1991846232)

---

## Commands

### /start

Returns Wonder Engine health status, dependency states, and command list.

**Example output:**
```
Wonder Engine ONLINE
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
State a fact -> stored in Watcher automatically
```

If Wonder Engine is degraded (e.g., LOR down):
```
Wonder Engine DEGRADED
Axioms intact: True

Services:
  [!] lor: down
  [+] watcher: up
  [+] ollama: up
```

Note: `status` is `"healthy"` only if LOR and Ollama are both up. Watcher being
down does not degrade Wonder Engine status.

---

### /status

Returns detailed Wonder Engine status including the Three Axioms.

**Example output:**
```
Wonder Engine: healthy
Endpoint: http://localhost:9600
Timeout: 120s

Dependencies:
  lor: up
  watcher: up
  ollama: up

The Three Axioms:
  1. Ground truth exists.
  2. Ground truth is discoverable.
  3. Discovery is relational.
```

---

### /remember \<text\>

Stores text directly in Watcher as a note episode. Bypasses intent classification —
useful when you want to explicitly store something without the bot guessing.

**Usage:**
```
/remember The Olsan structural steel arrives week of March 10
```

**Response (success):**
```
Remembered.
```

**Response (Watcher down):**
```
Failed to store. Is Watcher running?
```

**What gets stored in Watcher:**
```json
{
  "source": "manual",
  "event_type": "note",
  "content": "The Olsan structural steel arrives week of March 10",
  "metadata": {
    "via": "telegram",
    "author": "robert"
  }
}
```

---

### /help

Same output as `/start`. Shows health + command list.

---

## Free Text Messages

Any non-command text is classified and routed automatically.

### Question Path

The bot classifies your message as a question (the default) and routes it through
Wonder Engine's Three Gates.

**Example:**
```
You: What is the minimum slope for a drainage pipe under a slab?

Bot: [PARTIALLY GROUNDED]

GROUNDED: According to the plumbing code documents in LOR, drainage pipes under
slabs require a minimum slope of 1/4 inch per foot (2%)...

BOUNDARY: The specific requirements for cast iron vs PVC under slab appear to vary...

QUESTIONS: What jurisdiction and code year applies to this installation?
```

**Response format:**
```
[CLASSIFICATION]

<Wonder Engine response text>
```

**Classifications you'll see:**
| Classification | Meaning |
|----------------|---------|
| `[FULLY GROUNDED]` | Strong evidence, no gaps |
| `[PARTIALLY GROUNDED]` | Evidence exists but incomplete |
| `[AT PERIMETER]` | Only partial support found |
| `[IN VOID]` | No evidence found in LOR or Watcher |

Long responses are automatically split at newline boundaries if they exceed 4096 characters
(Telegram's message limit).

### Information Path

The bot classifies your message as information and stores it in Watcher directly.

**Example:**
```
You: Finished the rough plumbing inspection at Goatland today, passed with no corrections

Bot: Noted.
```

The text is stored in Watcher as `event_type: "note"` and becomes searchable memory
for future Wonder Engine queries.

**Examples that trigger information routing:**
- "The inspector signed off on the framing"
- "Robert prefers the Keenan spec for foundation waterproofing"
- "Ordered 200 feet of 4-inch ABS for the Olsan slab"
- "Meeting with the structural engineer is Monday at 10am"

**Examples that trigger question routing:**
- "What does the code say about..."
- "How do you calculate..."
- "Tell me about wet vents"
- "Who is responsible for the structural drawings?"

---

## Latency Guide

| Message type | Expected wait |
|-------------|---------------|
| Information → Watcher | 1–3 seconds |
| Question → Wonder Engine (fast path, Gate 1 confirmed) | 10–15 seconds |
| Question → Wonder Engine (boundary, 2 probe cycles) | 30–60 seconds |
| Question → Wonder Engine (insufficient, 3 probe cycles) | 60–90 seconds |
| Intent classification via Ollama | 1–3 seconds (added to above) |

The bot shows a "typing..." indicator while processing. All operations are async —
the bot remains responsive to other commands while a long query runs.

---

## Error Messages

| Error | Cause |
|-------|-------|
| `"Error: Wonder Engine timed out. Gates may be processing a complex query."` | Query exceeded 120s timeout |
| `"Error: Cannot connect to Wonder Engine. Is it running on port 9600?"` | Wonder Engine is down |
| `"Error: Wonder Engine error: ..."` | Other HTTP error from Wonder Engine |
| `"Failed to store. Is Watcher running?"` | Watcher returned an error or is down |
| `"Sorry, this bot is private."` | Unauthorized user ID |

---

## Notes for Robert

- **Sending information?** You can either just state it ("The pour is Friday") or use
  `/remember The pour is Friday`. Both work. `/remember` bypasses classification so it's
  more reliable when Ollama is slow.

- **Gate log?** The bot always requests `include_gate_log: false` from Wonder Engine. If you
  want to see which gate did what, query Wonder Engine directly:
  ```
  curl -X POST http://localhost:9600/query \
    -H "Content-Type: application/json" \
    -d '{"query": "your question", "include_gate_log": true}'
  ```

- **Response too long?** Wonder Engine responses can be detailed. They're split automatically
  but arrive as multiple messages. This is normal.

- **Classification wrong?** If something you intended as information got routed as a question
  (or vice versa), use `/remember` for explicit storage. The intent classifier is reliable
  but not perfect.
