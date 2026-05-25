# Web UI + Chat Session Memory

**Branch:** `claude/workflow-implementation-OZJ8O`
**PR:** [#13](https://github.com/RavindraTarunokusumo/Nexus/pull/13)
**Merge commit:** `dc06b13bef52c8024b3f834f40eada7656a8221b`
**Merged at:** 2026-05-25
**Merged by:** RavindraTarunokusumo

## Summary

Implemented two paired specs: persistent multi-turn chat sessions (backend) and a React web UI (frontend) for the Nexus grounded chatbot.

**Backend**: Added `chat_sessions` and `chat_messages` tables (migration 0004), a LangGraph memory controller backed by `AsyncPostgresSaver` (Postgres checkpointer), five chat session API endpoints, and CORS middleware. The `POST /chat/answer` single-turn endpoint remains backward-compatible.

**Frontend**: Created a `web/` Vite + React 19 + TypeScript + Tailwind CSS 4 workspace with a two-pane layout (session sidebar + chat panel), typed API client, `useSessions` / `useChatSession` hooks, and six components including citation display.

## Tasks Completed

**Phase A — Backend: Chat Session Memory**
- [x] **A1: pyproject.toml** — added `langchain>=0.3.0`, `langchain-openai>=0.2.0`, `langgraph-checkpoint-postgres>=2.0.0`, `psycopg[binary,pool]>=3.1.0` (commit: `eaa4dfa`)
- [x] **A2: ORM models + migration 0004** — `ChatSession`, `ChatMessage` models; migration with status/updated_at indexes and session_id+created_at compound index (commit: `356293d`)
- [x] **A3: session_memory.py** — `_MemoryState` TypedDict with `add_messages` reducer; `make_memory_graph` factory wrapping the grounded chat graph; `invoke_with_memory` entry point; conversation history injected as context (commit: `570b122`)
- [x] **A4: routes_chat_sessions.py** — `POST /chat/sessions` (201), `GET /chat/sessions` (status/limit/offset), `GET /chat/sessions/{id}` (with messages), `POST /chat/sessions/{id}/messages` (409 on archived, 503 on missing memory graph), `PATCH /chat/sessions/{id}` (title/status/archived_at) (commit: `4c252f5`)
- [x] **A5: app/main.py** — CORS middleware scoped to Vite dev origins; psycopg `AsyncConnectionPool` + `AsyncPostgresSaver` lifecycle with graceful degradation; chat session router (commit: `33e5418`)
- [x] **A6: tests/test_chat_sessions.py** — 15 integration tests covering CRUD, send message, title derivation (60-char truncation), 409/503 error cases, insufficient-evidence persistence (commit: `abc64fe`)

**Phase B — Frontend: React Web UI**
- [x] **B1–B6: web/ workspace** — Vite + React 19 + TypeScript + Tailwind CSS 4 scaffold; `api/client.ts` with `ApiError` normalization; `useSessions` / `useChatSession` hooks; `SessionSidebar`, `ChatPanel`, `MessageList`, `MessageBubble`, `CitationList`, `Composer` components; 23 Vitest + Testing Library tests (commit: `101ee33`)

## Test Results

- Backend: 226 passed (4 pre-existing embedder failures in network-restricted remote env)
- Frontend: 23 passed, clean TypeScript build

## Post-Merge Review Fixes (Copilot Code Review)

Six findings addressed in commits `a691fcd`–`9e8e9b4`:

- `a691fcd` — `Composer.tsx`: replaced `React.KeyboardEvent` with named `type KeyboardEvent` import (TypeScript namespace error under `jsx:react-jsx`)
- `0b942ed` — `App.tsx`: stashed first message in `pendingMessageRef`; `useEffect` dispatches it after `activeId` is set by session creation
- `fa48717` — `useSessions.ts`: `setError(null)` at start of `load()` to clear stale errors on success
- `db86e9e` — `client.test.ts`: `fetchMock.mockReset()` in `beforeEach` to prevent call-history leakage
- `312fa08` — `routes_chat_sessions.py`: replaced N+1 `_session_summary` calls in `list_sessions` with a single correlated-subquery SELECT
- `e7fc7ab` — `ChatPanel.tsx`: disabled `Composer` when `loading || !detail` to prevent dropped messages during session fetch
- `9e8e9b4` — Docs: updated `architecture.md`, `database.md`, `patterns.md` for all Phase 3 additions

---

## Parallel Session — PR #12

**Branch:** `claude/web-ui-chat-specs-fUwKz`
**PR:** [#12](https://github.com/RavindraTarunokusumo/Nexus/pull/12)
**Merge commit:** `000e266e4404b6e616d9b96626c7d7efb7278814`
**Merged at:** 2026-05-25

A parallel session implementing the same chat session memory spec independently, contributing additional security hardening, a Copilot code review pass, a test plan doc, and a security review doc.

### Tasks Completed

- [x] Add ChatSession and ChatMessage SQLAlchemy models (d217d24)
- [x] Create Alembic migration 0004_chat_sessions (d217d24)
- [x] Write failing session API tests — 18 tests, monkeypatch approach (bc68825)
- [x] Add LangGraph session memory controller with AsyncPostgresSaver (ff7b743)
- [x] Add session CRUD + messages API routes to routes_chat.py (bab5e4b)
- [x] Update pyproject.toml with new dependencies (bab5e4b)
- [x] Docs: architecture, commands, database updated (437c92e)
- [x] Docs: test-plan-chat-session-memory.md — 42 gaps identified (987c018)
- [x] Security review — fix F2 DSN leakage, F3 status param validation, F9 preview truncation; add security-review-chat-sessions.md (1e20d19)
- [x] Copilot review pass — title blank validator, N+1 query fix, error propagation, test coverage (75938f7)
- [x] Docs: fix /chat/answer curl example field name (3e57b1b)

### Security Findings (3 fixed, 7 deferred to TODO)

Fixed: F2 (DSN leakage in 503), F3 (unvalidated status param), F9 (unbounded preview).
Deferred to Ongoing TODO: F1 (prompt injection), F4 (rate limiting), F5 (API key guard), F6 (XSS in title), F8 (checkpointer.setup per request), F10 (role CHECK constraint).
