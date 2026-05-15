# Testing

> **Phase 1 Status: Implemented** — 20 integration tests across two files; all pass against a real pgvector container.

Read [docs/specs/operations.md](specs/operations.md) for phase-level validation gates.

## Running Tests

```sh
python -m pytest tests/ -v
```

**Requirements:**

- Docker must be running (testcontainers starts a `pgvector/pgvector:pg16` container automatically).
- A `.env` file must exist with `DATABASE_URL` and `APP_SECRET` set (any values; the test container overrides the DB URL at runtime).

Run a single file:

```sh
python -m pytest tests/test_sources.py -v
python -m pytest tests/test_ingestion.py -v
```

## Test Architecture

Tests are **integration tests** — they run against a real PostgreSQL + pgvector instance managed by testcontainers. There are no mocks for the database layer.

Key fixtures (in `tests/conftest.py`):

| Fixture | Scope | Purpose |
|---|---|---|
| `pg_container` | session | Starts a `pgvector/pgvector:pg16` Docker container once per run |
| `db_url` | session | Builds the asyncpg connection URL from the container |
| `run_migrations` | session, autouse | Runs `alembic upgrade head` via subprocess before any test |
| `async_engine` | function | Fresh asyncpg engine per test (avoids event-loop conflicts) |
| `session_factory` | function | `async_sessionmaker` bound to the per-test engine |
| `clean_db` | function, autouse | Truncates all tables (reverse dependency order) before each test |
| `client` | function | `httpx.AsyncClient` wired to a minimal FastAPI app (no production lifespan) |

Network calls (RSS fetches, URL fetches) are patched with `unittest.mock.AsyncMock` to keep tests fast and hermetic.

## Test Files

### `tests/test_sources.py` — 8 tests

Covers the source management API:

- Create RSS source with all fields
- Create manual source without URL
- Reject unsupported `source_type`
- Reject duplicate URL (409)
- List sources when empty
- List sources returns all rows
- Get source by UUID
- Get source returns 404 for unknown UUID

### `tests/test_ingestion.py` — 12 tests

Covers ingestion endpoints and cross-cutting invariants:

- **Text ingestion:** success, empty-text rejection (422), content-hash deduplication, provenance (document links to source row)
- **URL ingestion:** success (mocked fetch), same-URL deduplication, content-hash deduplication across different URLs, blocked scheme (`file://` → 422)
- **RSS ingestion:** success with multiple entries + provenance check, deduplication skips already-seen entries, wrong source type (422), source not found (404)

## Critical Invariants Tested

- Duplicate documents (by URL or content hash) are skipped, not double-inserted.
- Every ingested document has a `source_id` that resolves to a real `sources` row.
- `source_type` validation is enforced at the API layer (422 for unknown types).
- RSS ingestion rejects non-RSS sources (422) and missing sources (404).
- Empty text is rejected before persistence (422).
- Blocked URL schemes (`file://`, etc.) are rejected (422).

## Required Test Types (Future Phases)

- Unit tests for chunking, span ordering, and embedding helpers.
- Schema validation tests for LLM extraction and synthesis outputs.
- Worker tests for job orchestration and retry behavior.
- End-to-end fixture tests: ingest a source → produce spans, claims, and a grounded answer.
- Agent/model run logging with status and cost estimate.
