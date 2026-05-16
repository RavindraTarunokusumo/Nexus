# TODO

## Active

- [x] Update CI markdown workflow descriptions to Nexus Lite terminology and remove legacy broker/flaskr references. (commit: b1d6450)
- [x] Publish onboarding docs and repo-local Codex/GitNexus assets to `main`. (commit: 3cce170)
- [x] Replace scaffold placeholders in `docs/*.md` with project-specific architecture, commands, and testing guidance.
- [x] Add the first real implementation plan for the main product slice. (docs/superpowers/plans/2026-05-15-phase1-foundation.md)
- [x] Resolve open MVP implementation choices before coding: asyncpg, SQLAlchemy 2.x async, Alembic, bge-small-en-v1.5, testcontainers.

### Phase 1 — Foundation + Ingestion (branch: feat/phase1-foundation)

- [x] T1: Project scaffold — pyproject.toml, Dockerfile, docker-compose.yml, .env.example, alembic.ini, __init__.py files (commit: e7058a2)
- [x] T2: DB models — all 8 tables in app/db/models.py, session factory in app/db/session.py (commit: 02232ba)
- [x] T3: Alembic migration — pgvector extension + all 8 tables with indexes (commit: 14e15a6)
- [x] T4: FastAPI app + config — app/config.py (pydantic-settings v2), app/main.py (lifespan, routers) (commit: fc123be)
- [x] T5: Source management API — POST /sources, GET /sources in app/api/routes_sources.py (commit: f445a13)
- [x] T6: Ingestion layer — app/ingestion/cleaner.py, url_fetcher.py, rss.py (commit: b29549b)
- [x] T7: Ingestion API — POST /ingest/rss/{source_id}, POST /ingest/url, POST /ingest/text (commit: abe055d)
- [x] T8: Domain pack — app/domain_packs/personal_ai_tech.yaml (commit: 3d2bdac)
- [x] T9: Integration tests — tests/conftest.py, test_sources.py, test_ingestion.py (commit: 69c4dca)
- [x] Pre-PR: simplify refactor, security hardening, doc updates (commits: 5c10084, e6d6b09, b1129e9)
- [x] Wire GitNexus into the repo-local Codex workflow and onboarding docs. (commit: 5b02092)

### Phase 2 — Retrieval Foundation (branch: feat/phase2-retrieval, merge: 7633d13)

- [x] T1: Span chunker — app/ingestion/chunker.py (commit: 20b2470)
- [x] T2: Embedder singleton — app/intelligence/embedder.py, __init__.py (commit: 198d810)
- [x] T3: Document/search routes — GET /documents, GET /documents/{id}, POST /search/spans (commit: 9c2e89b)
- [x] T4: Background chunk+embed pipeline — _chunk_and_embed, BackgroundTasks wiring (commit: cf7d267)
- [x] T5: App wiring — Embedder lifespan init, documents router mount (commit: c2dbc13)
- [x] T6: Infra — hf_cache volume, sentence-transformers/tiktoken deps (commit: 78d2be7)
- [x] T7: Test suite — 41 tests, MockEmbedder, local-Postgres fallback, sgmllib stub (commit: 2cf0e20)
- [x] Review fixes — chunker trailing-span bug, 422→200 empty search, status param shadow, unused imports, race-condition handling (commit: 402b035)

### Phase 2.5 — Monitoring CLI (branch: wt/phase2.5-cli)

- [x] T1: CLI scaffold — pyproject.toml deps (typer, rich), app/cli/__init__.py, app/cli/config.py (commit: f64c1f5)
- [x] T2: DB reader — app/cli/db.py: count_by_status, list_sources, list_documents, get_document_with_spans, get_status_snapshot (commit: c72b1bb)
- [x] T3: Renderers — app/cli/render.py: rich tables + --json for all 5 output shapes (commit: d1d00f9)
- [x] T4: HTTP client — app/cli/http.py: ingest_url/text/rss, search_spans wrappers (commit: d71ed64)
- [x] T5: Main app — app/cli/main.py: status, sources, documents, document commands; _run() helper (commit: b7bd5a9)
- [x] T6: search command — POST /search/spans via http_search_spans alias (commit: 5bce81c)
- [x] T7: ingest commands — ingest url/text/rss on ingest_app sub-typer (commit: 62555fe)
- [x] Review fixes — timeout 10s, top-level imports, datetime/timedelta cleanup (commit: acb3fa0)

## Future

### Phase 3 — Claim Extraction + LLM Gateway

- [ ] POST /documents/{id}/extract-claims — LLM-driven claim extraction from document spans
- [ ] OpenRouter LLM client — configurable model gateway, cost tracking via AgentRun
- [ ] Evidence linking — ClaimEvidence rows joining claims to supporting spans
- [ ] Re-embedding sweep — background job to embed documents left in "chunked" state when embedder was unavailable

### Ongoing

- [ ] HTTP Basic Auth / API key middleware (security gap, open since Phase 1)
- [ ] Shared httpx.AsyncClient via lifespan (currently created per-request in ingestion)
- [ ] Populate `docs/iterations/active/` with execution logs
- [ ] Record durable workflow lessons in `docs/insights.md` as they appear.
