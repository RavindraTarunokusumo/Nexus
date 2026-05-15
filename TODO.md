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

## Future

- [ ] Populate `docs/iterations/active/` with the first execution log when work starts.
- [ ] Record durable workflow lessons in `docs/insights.md` as they appear.
