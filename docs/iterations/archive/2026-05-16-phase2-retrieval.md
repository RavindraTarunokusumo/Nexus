# Phase 2 — Retrieval Foundation

**Date:** 2026-05-16
**Branch:** `feat/phase2-retrieval`
**PR:** [#3](https://github.com/RavindraTarunokusumo/Nexus/pull/3)
**Merge commit:** `7633d13`

---

## What Was Built

### New files

| File | Purpose |
|------|---------|
| `app/ingestion/chunker.py` | `chunk_document(text, metadata) -> list[dict]` — overlapping 600-word sliding windows with 100-word overlap; each span carries `span_index`, `text`, `token_count`, `metadata_json` |
| `app/intelligence/__init__.py` | Package marker |
| `app/intelligence/embedder.py` | `Embedder` singleton wrapping BAAI/bge-small-en-v1.5; 384-dim L2-normalised vectors; sentence-transformers is imported lazily so the module is importable without the library |
| `app/api/routes_documents.py` | `GET /documents` (filters: `doc_status`, `source_id`; pagination: `limit`, `offset`), `GET /documents/{id}` (with spans, embedding vectors excluded), `POST /search/spans` (pgvector cosine similarity, top-k, returns `[]` when index is empty) |
| `conftest.py` | Root pytest conftest: injects a minimal `sgmllib` stub before imports so feedparser 6.0.x can be loaded on Python 3.11+ (where `sgmllib` was removed from stdlib) |
| `tests/test_chunker.py` | 7 unit tests for chunker windowing, overlap, metadata, edge cases |
| `tests/test_embedder.py` | 4 unit tests for real Embedder (excluded from standard CI run — require model download) |
| `tests/test_documents.py` | 7 integration tests for list/filter/pagination, detail+spans, 404 |
| `tests/test_search.py` | 4 integration tests for semantic ranking, top_k, empty index, response shape |
| `tests/test_chunk_embed_task.py` | 3 tests for `_chunk_and_embed` happy path, idempotency, empty text |

### Modified files

| File | Change |
|------|--------|
| `app/main.py` | Embedder initialised in `lifespan`; falls back to `None` with a warning if model load fails; `documents_router` mounted |
| `app/api/routes_ingestion.py` | Added `_chunk_and_embed` background task; wired `BackgroundTasks` into all three ingest routes; replaced `begin_nested()` savepoint dedup with select-before-insert in `_persist_document` and `_get_or_create_manual_source` |
| `docker-compose.yml` | Added `hf_cache` named volume mapping to `/root/.cache/huggingface` |
| `pyproject.toml` | Added `sentence-transformers>=3.0.0`, `tiktoken>=0.7.0` |
| `tests/conftest.py` | `MockEmbedder` (hash-based deterministic, unit-norm); `client_with_embedder` fixture; `mock_embedder` fixture; local PostgreSQL fallback when Docker unavailable; all three routers included in test app |

---

## Review Fixes Applied (Copilot PR #3)

| Comment | Fix |
|---------|-----|
| Chunker produces redundant trailing span when `len(words)` is exact multiple of step | Added early-break: `if start > 0 and len(words) - start <= _OVERLAP_TOKENS: break` |
| 422 for empty search index is semantically wrong for a well-formed request | Changed to `return []` (200 OK with empty list) |
| `status` query param in `list_documents` shadows `fastapi.status` module | Renamed to `doc_status`; test updated |
| `IntegrityError` import unused after savepoint removal | Kept — now used to catch rare concurrent-write race at `session.commit()` in url/text routes |
| Concurrent-write race results in 500 instead of graceful skipped | Added `try/except IntegrityError` around `session.commit()` in `ingest_url` / `ingest_text` |
| No doc comment on BG task commit-ordering assumption | Added docstring to `_chunk_and_embed` |
| Unused imports in test files | Removed `AsyncMock`, `patch`, `datetime`, `timezone`, `select` from `test_documents`; `numpy` from `test_embedder` and `test_search` |

**Skipped (intentional design decisions):**
- `embedder=None` leaves docs in `chunked` state — by design; Phase 3 will add re-embedding sweep
- `nexus_full_mvp_spec_markdown.md` deletion — pre-existing commit `ab2f635` ("chore: remove stale full-spec draft (superseded by docs/specs/)"), not Phase 2 work

---

## Key Decisions

### Background tasks over async workers
Used FastAPI `BackgroundTasks` for the chunk+embed pipeline. Simpler than Celery/ARQ for a single-process deployment. Trades observability (no job queue, no retry) for zero infra overhead. Phase 3 can introduce a proper task queue if needed.

### Status pipeline: fetched → chunked → embedded
Three-state pipeline makes it easy to query documents by processing stage and to diagnose failures (e.g., stuck in `chunked` when embedder is unavailable).

### Select-before-insert for dedup (no savepoints)
`begin_nested()` with asyncpg 0.29+ marks the outer transaction as DEACTIVE when a savepoint rolls back on a UniqueViolationError, causing `PendingRollbackError` on the subsequent `session.commit()`. Replaced with a SELECT check before INSERT. Concurrency risk is negligible for single-writer ingestion workloads; the rare race is handled with `try/except IntegrityError` at commit time.

### Decoupled `_chunk_and_embed` signature
`_chunk_and_embed(doc_id, session_factory, embedder)` takes a session factory rather than an open session. This lets it open its own connection from outside any existing transaction, which is required since it runs after the response session has been torn down.

### hf_cache Docker volume
Persists the ~130MB BAAI/bge-small-en-v1.5 model across container rebuilds. Without it, every `docker compose up` triggers a fresh HuggingFace download.

### `embed_one` is an alias
`Embedder.embed_one(text)` delegates to `embed([text])[0]`. No separate code path, no batching overhead for single queries.

---

## Open Items Carried to Phase 3

- `POST /documents/{id}/extract-claims` — LLM-driven claim extraction
- OpenRouter LLM client with cost tracking via `AgentRun` table
- `ClaimEvidence` rows linking claims to supporting spans
- Re-embedding background sweep for documents stuck in `chunked` state
- HTTP Basic Auth / API key middleware (security gap open since Phase 1)
- Shared `httpx.AsyncClient` via lifespan

---

## Test Results

```
pytest tests/ -q --ignore=tests/test_embedder.py
41 passed in 3.9s
```

Breakdown:
- `test_chunk_embed_task.py`: 3/3
- `test_chunker.py`: 7/7
- `test_documents.py`: 7/7
- `test_ingestion.py`: 12/12
- `test_search.py`: 4/4
- `test_sources.py`: 8/8
