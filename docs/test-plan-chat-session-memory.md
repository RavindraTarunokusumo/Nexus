# Test Plan: Chat Session Memory

This plan covers the session memory feature: `ChatSession` / `ChatMessage` DB models, the
`app/intelligence/session_memory.py` helpers, and all endpoints added to
`app/api/routes_chat.py`.  Tests are grouped by scope.  Items marked **[EXISTS]** are
already covered in `tests/test_chat_sessions.py`; items marked **[GAP]** are not yet written.

---

## Unit Tests

These test pure functions in isolation with no DB or HTTP layer.

### `_to_psycopg_url`

| # | Name | What it tests | Expected result |
|---|------|---------------|-----------------|
| U1 | asyncpg dialect stripped | Input `postgresql+asyncpg://user:pass@host/db` | Returns `postgresql://user:pass@host/db` **[EXISTS — implied by integration; GAP as explicit unit test]** |
| U2 | psycopg2 dialect stripped | Input `postgresql+psycopg2://user:pass@host/db` | Returns `postgresql://user:pass@host/db` **[GAP]** |
| U3 | plain URL unchanged | Input `postgresql://user:pass@host/db` | Returns the same string unmodified **[GAP]** |
| U4 | unrecognised scheme unchanged | Input `sqlite:///dev.db` | Returns the string unmodified (no crash) **[GAP]** |

### `_derive_title`

| # | Name | What it tests | Expected result |
|---|------|---------------|-----------------|
| U5 | Short string — no truncation | `"Hello"` (5 chars) | Returns `"Hello"` exactly **[GAP]** |
| U6 | Exactly 60 chars — no truncation | String of exactly 60 non-space chars | Returns the string as-is, no `...` appended **[GAP]** |
| U7 | 61+ chars — truncation with ellipsis | String of 61 chars | Returns first 60 chars + `"..."` **[GAP]** |
| U8 | Whitespace collapsed before measuring | `"  word1   word2  "` | Collapsed before the 60-char window is applied **[GAP]** |
| U9 | Multi-word string under limit | `"What did the latest sources say?"` (32 chars) | Returned verbatim **[EXISTS — asserted via API round-trip in `test_send_first_message_derives_session_title`; GAP as direct unit test]** |
| U10 | Empty string | `""` | Returns `""` without error **[GAP]** |

### `SessionPatchRequest` validation

| # | Name | What it tests | Expected result |
|---|------|---------------|-----------------|
| U11 | Blank title rejected | `{"title": "   "}` | Pydantic `ValueError` raised **[GAP]** |
| U12 | Invalid status rejected | `{"status": "deleted"}` | Pydantic `ValueError` raised **[GAP]** |
| U13 | Valid status values accepted | `"active"` and `"archived"` | No validation error **[GAP]** |

---

## Integration Tests (API)

These run against the full FastAPI app backed by the test database.  All currently live in
`tests/test_chat_sessions.py`.

### Session Creation — `POST /chat/sessions`

| # | Name | What it tests | Expected result |
|---|------|---------------|-----------------|
| I1 | Create with no body | Minimal create call | 201, UUID `id`, `status=active`, `message_count=0`, `last_message_preview=null` **[EXISTS]** |
| I2 | Create with explicit title | `{"title": "My session"}` | 201, `title` echoed back **[EXISTS]** |
| I3 | Title at max length (120 chars) | Title exactly 120 chars | 201 accepted **[GAP]** |
| I4 | Title exceeding max length | Title of 121 chars | 422 Unprocessable Entity **[GAP]** |

### Session Listing — `GET /chat/sessions`

| # | Name | What it tests | Expected result |
|---|------|---------------|-----------------|
| I5 | Empty list | No sessions created | 200 with `[]` **[EXISTS]** |
| I6 | Default status filter is active | Two active sessions created | Both appear in response **[EXISTS]** |
| I7 | Status filter separates active from archived | One archived, one active | Archived absent from `?status=active`; present in `?status=archived` **[EXISTS]** |
| I8 | `limit` parameter respected | 5 sessions created, `?limit=3` | Returns exactly 3 sessions **[GAP]** |
| I9 | `offset` parameter respected | 5 sessions created, `?limit=2&offset=2` | Returns sessions 3 and 4 (by insertion order) **[GAP]** |
| I10 | `limit` boundary: min=1 | `?limit=0` | 422 **[GAP]** |
| I11 | `limit` boundary: max=100 | `?limit=101` | 422 **[GAP]** |
| I12 | `offset` boundary: negative | `?offset=-1` | 422 **[GAP]** |
| I13 | Ordered by `updated_at` desc | Two sessions, second updated later | Second session appears first **[GAP]** |

### Session Detail — `GET /chat/sessions/{session_id}`

| # | Name | What it tests | Expected result |
|---|------|---------------|-----------------|
| I14 | Not found | Random UUID | 404 **[EXISTS]** |
| I15 | Empty transcript | New session, no messages | 200, `messages=[]` **[EXISTS]** |
| I16 | Messages ordered ascending | Two send-message calls | Messages appear in `created_at ASC` order **[GAP]** |
| I17 | Message fields complete | One send (mocked) | `role`, `content`, `run_id`, `citations`, `retrieved_context_count`, `tokens_used`, `cost_estimate_usd` all present on assistant message **[GAP]** |

### Session Update — `PATCH /chat/sessions/{session_id}`

| # | Name | What it tests | Expected result |
|---|------|---------------|-----------------|
| I18 | Rename | `{"title": "New name"}` | 200, `title` updated **[EXISTS]** |
| I19 | Archive sets `archived_at` | `{"status": "archived"}` | 200, `status=archived`, `archived_at` not null **[EXISTS]** |
| I20 | Not found | Random UUID | 404 **[EXISTS]** |
| I21 | Unarchive clears `archived_at` | Archive then patch `{"status": "active"}` | `archived_at` is null, `status=active` **[GAP]** |
| I22 | Rename + archive in one call | `{"title": "x", "status": "archived"}` | Both fields applied atomically **[GAP]** |
| I23 | Blank title rejected | `{"title": "  "}` | 422 **[GAP]** |
| I24 | Invalid status rejected | `{"status": "deleted"}` | 422 **[GAP]** |

### Send Message — `POST /chat/sessions/{session_id}/messages`

| # | Name | What it tests | Expected result |
|---|------|---------------|-----------------|
| I25 | Session not found | Random UUID | 404 **[EXISTS]** |
| I26 | Archived session pre-flight rejected | Archive then send | 409 **[EXISTS]** |
| I27 | Happy path: user + assistant rows persisted | Mock `run_session_turn` success | 200, `user_message.role=user`, `assistant_message.role=assistant`, content matches **[EXISTS]** |
| I28 | `run_session_turn` raises → 503 | Mock raises `RuntimeError` | 503 **[EXISTS]** |
| I29 | Failure leaves transcript empty | Mock raises, then GET transcript | `messages=[]` — no partial write **[EXISTS]** |
| I30 | Result has `error` field → 503 | Mock returns `{"error": "boom"}` | 503, no messages persisted **[GAP]** |
| I31 | Title derived from first message | New untitled session, first send | Session title = first 60 chars of content **[EXISTS]** |
| I32 | Title not overwritten by second message | Title set on first send, second send | Title unchanged after second message **[GAP]** |
| I33 | Explicit title not overwritten | Session created with title, then message | Title stays as set at creation **[GAP]** |
| I34 | `message_count` updates after each send | Two sends (mocked) | `message_count=4` (2 user + 2 assistant) **[EXISTS]** |
| I35 | `last_message_preview` reflects latest content | One send (mocked) | Preview equals assistant message content (most recent) **[GAP]** |
| I36 | `top_k` passed through to `run_session_turn` | Send with `{"top_k": 5}` | `run_session_turn` called with `top_k=5` **[GAP]** |
| I37 | Race condition: archived between pre-flight and write | Patch session to archived inside monkeypatched turn | Inner re-check returns 409, no messages written **[GAP]** |
| I38 | Blank content rejected | `{"content": "  "}` | 422 **[GAP]** |
| I39 | Content over 2048 chars rejected | Content of 2049 chars | 422 **[GAP]** |

### Backward Compatibility — `POST /chat/answer`

| # | Name | What it tests | Expected result |
|---|------|---------------|-----------------|
| I40 | No spans → insufficient-evidence answer | Empty DB, real graph | 200, `answer` contains "evidence" **[EXISTS]** |
| I41 | Response shape unchanged | Any call | All fields: `answer`, `citations`, `retrieved_context_count`, `run_id`, `tokens_used`, `cost_estimate_usd` **[GAP]** |
| I42 | LLMError → 503 | Mock `run_chat_with_context` to raise `LLMError` | 503 **[GAP]** |

---

## End-to-End / Manual Smoke Tests

Run against a fully wired local instance (real Postgres, real OpenRouter key).

| # | Name | Steps | Expected result |
|---|------|-------|-----------------|
| E1 | Full conversation round-trip | Create session → send "What changed?" → send follow-up "Summarise that" → GET detail | Both turns persisted; second message shares the same `thread_id`; LangGraph has prior context available |
| E2 | Title auto-set from first message | Create untitled session → send long message (>60 chars) → GET session | Title is first 60 chars + `"..."` |
| E3 | LangGraph thread continuity | Send three messages in one session; GET detail | Six rows (3 user, 3 assistant) in ascending order; assistant responses show awareness of prior turns |
| E4 | Concurrent sends to same session | Two simultaneous POST /messages requests to same session | Both 200; four rows persisted; no duplicate or missing rows |
| E5 | Checkpointer connectivity | Start with DB reachable, send message; stop DB mid-turn (simulate) | 503 returned; transcript unchanged |
| E6 | Pagination across many sessions | Create 35 active sessions; GET with default limit=30 | 30 returned; GET with `?offset=30` returns remaining 5 |
| E7 | Archive workflow end-to-end | Create → send two messages → archive → attempt third send | Third send returns 409; GET shows archived status and prior messages intact |
| E8 | `POST /chat/answer` alongside sessions | Use both endpoints in same test run | Each works independently; no cross-contamination of state |

---

## Coverage Summary

| Area | Covered | Gaps |
|------|---------|------|
| `_to_psycopg_url` | 0 of 4 | U1–U4 |
| `_derive_title` | 1 of 6 (via API) | U5–U10 as direct unit tests |
| Schema validation | 0 of 5 | U11–U13, I3–I4 |
| `POST /chat/sessions` | 2 of 4 | I3–I4 |
| `GET /chat/sessions` | 3 of 9 | I8–I13 |
| `GET /chat/sessions/{id}` | 2 of 4 | I16–I17 |
| `PATCH /chat/sessions/{id}` | 3 of 7 | I21–I24 |
| `POST /messages` | 7 of 15 | I30–I39 (excl. already-covered) |
| `POST /chat/answer` (compat) | 1 of 3 | I41–I42 |
| End-to-end / manual | 0 of 8 | E1–E8 |

**Highest-priority gaps** (likely to catch real bugs):

1. **I30** — `error` field in result does not persist messages (code path exists, not tested)
2. **I37** — Race condition re-check inside the write transaction (code exists, not tested)
3. **U1–U4** — `_to_psycopg_url` has no unit tests at all
4. **I16** — Message ordering guarantee (ASC by `created_at`)
5. **E3** — LangGraph thread continuity (the core value-add of session memory)
6. **I21** — Unarchive clears `archived_at` (regression risk on future status changes)
