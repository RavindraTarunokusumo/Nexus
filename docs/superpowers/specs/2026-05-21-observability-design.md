# Observability — Centralized Logger & DB-Backed Pipeline Tracer

**Status:** Design
**Date:** 2026-05-21
**Author:** Brainstormed with Claude
**Phase:** Post-Phase-3 hardening

## Motivation

A visibility review of the Nexus pipeline ([reference](../../../app)) surfaced critical gaps:

1. No central logging — only `app/main.py` instantiates a logger; ingestion, chunk/embed, extraction, and LLM call sites emit nothing.
2. `agent_runs` is the only audit channel, but has no `run_id`, `document_id`, or `span_id` — LLM calls cannot be joined back to the document or span that triggered them, violating the project's own provenance invariant ([docs/database.md:166-174](../../database.md)).
3. `agent_runs` truncates prompts to 300 chars and responses to 500 chars, making schema-failure debugging impossible.
4. Per-span extraction failures live only in LangGraph state and are discarded after `graph.ainvoke` returns.
5. `documents.status` lacks per-stage timestamps — stuck-document detection requires reading code, not SQL.
6. `LLMClient._log` runs inside `finally`; a DB failure in the audit write shadows the original LLM exception.

This iteration introduces a centralized observability layer (logger + DB-backed pipeline tracer) that closes gaps #1–#5 and partially closes #6 by isolating tracer failures. Several adjacent silent-failure gaps from the review are deferred to TODO.md (see "Out of Scope" below).

## Scope

### In scope

- New `app/observability/` package with three modules: `run_context.py`, `logger.py`, `tracer.py`
- Alembic migration `0002_observability.py`:
  - `agent_runs`: add nullable `run_id`, `document_id`, `span_id`, `prompt_tokens`, `completion_tokens`; remove the 300/500 char truncation in the writer (column types already JSONB-compatible)
  - New `span_extractions` table
  - `documents`: add nullable `chunked_at`, `embedded_at`, `extraction_started_at`, `extraction_completed_at`
- Wire run/document/span correlation through `LLMClient`, the extraction LangGraph, and `_chunk_and_embed`
- `configure_logging()` invoked from FastAPI lifespan and CLI startup
- Two new CLI commands: `nexus runs list`, `nexus runs show <run_id>`
- `ExtractionSummary.run_id` field on the `/documents/{id}/extract-claims` response
- TODO.md additions covering the deferred work

### Out of scope (deferred to TODO.md)

- LangSmith tracing integration for LLM calls (env-gated via `LANGCHAIN_TRACING_V2` / `LANGCHAIN_API_KEY`)
- Full CLI UX: progress bars on ingest/extraction, color-coded log levels, `nexus status --live` dashboard
- FastAPI request_id middleware + `X-Request-ID` propagation
- `_chunk_and_embed` try/except wrap setting `chunk_failed` / `embed_failed` status
- RSS entry-fetch drop logging + `dropped` field in `IngestResult`
- File-sink (`logs/nexus.jsonl`) + `nexus logs tail` command

## Architecture

```
                            ┌────────────────────────────────────┐
                            │       app/observability/           │
                            │                                    │
   FastAPI lifespan  ─────▶ │  logger.configure_logging()        │
   CLI main          ─────▶ │     stdlib + JSON formatter to     │
                            │     stdout; RunContextFilter       │
                            │     injects run_id/doc_id/span_id  │
                            │                                    │
   extract_claims    ─────▶ │  run_context.extraction_run(...)   │
   route             ┌────▶ │     ContextVar binding             │
                     │      │                                    │
   LLMClient,        │      │  tracer.record_agent_run(...)      │
   extraction graph, │      │  tracer.record_span_extraction(..) │
   _chunk_and_embed  └────▶ │  tracer.mark_document_status(..,t) │
                            └────────────────────────────────────┘
                                          │
                                          ▼
                            ┌────────────────────────────────────┐
                            │  Postgres                          │
                            │   agent_runs (+ run_id, doc_id,    │
                            │               span_id, untrunc)    │
                            │   span_extractions (NEW)           │
                            │   documents (+ *_at timestamps)    │
                            └────────────────────────────────────┘
                                          ▲
                                          │
                            ┌────────────────────────────────────┐
                            │  CLI                               │
                            │   nexus runs list                  │
                            │   nexus runs show <run_id>         │
                            └────────────────────────────────────┘
```

Key choices:

- **Contextvars carry correlation, not function args.** `run_id`, `document_id`, and `span_id` are bound by `extraction_run()` and `span_scope()` async context managers. `LLMClient.complete_json` reads them implicitly — no signature changes leak across the codebase. The same contextvars feed `RunContextFilter` so every log line during an extraction is correlated.
- **Tracer = thin DB writers, not a framework.** Four functions; each opens a short-lived session, writes one row, commits. No batching, no buffering, no async queue. Tracer failures are caught and logged at WARNING and never raise.
- **Logger config from env.** `LOG_LEVEL` (default `INFO`), `LOG_FORMAT` (`json` default; `console` for local dev). One `configure_logging()` call sets root logger handlers.
- **Migration is forward-only.** All new columns are nullable; no production data exists. Downgrade is defined (drop columns + drop table).

## Components

### `app/observability/run_context.py`

```python
run_id_var: ContextVar[uuid.UUID | None] = ContextVar("run_id", default=None)
document_id_var: ContextVar[uuid.UUID | None] = ContextVar("document_id", default=None)
span_id_var: ContextVar[uuid.UUID | None] = ContextVar("span_id", default=None)

@asynccontextmanager
async def extraction_run(document_id: uuid.UUID) -> AsyncIterator[uuid.UUID]:
    """Mint a run_id, bind run_id + document_id, yield run_id, Token-reset on exit."""

@asynccontextmanager
async def span_scope(span_id: uuid.UUID) -> AsyncIterator[None]:
    """Bind span_id within an extraction_run, Token-reset on exit."""

def current_context() -> dict[str, uuid.UUID | None]:
    """Snapshot {run_id, document_id, span_id} for log records / DB writes."""
```

Token-reset on `__aexit__` prevents context bleed across concurrent `asyncio.gather` tasks.

### `app/observability/logger.py`

```python
class RunContextFilter(logging.Filter):
    def filter(self, record: LogRecord) -> bool:
        # Wrapped in try/except — broken contextvar must not silence the line.
        ctx = current_context()
        record.run_id = str(ctx["run_id"]) if ctx["run_id"] else None
        record.document_id = ...
        record.span_id = ...
        return True

def configure_logging(level: str | None = None, fmt: str | None = None, *,
                     force: bool = False) -> None:
    """Idempotent. Reads LOG_LEVEL, LOG_FORMAT from env. Installs JSON formatter
       (default) or console formatter on the root logger; attaches RunContextFilter."""
```

JSON formatter emits `ts`, `level`, `logger`, `msg`, `run_id`, `document_id`, `span_id`, plus any `extra={…}` fields. Built on stdlib only — a ~20-line `Formatter` subclass; no external dep.

### `app/observability/tracer.py`

```python
async def record_agent_run(
    session_factory, *, run_type, model, input_payload, raw_output,
    total_tokens, status, prompt_tokens=None, completion_tokens=None,
) -> None:
    """Insert one agent_runs row. Reads run_id/document_id/span_id from contextvars.
       Catches and logs DB errors; never raises."""

async def record_span_extraction(
    session_factory, *, span_id, status, attempts, error=None,
) -> None: ...

async def mark_document_timestamp(
    session_factory, document_id, field: Literal[
        "chunked_at", "embedded_at",
        "extraction_started_at", "extraction_completed_at",
    ]
) -> None: ...
```

All three are fire-and-forget from the caller's perspective.

### Edits to existing code

| File | Change |
|---|---|
| `app/intelligence/llm_client.py` | Replace `_log` with `tracer.record_agent_run` call. Remove truncation. Split `prompt_tokens` / `completion_tokens` from OpenRouter usage. |
| `app/intelligence/extraction.py` | `make_extraction_graph` wraps the ainvoke flow in `extraction_run(document_id)`. `_extract_one_span` wraps work in `span_scope(span_id)` and writes a `span_extractions` row. `load_spans` calls `mark_document_timestamp(... "extraction_started_at")`; `update_status` calls `... "extraction_completed_at"`. |
| `app/api/routes_ingestion.py` | `_chunk_and_embed` calls `mark_document_timestamp("chunked_at")` after chunk-commit and `("embedded_at")` after embed-commit. No try/except wrap (deferred). |
| `app/api/routes_claims.py` | `ExtractionSummary` gains a `run_id: uuid.UUID` field, populated from the graph's final state. |
| `app/main.py` | Lifespan calls `configure_logging()` first. |
| `app/cli/main.py` | Calls `configure_logging()` at startup; registers `runs` Typer sub-app. |
| `app/cli/db.py` | New async readers: `list_runs(limit, offset)` and `show_run(run_id)`. |
| `app/cli/render.py` | Two new renderers — plain Rich tables (no progress bars; deferred). |
| `app/db/models.py` | `AgentRun`: add `run_id`, `document_id`, `span_id`, `prompt_tokens`, `completion_tokens`. New `SpanExtraction` model. `Document`: add 4 `*_at` columns. |
| `app/db/migrations/versions/0002_observability.py` | New migration. |

### Schema details

`span_extractions`:

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| run_id | UUID | NOT NULL; correlates to `agent_runs.run_id` |
| span_id | UUID | FK → spans (CASCADE) |
| document_id | UUID | FK → documents (CASCADE); denormalized for query convenience |
| status | TEXT | `success`, `schema_error`, `llm_error`, `malformed_response` |
| attempts | INTEGER | 1 on success first try, up to `_MAX_RETRIES + 1` |
| error | TEXT | Nullable; last error message on failure |
| created_at | TIMESTAMPTZ | Auto-set |

Indexes: `run_id`, `(document_id, span_id)`, `status`.

`agent_runs` additions:

| Column | Type | Notes |
|---|---|---|
| run_id | UUID | Nullable (historical rows lack one) |
| document_id | UUID | Nullable; FK → documents (CASCADE) |
| span_id | UUID | Nullable; FK → spans (CASCADE) |
| prompt_tokens | INTEGER | Nullable |
| completion_tokens | INTEGER | Nullable |

Index: `run_id`.

`documents` additions: `chunked_at`, `embedded_at`, `extraction_started_at`, `extraction_completed_at` — all `TIMESTAMPTZ NULL`.

## Data Flow

### Happy path: `POST /documents/{doc_id}/extract-claims`

```
1. routes_claims.extract_claims
2. make_extraction_graph(...).ainvoke({document_id, model, ...})
3. graph node: load_spans
     extraction_run(document_id) ENTERS                ──▶ mints run_id=R1
     contextvars: run_id=R1, document_id=D1
     tracer.mark_document_timestamp(D1, "extraction_started_at")
     SELECT spans for D1
4. graph node: extract_spans
     asyncio.gather(bounded(s1), bounded(s2), ...) with Semaphore(5)
     task for span S1:
       span_scope(S1) ENTERS                           contextvars: R1, D1, S1
         LLMClient.complete_json(...)
           httpx POST to OpenRouter
           tracer.record_agent_run(
             run_type="claim_extraction", model=...,
             input_payload={system, user},  ← full, untruncated
             raw_output=full_response_text,
             prompt_tokens=..., completion_tokens=...,
             status="success")
           pydantic-validate; return (ExtractionOutput, total_tokens)
         tracer.record_span_extraction(S1, status="success", attempts=1)
       span_scope(S1) EXITS                            contextvars: R1, D1
5. graph node: store_claims  →  INSERT claims + claim_evidence
6. graph node: update_status
     doc.status = "claims_extracted"
     tracer.mark_document_timestamp(D1, "extraction_completed_at")
   extraction_run() EXITS                              all contextvars reset
7. extract_claims route returns ExtractionSummary { run_id: R1, ... }
```

Every log record emitted between steps 3 and 6 carries `run_id=R1`, plus `document_id` and (during step 4 tasks) `span_id`. `nexus runs show R1` reconstructs the timeline from the DB.

### Retry path inside `_extract_one_span`

```
attempt=1: complete_json → LLMSchemaError
           tracer.record_agent_run(status="schema_error")  ← attempt logged
           build_correction_prompt; retry
attempt=2: complete_json → success
           tracer.record_agent_run(status="success")       ← second row, same span_id
After loop exits:
           tracer.record_span_extraction(
               span_id=S2, status="success", attempts=2, error=None)
```

One `agent_runs` row per LLM call (retries visible as multiple rows with the same `span_id` + `run_id`); one `span_extractions` row per span summarising the outcome.

### Failure path: span-level `LLMError`

```
attempt=1..3: LLMError on every attempt
              tracer.record_agent_run(status="llm_error" / "malformed_response")
After loop:
              tracer.record_span_extraction(
                  span_id=S2, status="llm_error", attempts=3,
                  error="OpenRouter 400: ...")
```

`update_status` sees ≥1 failed + ≥1 success → `extraction_partial`. Failures now queryable.

### Failure path: pipeline abort (`LLMNetworkError`)

```
LLMNetworkError bubbles out of asyncio.gather
extract_spans node returns {"error": "..."}
graph routes to update_status (skip store_claims)
update_status: doc.status = "extraction_failed"; mark_document_timestamp(D1, "extraction_completed_at")
extraction_run() EXITS normally
route raises HTTPException(503)
```

`extraction_started_at` / `extraction_completed_at` bracket even failed runs.

### Ingestion path: timestamps only

```
ingest_url → _persist_document → response sent
                                  │
                                  ▼ (BackgroundTasks)
                            _chunk_and_embed
                                  ├─▶ chunk + commit
                                  ├─▶ tracer.mark_document_timestamp(doc_id, "chunked_at")
                                  ├─▶ embed + commit
                                  └─▶ tracer.mark_document_timestamp(doc_id, "embedded_at")
```

No contextvars used here — no `run_id` for ingestion in this iteration.

### CLI flow: `nexus runs show <run_id>`

```
cli/main.py:runs_show
  → cli/db.py:show_run(run_id)
       SELECT * FROM agent_runs WHERE run_id = ? ORDER BY created_at
       SELECT * FROM span_extractions WHERE run_id = ? ORDER BY created_at
       SELECT *_at, status FROM documents WHERE id = (the run's document_id)
  → cli/render.py:render_run(...)
       Rich tables: header (doc + timing), agent_runs, span_extractions
       OR --json → JSON dump
```

## Error Handling

The principle: **observability code must never break the pipeline**.

### Tracer failure isolation

```python
async def record_agent_run(session_factory, **fields) -> None:
    try:
        async with session_factory() as session:
            session.add(AgentRun(**fields))
            await session.commit()
    except Exception:
        logger.exception(
            "tracer.record_agent_run failed",
            extra={"run_type": fields.get("run_type"), "status": fields.get("status")},
        )
        # swallow — never raise
```

This closes the audit-write shadowing bug: the previous `try/finally` in `LLMClient.complete_json` is replaced by an unconditional `await tracer.record_agent_run(...)` in the same logical position, and `record_agent_run` cannot raise. The original `LLMNetworkError` / `LLMSchemaError` therefore always wins.

### Logger failure isolation

`RunContextFilter.filter` wraps its contextvar reads in `try/except Exception: return True` so a misconfigured contextvar can never silence a log line. JSON formatter falls back to `repr()` for any value that fails `json.dumps`.

### `configure_logging()` idempotency

Module-level `_configured` flag; second call is a no-op. Tests can force-reset with `configure_logging(force=True)`.

### Context bleed prevention

`Token`-reset on `__aexit__`. `ContextVar` is asyncio-task-aware, so binding inside one `gather` task does not leak into siblings. The reset is belt-and-suspenders for exception interruption.

### Failure modes intentionally NOT handled this iteration

| Failure | Behavior after this iteration | Deferred fix |
|---|---|---|
| `_chunk_and_embed` raises | Document silently stuck. `chunked_at` may be set if chunker succeeded but embedder failed — at least stuck-stage is identifiable. | Wrap in try/except, set `chunk_failed` / `embed_failed` status |
| RSS entry fetch raises | Silent drop (unchanged) | Log drop + add `dropped` field to `IngestResult` |
| FastAPI request without extraction context | Logs lack `run_id` (correct — there is none) | request_id middleware adds separate correlation field |
| Postgres unavailable during a tracer call | Tracer logs WARNING; row is lost forever | Buffered retry or file-sink fallback |

### Migration safety

All new columns are `nullable=True`. `span_extractions` is brand-new. No data backfill required. Downgrade path: drop columns + drop table.

### Exception type changes

None. The existing `LLMError` / `LLMNetworkError` / `LLMSchemaError` hierarchy is preserved.

## Testing

### New test files

| File | Purpose | Style |
|---|---|---|
| `tests/test_observability_context.py` | `extraction_run` / `span_scope` bind+reset semantics; gather-isolation between concurrent tasks | Unit (asyncio, no DB) |
| `tests/test_observability_logger.py` | `configure_logging` idempotency; JSON formatter output shape; `RunContextFilter` injects current contextvars; filter survives broken contextvar | Unit (`caplog` + `StringIO` handler for JSON path) |
| `tests/test_observability_tracer.py` | `record_agent_run` / `record_span_extraction` / `mark_document_timestamp` write expected rows; tracer swallows DB errors and logs them | Integration (testcontainers + mocked broken session_factory for the swallow case) |
| `tests/test_cli_runs.py` | `nexus runs list` and `nexus runs show <run_id>` — happy path, empty result, missing run_id, JSON output | Integration (CLI e2e, follows `test_cli_e2e.py`) |

### Updated tests

| File | Change |
|---|---|
| Extraction tests | One `span_extractions` row per span; retries produce one row per span but multiple `agent_runs` rows; document `extraction_started_at` / `extraction_completed_at` populated; `ExtractionSummary.run_id` matches DB rows |
| Ingestion tests | After `_chunk_and_embed`, `chunked_at` and `embedded_at` populated |
| LLM-client tests | `agent_runs` no longer truncates; `prompt_tokens` / `completion_tokens` split from OpenRouter usage |

### Not tested

- Log JSON output line-by-line in pipeline tests (formatter is covered once in its own test; pipeline tests assert against DB state)
- `_chunk_and_embed` failure modes (deferred)
- LangSmith integration (deferred)

### Concurrency regression test

```python
async def task(label):
    async with span_scope(uuid_for(label)):
        await asyncio.sleep(0.001 * random.randint(1, 5))
        return current_context()["span_id"]

results = await asyncio.gather(*[task(i) for i in range(20)])
assert results == [uuid_for(i) for i in range(20)]  # no cross-task bleed
```

The most likely place a correctness bug would hide and the cheapest to test directly.

### Coverage philosophy

No new thresholds. Existing `pyproject.toml` settings apply.

## Recap

- New `app/observability/` package: `run_context.py`, `logger.py`, `tracer.py`
- Migration `0002_observability.py`: 3 new correlation columns on `agent_runs` (+ 2 token-split columns + remove truncation in writer), new `span_extractions` table, 4 new `*_at` timestamps on `documents`
- Wiring through `LLMClient`, extraction graph, `_chunk_and_embed`, `main.py` lifespan, `cli/main.py` startup
- New CLI: `nexus runs list`, `nexus runs show <run_id>`
- `ExtractionSummary.run_id` field on the API response
- TODO.md additions: LangSmith, full CLI UX, `_chunk_and_embed` error status, RSS drop logging, request_id middleware, file-sink option
