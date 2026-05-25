# Web UI + Chat Session Memory

**Branch:** `claude/workflow-implementation-OZJ8O`
**PR:** [#13](https://github.com/RavindraTarunokusumo/Nexus/pull/13)
**Merge commit:** [pending]
**Merged at:** [pending]
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
