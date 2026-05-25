# Security Review — Chat Session Memory

**Date:** 2026-05-25
**Scope:** `app/api/routes_chat.py`, `app/intelligence/session_memory.py`, `app/db/models.py` (ChatSession/ChatMessage), `app/db/migrations/versions/0004_chat_sessions.py`
**Deployment context:** Private VPS, no authentication currently in place.

---

## Summary Table

| # | Finding | Severity | Status |
|---|---------|----------|--------|
| 1 | Multi-turn prompt injection via checkpointer history | **High** | Deferred — tracked in TODO |
| 2 | Exception/DSN leakage in 503 response body | **High** | **Fixed in this session** |
| 3 | Unvalidated `status` query param in list endpoint | **Medium** | **Fixed in this session** |
| 4 | No rate limiting, no session/message caps, `setup()` per request | **Medium** | Deferred — tracked in TODO |
| 5 | Cross-session access — list endpoint exposes all IDs without auth | **Medium** | Deferred — existing no-auth TODO |
| 6 | `_derive_title` stores unsanitized user input (stored XSS vector) | Low | Deferred — frontend must HTML-escape |
| 7 | Cascade delete removes messages with no audit trail | Low | Deferred — no delete endpoint yet |
| 8 | `checkpointer.setup()` called on every request | Low | Deferred — tracked in TODO |
| 9 | `last_message_preview` returns full content with no truncation | Low | **Fixed in this session** (truncated to 150 chars) |
| 10 | `role` column has no CHECK constraint | Info | Deferred — tracked in TODO |

---

## Findings

### Finding 1 — Multi-turn Prompt Injection via Checkpointer History (High, Deferred)

`run_session_turn` uses `AsyncPostgresSaver` keyed to `session_id` as the LangGraph `thread_id`. On every turn the full prior conversation (all `HumanMessage` and `AIMessage` objects) is restored from the checkpointer and passed to the LLM with no role-tagging, no wrapping, and no separation between trusted and untrusted content.

An attacker can craft a first message that permanently poisons the thread for its lifetime. The injection is stored in the checkpointer and replayed verbatim on every subsequent turn.

**Mitigation:** Wrap user messages with an explicit system-level untrusted-input marker in the agent prompt. Consider a configurable context window limit to cap injection surface. Plan a guardrail pass (Llama Guard or equivalent) once auth is in place.

---

### Finding 2 — Exception/DSN Leakage in 503 Responses (High, Fixed)

`routes_chat.py` was forwarding raw exception strings to HTTP clients via `detail=f"... {exc}"`. If the psycopg3 driver fails to connect, the exception message includes the full DSN (host, port, user, password). **Fixed:** all 503 `detail` fields now use static strings; full exception is logged server-side only.

---

### Finding 3 — Unvalidated `status` Query Parameter (Medium, Fixed)

`GET /chat/sessions` accepted an arbitrary string for `status_filter`. **Fixed:** `pattern="^(active|archived)$"` added to the `Query(...)` declaration; invalid values now return 422.

---

### Finding 4 — No Rate Limiting / Session or Message Caps (Medium, Deferred)

No rate limiting anywhere. Any client can create unlimited sessions and messages, exhausting DB storage and OpenRouter API quota. Additionally `checkpointer.setup()` issues DDL on every request (see Finding 8).

**Mitigation:** Add per-IP rate limiting (e.g., `slowapi`), a `MAX_SESSIONS` and `MAX_MESSAGES_PER_SESSION` guard, and move `checkpointer.setup()` to the application lifespan handler.

---

### Finding 5 — Cross-Session Access Without Auth (Medium, Deferred)

`GET /chat/sessions` returns all session IDs server-wide. Combined with no auth, any client can enumerate sessions and access full transcripts. This worsens the existing no-auth gap (open TODO). **Mitigation:** Minimum viable fix is a pre-shared `X-API-Key` header check before shipping the list endpoint externally.

---

### Finding 6 — `_derive_title` Stores Unsanitized User Input (Low, Deferred)

`_derive_title` performs only whitespace normalization. The result is stored and returned in every `SessionSummary`. A frontend rendering titles without HTML-escaping is vulnerable to stored XSS. **Mitigation:** Frontend must HTML-escape the `title` field. Backend should strip non-printable characters.

---

### Finding 7 — Cascade Delete Removes Audit Trail (Low, Deferred)

`ON DELETE CASCADE` on `chat_messages` permanently destroys all messages when a session is deleted. No delete endpoint exists yet, but the schema allows it. **Mitigation:** Consider soft-deletion or `ON DELETE RESTRICT` with an explicit archival step.

---

### Finding 8 — `checkpointer.setup()` Called on Every Request (Low, Deferred)

`session_memory.py` calls `await checkpointer.setup()` inside `run_session_turn`, issuing `CREATE TABLE IF NOT EXISTS` DDL on every message. **Mitigation:** Move `setup()` to the application lifespan handler and cache the connection.

---

### Finding 9 — `last_message_preview` Unbounded (Low, Fixed)

`_build_session_summary` was returning the full raw message content as `last_message_preview`, up to 2048 chars. **Fixed:** Truncated to 150 characters server-side.

---

### Finding 10 — `role` Column Has No CHECK Constraint (Info, Deferred)

`ChatMessage.role` accepts any string. No current write path allows arbitrary roles, but no DB-level guard exists. **Mitigation:** Add `CHECK (role IN ('user', 'assistant'))` in a future migration.

---

## Immediate Action Items (before any public exposure)

1. ~~Fix Finding 2~~ ✅ Done
2. ~~Fix Finding 3~~ ✅ Done
3. ~~Fix Finding 9~~ ✅ Done
4. **Finding 5** — Add pre-shared API key guard to all session endpoints before exposing publicly
5. **Finding 4** — Add rate limiting and move `checkpointer.setup()` to startup
6. **Finding 1** — Document and plan guardrail pass for prompt injection
