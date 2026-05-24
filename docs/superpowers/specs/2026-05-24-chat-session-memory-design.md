# Chat Session Memory Design

## Goal

Add persistent multi-turn chat sessions to the existing grounded Nexus chatbot so a web UI can create sessions, continue conversations, list previous messages, and show citations for every assistant answer.

This spec pairs with [Chat Web UI Design](2026-05-24-chat-web-ui-design.md). The UI spec depends on the API and data contracts defined here.

## Current State

Nexus currently exposes a single-turn `POST /chat/answer` endpoint implemented by `app/api/routes_chat.py` and `app/intelligence/chat.py`. The graph retrieves embedded spans, loads active claims linked through `claim_evidence`, asks the configured T2 model for a grounded answer, validates citation labels, and returns answer text, citations, run ID, token usage, and estimated cost.

The current design intentionally has no chat history, no session IDs, no persisted user or assistant messages, and no web UI.

## Source Guidance

The LangChain short-term memory documentation defines a thread as the unit for remembering interactions in one conversation. LangChain agents persist short-term memory through a checkpointer, and invocations must pass a configurable `thread_id`. For production persistence, the docs recommend a database-backed checkpointer such as `langgraph-checkpoint-postgres`.

References:

- LangChain overview: https://docs.langchain.com/oss/python/langchain/overview
- LangChain short-term memory: https://docs.langchain.com/oss/python/langchain/short-term-memory
- LangGraph persistence/checkpointers: https://docs.langchain.com/oss/python/langgraph/persistence

## Considered Approaches

### Recommended: LangChain Memory Controller Plus App Tables

Use a LangChain agent with a Postgres checkpointer for thread-level short-term memory, and add app-owned `chat_sessions` and `chat_messages` tables for UI display and audit. The LangChain thread ID is the Nexus `chat_sessions.id`.

This keeps memory behavior aligned with LangChain while avoiding direct UI dependence on LangGraph checkpoint internals. It also lets the existing grounded chat graph remain the source of citation-safe answers.

### Alternative: App Tables Only

Store all messages in Nexus tables and manually inject recent turns into the existing chat prompt.

This is simpler operationally but does not satisfy the request to use LangChain for session memory, and it would recreate memory logic that LangChain already provides.

### Alternative: Checkpointer Only

Use only LangChain checkpoint tables and query them for the UI.

This reduces schema work but couples product features to persistence internals that are optimized for graph state, not UI list/detail views. It also makes message-level metadata, citations, run IDs, and costs harder to query.

## Decision

Implement session memory as a small orchestration layer around the existing grounded chat graph:

1. Nexus owns session metadata and displayable message rows.
2. LangChain owns short-term conversation memory through a Postgres checkpointer.
3. The LangChain `thread_id` equals the Nexus `chat_session.id`.
4. The existing hybrid chat graph remains responsible for grounded retrieval, citation validation, model token tracking, and insufficient-evidence fallback.
5. The memory controller may use conversation history to interpret follow-up questions, but factual answers must still come from retrieved Nexus corpus context and validated citations.

## Scope

Included:

- Persistent chat sessions.
- Persistent user and assistant message rows.
- LangChain short-term memory keyed by session ID.
- API endpoints for the web UI to create, list, open, archive, and continue sessions.
- Citation, token, cost, and run metadata on assistant messages.
- Backward-compatible retention of `POST /chat/answer` for CLI and single-turn callers.

Not included:

- User accounts, auth, sharing, or multi-tenant access control.
- Streaming responses.
- Long-term memory across sessions or user preference learning.
- Editing messages, branching conversations, or regenerated answers.
- Frontend implementation; see the paired UI spec.

## Architecture

Add a new session layer alongside the current single-turn chat route:

```text
React UI
-> FastAPI chat session routes
-> ChatSessionService
-> LangChain memory controller, thread_id = chat_session.id
-> existing make_chat_graph/run_chat_with_context
-> app-owned chat_messages rows for UI and audit
```

The memory controller should be implemented in a focused module such as `app/intelligence/session_memory.py`. It should create or receive a LangChain agent configured with a Postgres-backed checkpointer. The agent receives the user message and the prior thread state, resolves follow-up references when needed, and calls a single internal tool that runs the existing grounded chat graph.

The internal tool should accept a standalone question and return:

- answer text
- validated citations
- run ID
- token usage
- cost estimate
- retrieved context count

The agent prompt must state that chat history is only for interpreting the current user request. It must not allow history to create factual claims that are absent from retrieved Nexus evidence.

## Dependencies

Add Python dependencies during implementation:

- `langchain`
- `langchain-openai` if the LangChain agent calls OpenRouter through an OpenAI-compatible chat model.
- `langgraph-checkpoint-postgres`
- `psycopg[binary,pool]` if required by the Postgres checkpointer.

The existing project already depends on `langgraph`. The implementation should verify exact package constraints against the installed LangChain version at implementation time.

## Persistence Model

Add an Alembic migration and SQLAlchemy models for app-owned chat records.

### `chat_sessions`

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key; also used as LangChain `thread_id` |
| title | TEXT | Nullable until first user message; derived from the first message |
| status | TEXT | `active` or `archived`; default `active` |
| created_at | TIMESTAMPTZ | Auto-set |
| updated_at | TIMESTAMPTZ | Updated whenever a message is appended |
| archived_at | TIMESTAMPTZ | Nullable |

Indexes:

- `status`
- `updated_at DESC`

### `chat_messages`

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| session_id | UUID | FK to `chat_sessions.id` with cascade delete |
| role | TEXT | `user` or `assistant` |
| content | TEXT | Displayable message body |
| run_id | UUID | Nullable; assistant messages link to chat run context |
| citations_json | JSONB | Assistant citations in the same shape returned by current chat answers |
| retrieved_context_count | INTEGER | Nullable for user messages |
| prompt_tokens | INTEGER | Nullable; assistant message metadata |
| completion_tokens | INTEGER | Nullable; assistant message metadata |
| tokens_used | INTEGER | Nullable; assistant message metadata |
| cost_estimate_usd | FLOAT | Nullable; assistant message metadata |
| error | TEXT | Nullable; populated only if failed-message persistence is later enabled |
| created_at | TIMESTAMPTZ | Auto-set |

Indexes:

- `(session_id, created_at, id)`
- `run_id`

LangChain checkpoint tables are created by the checkpointer setup path. They are not part of the UI contract.

## API Contract

Keep `POST /chat/answer` unchanged.

Add these endpoints under the existing chat router.

### `POST /chat/sessions`

Creates an empty active session.

Request:

```json
{
  "title": "Optional title"
}
```

Response `201`:

```json
{
  "id": "00000000-0000-0000-0000-000000000000",
  "title": "Optional title",
  "status": "active",
  "created_at": "2026-05-24T19:00:00Z",
  "updated_at": "2026-05-24T19:00:00Z",
  "message_count": 0,
  "last_message_preview": null
}
```

### `GET /chat/sessions`

Lists sessions newest first.

Query params:

- `status`: `active` or `archived`, default `active`
- `limit`: 1 to 100, default 30
- `offset`: default 0

Response `200`:

```json
[
  {
    "id": "00000000-0000-0000-0000-000000000000",
    "title": "Open-source LLM updates",
    "status": "active",
    "created_at": "2026-05-24T19:00:00Z",
    "updated_at": "2026-05-24T19:10:00Z",
    "message_count": 4,
    "last_message_preview": "What changed since the last release?"
  }
]
```

### `GET /chat/sessions/{session_id}`

Returns session metadata and ordered messages.

Response `200`:

```json
{
  "id": "00000000-0000-0000-0000-000000000000",
  "title": "Open-source LLM updates",
  "status": "active",
  "created_at": "2026-05-24T19:00:00Z",
  "updated_at": "2026-05-24T19:10:00Z",
  "messages": [
    {
      "id": "11111111-1111-1111-1111-111111111111",
      "role": "user",
      "content": "What changed in recent open-source LLM releases?",
      "created_at": "2026-05-24T19:01:00Z"
    },
    {
      "id": "22222222-2222-2222-2222-222222222222",
      "role": "assistant",
      "content": "Grounded answer text.",
      "created_at": "2026-05-24T19:01:05Z",
      "run_id": "33333333-3333-3333-3333-333333333333",
      "citations": [],
      "retrieved_context_count": 3,
      "tokens_used": 900,
      "cost_estimate_usd": 0.000126
    }
  ]
}
```

### `POST /chat/sessions/{session_id}/messages`

Appends a user message, invokes the memory-backed chat flow, persists the assistant response, and returns both rows.

Request:

```json
{
  "content": "What about follow-up details?",
  "top_k": 8
}
```

Validation:

- `content`: required, non-blank, max 2048 characters.
- `top_k`: default 8, range 1 to 20.
- Archived sessions reject new messages with `409`.

Response `200`:

```json
{
  "session": {
    "id": "00000000-0000-0000-0000-000000000000",
    "title": "Open-source LLM updates",
    "status": "active",
    "updated_at": "2026-05-24T19:12:00Z"
  },
  "user_message": {
    "id": "44444444-4444-4444-4444-444444444444",
    "role": "user",
    "content": "What about follow-up details?",
    "created_at": "2026-05-24T19:12:00Z"
  },
  "assistant_message": {
    "id": "55555555-5555-5555-5555-555555555555",
    "role": "assistant",
    "content": "Grounded answer text.",
    "created_at": "2026-05-24T19:12:04Z",
    "run_id": "66666666-6666-6666-6666-666666666666",
    "citations": [],
    "retrieved_context_count": 2,
    "tokens_used": 800,
    "cost_estimate_usd": 0.000112
  }
}
```

### `PATCH /chat/sessions/{session_id}`

Updates title or status.

Request:

```json
{
  "title": "New title",
  "status": "archived"
}
```

Rules:

- Title may be set to a non-blank string up to 120 characters.
- Status may be `active` or `archived`.
- Archiving sets `archived_at`; reactivating clears it.

### Error Responses

| Status | Meaning |
|---|---|
| 404 | Session not found |
| 409 | Cannot append to archived session |
| 422 | Invalid request payload |
| 503 | Embedder, OpenRouter, LangChain memory, or chat graph unavailable |

If generation fails with `503`, the first implementation should not persist partial user-only turns. This avoids a UI state where a user message appears without a corresponding assistant answer. Failed-turn persistence can be added later with explicit retry semantics.

## Memory Behavior

The session memory must support normal follow-ups:

```text
User: What changed in recent open-source LLM releases?
Assistant: ...
User: Which of those mattered for inference cost?
```

The second question should be interpreted using prior turns, but the final answer must still cite retrieved spans and claims. If the corpus does not support the follow-up, return the existing insufficient-evidence answer.

The memory controller should keep the complete LangChain thread state in the checkpointer for the first version. Context compaction or summarization should be deferred until message volume creates a measurable cost or quality problem.

## Title Generation

For the first user message in an untitled session, derive a deterministic title without an LLM call:

- Trim whitespace.
- Collapse internal whitespace.
- Use the first 60 characters.
- Append `...` only if the original text was longer than 60 characters.

Users can rename sessions through the web UI.

## Observability

Assistant messages should store the `run_id` produced by the existing `chat_run()` context. Existing `agent_runs` rows remain the authoritative LLM call audit log.

Add structured logs around:

- session creation
- session message invocation start/end
- LangChain checkpointer errors
- chat graph errors

Logs should include `session_id` and `run_id` when available.

## Testing

Add tests before implementation:

- Migration creates `chat_sessions` and `chat_messages` with expected constraints.
- Session create/list/detail endpoints return stable response shapes.
- Posting a first message creates a title, user row, assistant row, and LangChain thread keyed by session ID.
- Follow-up message passes the same `thread_id` to the LangChain memory controller.
- Archived sessions reject new messages with `409`.
- Insufficient-evidence answers are persisted as assistant messages with empty citations and zero token usage.
- LLM or memory failures return `503` and do not persist partial turns.
- Existing `POST /chat/answer` tests continue to pass unchanged.

## Risks

- The LangChain agent may add an extra model call if implemented as a tool-calling agent. Keep the first implementation explicit and measure token/cost impact.
- Checkpointer setup may require a psycopg-style Postgres URL while the app uses SQLAlchemy `postgresql+asyncpg`. Add a small URL conversion helper if needed.
- Chat history can amplify prompt injection. The memory prompt must state that previous user messages are untrusted context for conversation continuity, not factual evidence.
- UI display tables and LangChain checkpoint state can diverge if writes are not ordered carefully. Persist app rows only after the memory-backed answer succeeds.

## Acceptance Criteria

- A client can create a chat session, send two messages to the same session, reload the session, and see all persisted turns.
- The second message uses the same LangChain `thread_id` as the first.
- Assistant answers retain validated citations to spans/documents/sources.
- Single-turn CLI behavior through `POST /chat/answer` remains backward compatible.
- The paired React UI spec can be implemented using only the endpoints in this document.
