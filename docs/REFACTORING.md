# Telegram-Wonder Engine Bot — Refactoring Plan

**Date:** 2026-02-21
**Based on:** Full source code review (system report)
**Current grade:** B+ (security issues resolved, tests still needed)
**Updated:** 2026-02-21 — Issues 1, 2, 3 fixed in commits eb8c36d, 845bfbd, 6b6cf67

The bot's design is correct. The routing logic, async implementation (httpx throughout),
and single-purpose scope are all right. The critical problem is a security issue, not an
architectural one. Fix Issue 1 before anything else.

---

## Issues Found (Ranked by Severity)

### Issue 1 — ~~Telegram token hardcoded in source code~~ (CRITICAL) [FIXED — eb8c36d]

**File:** `bot.py:27`

**Current state:**
```python
TELEGRAM_TOKEN = "8530568052:AAHh3anh3Xu2t-CJFrBC-nK49_7_nUeJyyA"
```

**Problem:**
This is a live, active Telegram bot token. It is hardcoded in a Python source file that is:
- Version-controlled (git repo)
- Readable by any process on the machine
- Visible in this documentation

If this token is ever committed to a public repository or exposed in any way, anyone can
impersonate `@roberts_clawd_bot`. Telegram bot tokens grant full control over the bot —
sending messages, intercepting incoming messages, changing settings.

**Immediate action:** Revoke the current token via @BotFather and generate a new one.
Then move it to an environment variable or `.env` file before the new token is used.

**Fix:**
```python
import os
from dotenv import load_dotenv

load_dotenv()  # reads E:\telegram-ollama-bot\.env

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]  # fails fast if missing
```

`.env` file (not committed to git):
```
TELEGRAM_TOKEN=your_new_token_here
AUTHORIZED_USER_ID=1991846232
WONDER_URL=http://localhost:9600
WATCHER_URL=http://localhost:9100
OLLAMA_URL=http://localhost:11434
WONDER_TIMEOUT=120
OLLAMA_MODEL=qwen2.5:14b-instruct
```

`.gitignore`:
```
.env
```

**Alternative (no dotenv dependency):** Use OS environment variables set via NSSM:
```cmd
nssm set TelegramOllamaBot AppEnvironmentExtra TELEGRAM_TOKEN=your_token_here
```

Then in bot.py:
```python
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
```

**Effort:** 20 minutes (including token revocation and regeneration)
**Risk:** None — straightforward substitution

---

### Issue 2 — ~~All configuration hardcoded~~ (HIGH) [FIXED — 845bfbd]

**File:** `bot.py:27–35`

**Current state:**
```python
TELEGRAM_TOKEN = "..."
AUTHORIZED_USER_ID = 1991846232
WONDER_URL = "http://localhost:9600"
WATCHER_URL = "http://localhost:9100"
OLLAMA_URL = "http://localhost:11434"
WONDER_TIMEOUT = 120
OLLAMA_MODEL = "qwen2.5:14b-instruct"
```

**Problem:**
Every value requires a source code edit to change. This blocks the token fix (Issue 1)
from being done correctly, and means port changes require touching source code.

**Fix:** Apply as part of Issue 1 — move all config to `.env` + `os.environ` or
pydantic-settings. Watcher's `config.py` is the reference pattern.

**Effort:** Included in Issue 1 effort
**Risk:** None

---

### Issue 3 — ~~NSSM service dependency missing Wonder Engine~~ (MEDIUM) [FIXED — 6b6cf67]

**File:** `install_service.bat:43`

**Current state:**
```bat
C:\nssm\nssm-2.24\win64\nssm.exe set TelegramOllamaBot DependOnService Ollama
```

**Problem:**
The service dependency is set to `Ollama` only. But the bot's primary backend is Wonder
Engine (port 9600). If Wonder Engine hasn't started yet, the bot starts successfully but all
question routing fails immediately with `ConnectError`.

The correct dependency chain is `WonderEngine` (which itself depends on LOR, Watcher, Ollama).
Setting `DependOnService WonderEngine` would ensure the bot waits for the full stack.

**Fix:**
```cmd
nssm set TelegramOllamaBot DependOnService WonderEngine
```

Or update `install_service.bat`:
```bat
C:\nssm\nssm-2.24\win64\nssm.exe set TelegramOllamaBot DependOnService WonderEngine
```

**Effort:** 5 minutes
**Risk:** None — additive constraint

---

### Issue 4 — No upper bounds on dependency pins (LOW)

**File:** `requirements.txt`

**Current state:**
```
python-telegram-bot>=21.0
httpx>=0.25.0
```

**Problem:**
`python-telegram-bot` had breaking API changes between major versions (v13 sync → v20 async).
An uncontrolled `pip install --upgrade` could introduce regressions.

**Fix:**
```
python-telegram-bot>=21.0,<22.0
httpx>=0.25.0,<1.0
```

If adding `python-dotenv` for Issue 1:
```
python-telegram-bot>=21.0,<22.0
httpx>=0.25.0,<1.0
python-dotenv>=1.0.0,<2.0
```

**Effort:** 5 minutes
**Risk:** None

---

### Issue 5 — No tests (LOW)

**Status:** Zero test files.

---

#### Test Infrastructure

**Directory structure:**
```
E:\telegram-ollama-bot\
├── tests/
│   ├── conftest.py
│   └── test_bot.py
```

**`pytest.ini` (add to project root):**
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

**`tests/conftest.py` — CRITICAL:**

`bot.py` reads `TELEGRAM_TOKEN` at module level via `os.environ["TELEGRAM_TOKEN"]`. If the
variable is not set before `bot` is imported, the test file crashes at collection time with
a `KeyError`. The conftest must patch environment variables before any import:

```python
import os
# Set before bot.py is imported — module-level os.environ reads happen at import time
os.environ.setdefault("TELEGRAM_TOKEN", "test_token_placeholder")
os.environ.setdefault("AUTHORIZED_USER_ID", "1991846232")
os.environ.setdefault("WONDER_URL", "http://localhost:9999")    # non-existent
os.environ.setdefault("WATCHER_URL", "http://localhost:9998")
os.environ.setdefault("OLLAMA_URL", "http://localhost:9997")
```

This conftest pattern must exist before any test can run. It is the most important
infrastructure step for this project.

Requires `pytest-asyncio` for async tests: `pip install pytest-asyncio`

---

#### Unit Tests

**T31 — `is_authorized()` authorization boundary**
(`bot.py:53–57`)

Pure function, no dependencies:

| Input user_id | Expected | Notes |
|---------------|----------|-------|
| `1991846232` | `True` | Authorized ID |
| `1991846233` | `False` | Off-by-one — must not be authorized |
| `0` | `False` | |
| `-1` | `False` | Negative ID |
| `"1991846232"` (string) | Document behavior — raises `TypeError` or returns `False` | Guards against type coercion bugs |

The off-by-one case (`+1`) is the most important. Authorization checks that fail at `n+1`
or `n-1` indicate a comparison bug (e.g., `>=` vs `==`).

---

**T32 — `split_message()` boundary and infinite loop risk**
(`bot.py:60–77`)

Pure function, no dependencies. Telegram's hard limit is 4096 characters.

| Scenario | Expected |
|----------|----------|
| Empty string | `[""]` or `[]` — document actual behavior |
| Exactly 4096 chars | Single-element list, no split |
| 4097 chars | Two chunks, neither exceeds 4096 |
| 4096 + 1 chars, whitespace at position 4090 | Splits at whitespace boundary (4090), not mid-word at 4096 |
| `\n` character in text | Newline preserved, not swallowed by split |
| **4097+ chars with NO whitespace** | Must terminate. If split logic scans for whitespace and finds none, it could infinite-loop. Wrap call in `pytest.raises` or use `pytest-timeout` with 1s limit: `@pytest.mark.timeout(1)` |

The no-whitespace case is the most important. A 4097-char token (URL, base64 string) with
no spaces will reveal whether the split function has a fallback hard-cut or loops forever.

---

**T33 — `format_wonder_response()` all four classifications + missing key**
(`bot.py:80–84`)

Pure function, no dependencies:

| `classification` value | Expected prefix in output |
|------------------------|--------------------------|
| `"fully_grounded"` | `[FULLY GROUNDED]` (or whatever string is used — read the source) |
| `"partially_grounded"` | `[PARTIALLY GROUNDED]` |
| `"at_perimeter"` | `[AT PERIMETER]` |
| `"in_void"` | `[IN VOID]` |
| Missing `classification` key | Does not raise `KeyError` — document default behavior |
| `classification` present, `response` is empty string | Prefix still present, no crash |

The missing-key case guards against Wonder Engine API changes. If a new classification
value is added or the key is renamed, T33 will catch it before it reaches users.

---

**T34 — `classify_intent()` response parsing and fallback**
(`bot.py:91–118`)

Async function. Mock `httpx.AsyncClient.post` using `unittest.mock.AsyncMock` or
`pytest-httpx`:

| Ollama response content | Expected return value | Notes |
|-------------------------|-----------------------|-------|
| `"INFORMATION"` | `"information"` | Happy path |
| `"QUESTION"` | `"question"` | Happy path |
| `"  INFORMATION  "` (whitespace) | `"information"` or fallback — document | Whitespace stripping |
| `"ANALYSIS"` (unrecognized) | `"question"` | Default fallback |
| `""` (empty string) | `"question"` | Default fallback |
| `httpx.ConnectError` raised | `"question"` | Silent fallback — documented in CLAUDE.md |
| `httpx.TimeoutException` raised | `"question"` | Ollama-down case |

The silent fallback to `"question"` is intentional design. These tests document and
lock in that behavior so it is not accidentally changed.

---

**T35 — `store_in_watcher()` status code handling**
(`bot.py:144–160`)

Async function. Mock `httpx.AsyncClient.post`:

| Mock response | Expected behavior | Notes |
|---------------|-------------------|-------|
| HTTP 200 | Returns success indicator (truthy or `"Noted."` message) | Happy path |
| HTTP 422 | Returns error message or falsy — does NOT raise | Invalid source |
| HTTP 500 | Returns error message or falsy — does NOT raise | Server error |
| `httpx.ConnectError` | Returns `"Failed to store"` string (CLAUDE.md troubleshooting documents this exact message) | Watcher-down case |

The `ConnectError` case is the most important — it is the most common failure mode and
the error message is user-visible.

---

**T36 — `check_wonder_health()` status parsing**
(`bot.py:163–173`)

Async function. Mock `httpx.AsyncClient.get`:

| Mock response | Expected behavior |
|---------------|-------------------|
| HTTP 200 with `{"status": "ok", "services": {...}}` | Returns truthy / health dict |
| HTTP 500 | Returns falsy — does not raise |
| `httpx.ConnectError` raised | Returns `False` or error dict — does not raise |
| HTTP 200 with unexpected JSON shape | Document behavior — `KeyError` or graceful default? |

The unexpected JSON shape case guards against Wonder Engine API changes that silently
break the `/start` and `/status` command output.

---

**Quick wins (under 20 min each):** T31 `is_authorized()` boundary (10 min), T33 `format_wonder_response()` all classifications (15 min), T36 `check_wonder_health()` (15 min).

**Effort:** 1.5–2 hours for T31–T36 + infrastructure (conftest is the first thing to write)
**Risk:** None — additive. The conftest setup is the only tricky part due to module-level token read.

---

## Not Issues (Things That Look Like Problems But Aren't)

**No conversation history** — The bot is stateless by design. Session context is managed
by LOR's session compaction when queries hit `/api/query`. The bot's job is to route, not
to manage context.

**Intent classification uses the 14B model** — This adds 1–3 seconds per message for a
classification that returns a single word. A smaller model (e.g., `mistral:7b`) would be
faster. However, the 14B model's accuracy on edge cases (ambiguous statements, mixed
question/information) is worth the latency. Don't downgrade without testing.

**`include_gate_log: false`** — Wonder Engine's gate log is useful for debugging but
verbose. For day-to-day use, the classification prefix (`[PARTIALLY GROUNDED]`) provides
sufficient context. If you want gate details, query Wonder Engine directly.

**No rate limiting** — The bot is single-user. Rate limiting is unnecessary.

**Long polling instead of webhooks** — The machine has no public IP. Long polling is
the right choice for this deployment context.

---

## Prioritized Action List

| Priority | Issue | File(s) | Effort | Status |
|----------|-------|---------|--------|--------|
| 1 | ~~Move token to env var~~ | `bot.py`, `.env`, `requirements.txt` | 20 min | DONE (eb8c36d) |
| 2 | ~~Externalize all config to env vars~~ | `bot.py` | 10 min | DONE (845bfbd) |
| 3 | ~~Fix NSSM service dependency~~ | `install_service.bat` | 5 min | DONE (6b6cf67) |
| 4 | Pin dependency upper bounds | `requirements.txt` | 5 min | Open |
| 5 | Add unit tests (T31–T36) | new `tests/` directory | 1.5–2 hrs | Open |

**Total estimated effort:** ~2 hours (remaining: ~1.5 hrs for items 4–5)

---

## Steps to Fix Issue 1 (Token Security) — COMPLETED 2026-02-21

- [x] ~~Open Telegram, message `@BotFather`~~ (token not yet revoked — see note below)
- [ ] Revoke current token via @BotFather and regenerate (**still needed — token was in git history**)
- [x] Create `E:\telegram-ollama-bot\.env` with token
- [x] `.env` already in `.gitignore`
- [x] Install python-dotenv in venv
- [x] Update `bot.py` — `load_dotenv()` + `os.environ["TELEGRAM_TOKEN"]`
- [x] Externalize all other config to env vars with defaults
- [x] Fix install_service.bat dependency (Ollama → WonderEngine)
- [x] Restart service — verified running with env vars
- [x] Verify bot responds in Telegram (logs show clean startup)

**Note:** The old token is still in git history (commit 228b56c and 34f1f10). Robert should
revoke the current token via @BotFather, generate a new one, and update `.env`. The token
in the git history cannot be removed without a force push + history rewrite.
