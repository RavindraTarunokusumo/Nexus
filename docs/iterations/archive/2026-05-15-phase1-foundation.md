# Phase 1 Foundation — Archive

**Date:** 2026-05-15
**Status:** Complete — merged to `main`
**PR:** #2 — feat: Phase 1 foundation — project scaffold, DB schema, ingestion layer
**Commits:** `6d45ed2` (squash merge) + review fixes + GitNexus integration

---

## What Was Built

### Project Scaffold
- `pyproject.toml` — Python 3.11, FastAPI, SQLAlchemy async, asyncpg, pgvector, feedparser, httpx, trafilatura, pydantic-settings, pytest
- `Dockerfile`, `docker-compose.yml` — app + `pgvector/pgvector:pg16` + `redis:7` with healthchecks
- `.env.example`, `.gitignore`, `alembic.ini`

### Database Layer (`app/db/`)
- All 8 tables: `sources`, `documents`, `spans` (vector(384)), `claims`, `claim_evidence`, `briefs`, `brief_items`, `agent_runs`
- UUID primary keys, timezone-aware UTC timestamps throughout
- Alembic async migration `0001` — pgvector extension + all tables + indexes

### API (`app/api/`)
- `POST /sources`, `GET /sources`, `GET /sources/{id}`
- `POST /ingest/rss/{source_id}`, `POST /ingest/url`, `POST /ingest/text`

### Ingestion Layer (`app/ingestion/`)
- RSS: httpx-fetched feed bytes → `asyncio.to_thread(feedparser.parse)` — SSRF-safe, non-blocking
- URL fetching: per-hop SSRF redirect validation (`_validated_get`) — scheme allowlist + DNS private-IP blocking on every redirect
- HTML cleaning: trafilatura with plain-text fallback
- Deduplication: SHA-256 content hash; race-safe via `UNIQUE` constraint + savepoint (`begin_nested`)

### Tests
- 20 integration tests against a real `pgvector/pgvector:pg16` testcontainer
- Covers: source CRUD, RSS/URL/text ingestion, deduplication, provenance chain, SSRF rejection

---

## Code Review Fixes (post-merge)

Copilot review raised 8 inline comments; all resolved before merge:

| Issue | Fix |
|---|---|
| SSRF bypass via redirects (`follow_redirects=True`) | Disabled auto-redirects; added `_validated_get` loop that re-runs scheme + SSRF check on each hop |
| `feedparser.parse(url)` blocks event loop and bypasses SSRF | Replaced with `fetch_bytes` (httpx-validated) + `asyncio.to_thread(feedparser.parse, bytes)` |
| Per-document `session.commit()` inside RSS loop — partial failure risk | Switched to `begin_nested()` savepoints per document; single `session.commit()` at end of each endpoint |
| `_get_or_create_manual_source` mixed flush/commit boundaries | Replaced `session.rollback()` with `begin_nested()` — savepoint rolls back cleanly on IntegrityError |
| Unused `AsyncSession`, `Annotated` imports in `routes_sources.py` | Removed |
| Wrong return type on `db_session` generator | Fixed to `AsyncGenerator[AsyncSession, None]` |
| Migration `spans.embedding` Text→DROP→ADD dance | Removed placeholder; `ALTER TABLE spans ADD COLUMN embedding vector(384)` directly |
| f-string with no interpolation; error message omitted resolved IP | Fixed: includes `ip_str` in message |

---

## GitNexus Integration

Established as a follow-on to the Phase 1 merge:

- Upgraded global `gitnexus` from `1.6.3` → `1.6.5-rc.44` (fixes Node.js 24 segfault in tree-sitter bindings)
- Added minimal docstrings to all 8 empty `__init__.py` files (parser requires at least one module scope per file)
- `npx gitnexus analyze` now runs cleanly: **1,387 nodes · 1,744 edges · 23 clusters · 16 flows**
- `CLAUDE.md` and `AGENTS.md` updated: `## Code Graph / Repo Map` points to GitNexus section; Step 2 of the 7-Step Workflow now reads `gitnexus://repo/Nexus/context` as its first action
- Note: the `<!-- gitnexus:start/end -->` block is owned by `npx gitnexus analyze` and regenerated on each run — do not edit its content directly

---

## Key Decisions

- **Savepoints over per-document commits** — `begin_nested()` makes RSS ingestion atomic at the batch level while still isolating individual `IntegrityError` rollbacks
- **`fetch_bytes` + `asyncio.to_thread` for RSS** — keeps the event loop free and applies the same SSRF guards to the feed fetch itself
- **`_validated_get` redirect loop** — explicit hop-by-hop validation rather than disabling redirects entirely; allows legitimate redirect chains while blocking SSRF at every step
- **Migration: no Text placeholder** — vector column added directly after table creation; the placeholder + DROP was unnecessary since the pgvector extension is created earlier in the same migration

---

## Open Items (carried to Phase 2)

- HTTP Basic Auth / API key middleware — noted in PR as a security gap; service must remain behind a restricted firewall until implemented
- Shared `httpx.AsyncClient` via lifespan — currently created per-request in ingestion routes
- Phase 2 scope: span chunking (`app/ingestion/chunker.py`), embeddings (`BAAI/bge-small-en-v1.5`), pgvector semantic search
