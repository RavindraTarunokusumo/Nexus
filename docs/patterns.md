# Patterns

Record repo-specific implementation patterns here as they emerge. The current design constraints come from [docs/specs/README.md](specs/README.md).

## Initial Patterns

- Keep domain-specific behavior in domain packs.
- Keep the LLM gateway reusable and logged.
- Validate structured model outputs before persistence.
- Preserve source provenance on every derived object.
- Prefer deterministic logic and local models before expensive model calls.
- Keep MVP scope focused on Source, Document, Span, Claim, Brief, and Agent Run layers.

## Session Memory Pattern

LangGraph session memory wraps the existing single-turn chat graph rather than replacing it. `make_memory_graph()` creates a `StateGraph` with a single `"chat"` node that calls `run_chat_with_context` after injecting the conversation history as plain-text context into the question. The graph is compiled with `AsyncPostgresSaver` (backed by a `psycopg_pool.AsyncConnectionPool`) so each session thread's state persists across requests without in-memory state on the API server.

The `invoke_with_memory` entry point uses `{"configurable": {"thread_id": str(session_id)}}` so LangGraph keys checkpoints by session UUID. This means the API server is stateless — any replica can handle any session turn.

## Correlated Subquery for List Endpoints

When a list endpoint needs aggregates per row (e.g., `message_count`, `last_message_preview`), use correlated scalar subqueries in the main SELECT rather than issuing N+1 follow-up queries per row. SQLAlchemy syntax:

```python
count_sq = (
    select(func.count())
    .where(ChatMessage.session_id == ChatSession.id)
    .correlate(ChatSession)
    .scalar_subquery()
)
```

This keeps the list endpoint to a single round-trip regardless of page size.

## Frontend API Client Patterns

The `web/src/api/client.ts` typed fetch layer follows these conventions:
- All errors are normalised into `ApiError {status: number | null, message: string}` via `normalizeApiError()`, regardless of whether the failure was a network error, non-JSON body, or structured `{detail: ...}` FastAPI error.
- `ApiCallError` carries the `ApiError` as an explicit `readonly` field (not a constructor parameter property) to satisfy TypeScript's `erasableSyntaxOnly` constraint.
- Hooks (`useSessions`, `useChatSession`) reset error to `null` at the start of each load so transient failures never get stuck in state.
- The `Composer` is disabled (`disabled={!session || loading || !detail}`) until the session detail is fully loaded to prevent dropped messages during the initial fetch.
