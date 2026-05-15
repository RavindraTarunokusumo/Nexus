# Phase 1 Foundation — Implementation Plan

**Date:** 2026-05-15
**Branch:** `feat/phase1-foundation`
**Author:** Claude Code (autonomous)

## Scope

Phase 1 delivers the complete project scaffold, database schema, source management API, and
ingestion layer for Nexus Lite. No Phase 2+ features (embeddings, claim extraction, brief
synthesis, query) are included.

## Architecture Decisions

| Concern | Decision | Rationale |
|---|---|---|
| DB driver | asyncpg | Required for SQLAlchemy 2.x async |
| ORM | SQLAlchemy 2.x async | Spec requirement; future-proof |
| Migrations | Alembic | Industry standard with SQLAlchemy |
| Vector type | pgvector Python + `pgvector/pgvector:pg16` image | Spec requirement |
| Config | pydantic-settings v2 | Spec requirement |
| RSS | feedparser | Spec requirement |
| URL fetch | httpx + trafilatura | Spec requirement |
| Worker | None in Phase 1 | Ingestion runs synchronously in API |
| Tests | testcontainers[postgres] | Real Postgres+pgvector per spec |
| Embedding dim | 384 | bge-small-en-v1.5 output size |

## Deduplication Logic

1. Normalize URL: strip whitespace, lowercase scheme+host, strip trailing slash.
2. If URL exists in `documents.url`, reject with HTTP 409.
3. Compute `content_hash = SHA-256(normalize_text(clean_text))`.
4. If `content_hash` exists in `documents.content_hash`, reject with HTTP 409.
5. Pasted text without URL: skip URL check; rely solely on content hash.

## File Layout

```
app/
  __init__.py
  main.py
  config.py
  api/
    __init__.py
    routes_sources.py
    routes_ingestion.py
  db/
    __init__.py
    models.py
    session.py
    migrations/
      env.py
      script.py.mako
      versions/
        0001_initial_schema.py
  ingestion/
    __init__.py
    cleaner.py
    rss.py
    url_fetcher.py
  domain_packs/
    personal_ai_tech.yaml
tests/
  __init__.py
  conftest.py
  test_sources.py
  test_ingestion.py
Dockerfile
docker-compose.yml
.env.example
pyproject.toml
alembic.ini
```

## Task Breakdown

1. **T1 — Scaffold**: pyproject.toml, Dockerfile, docker-compose.yml, .env.example, alembic.ini, directory __init__.py files.
2. **T2 — DB models**: All 8 tables in `app/db/models.py`, DB session factory in `app/db/session.py`.
3. **T3 — Alembic migration**: Initial migration creating pgvector extension + all 8 tables with indexes.
4. **T4 — FastAPI app + config**: `app/config.py` (pydantic-settings), `app/main.py` (lifespan, router registration).
5. **T5 — Source management API**: `app/api/routes_sources.py` — POST /sources, GET /sources.
6. **T6 — Ingestion layer**: `app/ingestion/cleaner.py`, `app/ingestion/url_fetcher.py`, `app/ingestion/rss.py`.
7. **T7 — Ingestion API**: `app/api/routes_ingestion.py` — POST /ingest/rss/{source_id}, POST /ingest/url, POST /ingest/text.
8. **T8 — Domain pack**: `app/domain_packs/personal_ai_tech.yaml`.
9. **T9 — Integration tests**: `tests/conftest.py`, `tests/test_sources.py`, `tests/test_ingestion.py`.

## Risk / Mitigations

| Risk | Mitigation |
|---|---|
| pgvector extension unavailable in test container | Use `pgvector/pgvector:pg16` image in testcontainers fixture |
| trafilatura extraction returns None | Fall back to raw HTML text; store raw_text as-is |
| feedparser returns entries without URLs | Skip entries with no `link` field |
| asyncpg and Alembic sync/async mismatch | Use `run_sync` wrapper for Alembic env.py |
| Content hash collision | SHA-256 collision probability negligible for this use case |
