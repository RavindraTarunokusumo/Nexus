# Architecture

> **Phase 3 Status: Claim extraction implemented**

Nexus Lite is a private FastAPI application backed by PostgreSQL + pgvector, Redis, and local embeddings. The Phase 1 foundation covers source registration, document ingestion, and the full persistence schema.

Read [docs/specs/architecture.md](specs/architecture.md) for the full architecture spec.

## Tech Stack

| Layer | Technology |
|---|---|
| API | Python 3.11, FastAPI |
| ORM / async DB | SQLAlchemy 2.x async + asyncpg |
| Vector store | pgvector 0.2+, BAAI/bge-small-en-v1.5 (384 dims) |
| Migrations | Alembic |
| Config | pydantic-settings v2 |
| CLI | Typer >= 0.12, Rich >= 13.7 |
| RSS fetching | feedparser |
| URL fetching / cleaning | httpx + trafilatura |
| Cache / queue | Redis 7 |
| Containers | Docker Compose (pgvector/pgvector:pg16, redis:7-alpine) |
| LLM orchestration | LangGraph >= 0.2.0 |
| LLM gateway | OpenRouter (T2: `openai/gpt-4o-mini`) |

## Directory Layout

```
app/
  main.py                  # FastAPI app + lifespan (engine init)
  config.py                # pydantic-settings Settings (DATABASE_URL, APP_SECRET, …)
  api/
    deps.py                # DbSession dependency (injects AsyncSession from request state)
    routes_sources.py      # GET/POST /sources, GET /sources/{id}
    routes_ingestion.py    # POST /ingest/rss/{source_id}, /ingest/url, /ingest/text
    routes_claims.py       # POST /documents/{id}/extract-claims, GET /claims
  db/
    models.py              # SQLAlchemy ORM models (all 8 tables)
    session.py             # make_engine / make_session_factory helpers
    migrations/
      env.py               # Alembic env wired to DATABASE_URL
      versions/
        0001_initial_schema.py  # All 8 tables + pgvector extension
  ingestion/
    cleaner.py             # normalize_text, content_hash, normalize_url, extract_text
    rss.py                 # fetch_rss_entries (feedparser + async httpx)
    url_fetcher.py         # fetch_and_clean (httpx + trafilatura)
  intelligence/
    llm_client.py          # LLMClient.complete_json — OpenRouter calls, Pydantic validation,
                           #   AgentRun logging; ExtractedClaim / ExtractionOutput schemas;
                           #   LLMError / LLMNetworkError / LLMSchemaError hierarchy
    extraction.py          # LangGraph StateGraph (load_spans → extract_spans → store_claims
                           #   → update_status); asyncio.gather concurrency (Semaphore 5);
                           #   correction-prompt retry (max 2); status constants exported
    prompts/
      extract_claims.py    # SYSTEM_PROMPT, build_user_prompt, build_correction_prompt
  domain_packs/
    personal_ai_tech.yaml  # Default domain pack definition
  cli/
    __init__.py
    config.py              # CLISettings (API_URL, DB_URL, rich/json output flags)
    db.py                  # 5 direct-Postgres readers (asyncpg, short-lived sessions)
    http.py                # 4 HTTP wrappers for ingest/search (FastAPI server)
    render.py              # 5 Rich+JSON formatters + print_ingest_result
    main.py                # Typer app — nexus console-script entry point
tests/
  conftest.py              # testcontainers fixtures, Alembic migration, per-test DB clean
  test_sources.py          # Source CRUD integration tests (8 tests)
  test_ingestion.py        # Ingestion integration tests (12 tests)
  test_cli_db.py           # CLI DB reader unit tests (8 tests)
  test_cli_render.py       # CLI render/formatter tests (10 tests)
  test_cli_e2e.py          # CLI end-to-end integration tests (10 tests)
docker-compose.yml         # postgres (pgvector/pgvector:pg16), redis:7-alpine, app
alembic.ini
pyproject.toml
```

## Runtime Flow

```text
external source
-> ingestion (RSS / URL / text)
-> document cleaner (trafilatura + normalize)
-> content-hash deduplication
-> persist Document row
-> chunking -> spans -> embeddings
-> claim extraction (LangGraph, OpenRouter T2)
-> [future] retrieval index
-> [future] brief synthesis
-> [future] query answering
```

## CLI Access Model

The `nexus` CLI uses a hybrid access strategy:

- **Reads** (status, sources, documents, document detail) go **direct to Postgres** via short-lived asyncpg sessions — no server required.
- **Ingest and search** go **through the FastAPI server** over HTTP.

`CLISettings` resolves `--api-url` and `--db-url` from flags, `API_BASE_URL` / `DATABASE_URL` env vars, or `.env` defaults. `DATABASE_URL` is required only for commands that read directly from Postgres (status, sources, documents, document); HTTP-only commands (search, ingest) work without it. Every command accepts `--json` for machine-readable output and `--api-url` / `--db-url` overrides.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | /health | Liveness check |
| POST | /sources | Register a new source |
| GET | /sources | List all sources |
| GET | /sources/{id} | Get source by UUID |
| POST | /ingest/rss/{source_id} | Fetch and ingest RSS feed entries |
| POST | /ingest/url | Fetch and ingest a single URL |
| POST | /ingest/text | Ingest raw text directly |
| POST | /search/spans | Semantic span search (query, top_k) |
| POST | /documents/{id}/extract-claims | Run claim extraction for a document |
| GET | /claims | List claims (filter by document_id, claim_type, status) |

Supported `source_type` values: `rss`, `manual`, `api`.

### Claim extraction endpoint detail

`POST /documents/{document_id}/extract-claims[?force=true]`

| Status | Meaning |
|---|---|
| 200 | Extraction complete — returns `{document_id, claims_extracted, spans_processed, spans_failed, tokens_used, cost_estimate_usd, claim_ids}` |
| 404 | Document not found |
| 409 | Claims already exist; pass `?force=true` to re-extract |
| 422 | Document not in `embedded` or a post-extraction status |
| 503 | OpenRouter unreachable |

`GET /claims` query params: `document_id` (required UUID), `claim_type`, `status` (`active`\|`rejected`), `limit`, `offset`.

## Document Status Lifecycle

```text
fetched → chunked → embedded → claims_extracted
                              → extraction_partial
                              → extraction_failed
```

Status constants exported from `app/intelligence/extraction.py`: `STATUS_EMBEDDED`, `STATUS_CLAIMS_EXTRACTED`, `STATUS_EXTRACTION_PARTIAL`, `STATUS_EXTRACTION_FAILED`, `POST_EXTRACTION_STATUSES`.

## Claim Taxonomy

Claims are typed using a Pydantic `Literal` validated at extraction time:

`model_release`, `benchmark_result`, `product_launch`, `pricing_change`, `research_finding`, `infrastructure_update`, `security_issue`, `funding_event`, `regulation`, `forecast`, `other`

## LLM Tier Model

| Tier | Purpose | Config key | Default |
|---|---|---|---|
| T2 | Claim extraction | `settings.openrouter_t2_model` | `openai/gpt-4o-mini` |
| T3 | Brief synthesis (Phase 4) | reserved | — |

Cost is tracked per call: `0.30 / 1_000_000 * total_tokens` stored in the `agent_runs.cost_estimate` column.

## Current Boundary

The MVP implements the simplified hierarchy:

```text
Source -> Document -> Span -> Claim -> Brief
```

All 8 tables are schema-ready (migration 0001). Phases 1–3 populate `sources`, `documents`, `spans`, `claims`, `claim_evidence`, and `agent_runs`. Brief synthesis is Phase 4+.

The broader PoC hierarchy adds entities, relations, signals, clusters, theses, and decision artefacts. Those remain future-facing until the core ingestion-to-synthesis loop is stable.
