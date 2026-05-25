# Architecture

> **Phase 3 Status: Claim extraction + observability + hybrid chatbot + LLM-as-a-Judge eval framework implemented**

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
| LLM gateway | OpenRouter (T2: `deepseek/deepseek-v4-flash`) |

## Directory Layout

```
app/
  main.py                  # FastAPI app + lifespan (engine init)
  config.py                # pydantic-settings Settings (DATABASE_URL, APP_SECRET, …)
  api/
    deps.py                # DbSession dependency (injects AsyncSession from request state)
    routes_sources.py      # GET/POST /sources, GET /sources/{id}
    routes_ingestion.py    # POST /ingest/rss/{source_id}, /ingest/url, /ingest/text
    routes_chat.py         # POST /chat/answer
    routes_claims.py       # POST /documents/{id}/extract-claims, GET /claims
  observability/
    run_context.py         # asyncio-safe ContextVars (run_id, document_id, span_id);
                           #   extraction_run(), chat_run(), span_scope(), current_context()
                           #   context managers
    logger.py              # RunContextFilter (injects correlation IDs into log records);
                           #   _JsonFormatter (stdlib JSON output); configure_logging() (idempotent,
                           #   reads LOG_LEVEL / LOG_FORMAT env vars)
    tracer.py              # record_agent_run(), record_span_extraction(), mark_document_timestamp()
                           #   — all fire-and-forget, never raise
  db/
    models.py              # SQLAlchemy ORM models (all 8 tables)
    session.py             # make_engine / make_session_factory helpers
    migrations/
      env.py               # Alembic env wired to DATABASE_URL
      versions/
        0001_initial_schema.py  # All 8 tables + pgvector extension
        0002_observability.py   # Adds correlation ID columns to agent_runs/documents; new span_extractions table
        0003_evaluation.py      # Adds eval_datasets, eval_runs, eval_results tables
  ingestion/
    cleaner.py             # normalize_text, content_hash, normalize_url, extract_text
    rss.py                 # fetch_rss_entries (feedparser + async httpx)
    url_fetcher.py         # fetch_and_clean (httpx + trafilatura)
  intelligence/
    chat.py                # LangGraph chat answer graph (retrieve_spans → load_claims
                           #   → generate_answer → format_result); validates citation labels
                           #   against retrieved context; wraps graph in chat_run context
    llm_client.py          # LLMClient.complete_json — OpenRouter calls, Pydantic validation;
                           #   ExtractedClaim / ExtractionOutput schemas;
                           #   LLMError / LLMNetworkError / LLMSchemaError hierarchy;
                           #   uses tracer.record_agent_run; tracks prompt_tokens / completion_tokens;
                           #   supports run_type for claim extraction and chat answers
    extraction.py          # LangGraph StateGraph (load_spans → extract_spans → store_claims
                           #   → update_status); asyncio.gather concurrency (Semaphore 5);
                           #   correction-prompt retry (max 2); status constants exported;
                           #   wraps graph in extraction_run context; span_scope per span;
                           #   writes span_extractions rows; marks extraction timestamps;
                           #   run_with_context() entry point
    prompts/
      chat_answer.py       # SYSTEM_PROMPT plus question/context prompt builder for grounded chat
      extract_claims.py    # SYSTEM_PROMPT, build_user_prompt, build_correction_prompt
  domain_packs/
    personal_ai_tech.yaml  # Default domain pack definition
  evaluation/
    __init__.py
    datasets.py            # Pydantic schemas (GoldClaim, ClaimExtractionExample,
                           #   SpanRetrievalExample, Dataset); load_dataset(path) with SHA-256 checksum
    metrics.py             # precision_recall_f1, precision_at_k, ndcg_at_k, align_claims (Jaccard greedy)
    judges.py              # ClaimExtractionJudge (active);
                           #   BriefSynthesisJudge, GroundedAnswerJudge (Phase 4 stubs)
    runner.py              # execute_run(*) entry point; SUTConfig / EvalRunResult dataclasses;
                           #   budget gate; per-example error tolerance; Postgres persistence
    meta_eval.py           # compute_kappa, compute_pearson, load_human_labels
    prompts/
      __init__.py
      claim_extraction_judge.py  # JUDGE_SYSTEM_PROMPT, build_judge_prompt(), ClaimPairVerdict model
  cli/
    __init__.py
    config.py              # CLISettings (API_URL, DB_URL, rich/json output flags)
    db.py                  # direct-Postgres readers (asyncpg, short-lived sessions);
                           #   includes list_runs() and show_run()
    http.py                # HTTP wrappers for ingest/search/chat/extract (FastAPI server)
    render.py              # Rich+JSON formatters; includes search/chat/extract and run renderers
    eval.py                # Typer sub-app — nexus eval commands:
                           #   register-dataset, list-datasets, run, show, diff, calibrate
    main.py                # Typer app — nexus console-script entry point;
                           #   registers `runs` sub-app with `list` and `show` commands;
                           #   registers `eval` sub-app
tests/
  conftest.py              # testcontainers fixtures, Alembic migration, per-test DB clean
  test_sources.py          # Source CRUD integration tests (8 tests)
  test_ingestion.py        # Ingestion integration tests (12 tests)
  test_cli_db.py           # CLI DB reader unit tests (8 tests)
  test_chat_api.py         # Chat API integration tests
  test_chat_graph.py       # Chat graph integration tests
  test_cli_render.py       # CLI render/formatter tests
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
-> query answering (hybrid span + claim retrieval, LangGraph, OpenRouter T2)
-> [future] brief synthesis
```

## CLI Access Model

The `nexus` CLI uses a hybrid access strategy:

- **Reads** (status, sources, documents, document detail, runs) go **direct to Postgres** via short-lived asyncpg sessions — no server required.
- **Ingest, extract, search, and chat** go **through the FastAPI server** over HTTP.

`CLISettings` resolves `--api-url` and `--db-url` from flags, `API_BASE_URL` / `DATABASE_URL` env vars, or `.env` defaults. `DATABASE_URL` is required only for commands that read directly from Postgres (status, sources, documents, document, runs); HTTP-only commands (`search`, `chat`, `extract`, `ingest`) work without it. Every command accepts `--json` for machine-readable output and `--api-url` / `--db-url` overrides.

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
| POST | /chat/answer | Hybrid chatbot answer over embedded spans and active extracted claims |
| POST | /documents/{id}/extract-claims | Run claim extraction for a document |
| GET | /claims | List claims (filter by document_id, claim_type, status) |

Supported `source_type` values: `rss`, `manual`, `api`.

### Chat answer endpoint detail

`POST /chat/answer`

Request body:

```json
{
  "question": "What changed in recent open-source LLM releases?",
  "top_k": 8
}
```

| Status | Meaning |
|---|---|
| 200 | Returns `{answer, citations, retrieved_context_count, run_id, tokens_used, cost_estimate_usd}` |
| 422 | Blank question or invalid `top_k` |
| 503 | Embedder not initialised, OpenRouter unavailable, or chat graph failed |

If retrieval finds no usable embedded context, the route returns `200` with the insufficient-evidence answer, empty citations, and zero token usage without making a model call.

Citation safety behavior: the model may reference only retrieved context labels such as `C1`. The API normalizes and validates those labels against retrieved spans, drops unknown labels, and falls back to the insufficient-evidence answer if no valid citations remain.

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
| T1 | Embedding (local) | `settings.t1_model` | `BAAI/bge-small-en-v1.5` |
| T2 | Claim extraction (SUT) + chat answer | `settings.t2_model` | `deepseek/deepseek-v4-flash` |
| T3 | Brief synthesis (Phase 4); LLM judge for eval | `settings.t3_model` | `deepseek/deepseek-v4-pro` |

Cost is tracked per call: `0.30 / 1_000_000 * total_tokens` stored in the `agent_runs.cost_estimate` column.

## Observability

The `app/observability/` package adds structured logging and DB-backed tracing without modifying business logic.

### Correlation IDs (`run_context.py`)

Three asyncio-safe `ContextVar`s — `run_id_var`, `document_id_var`, `span_id_var` — propagate UUIDs through async call stacks without thread-safety concerns. Three context managers control their lifetimes:

| Context manager | Scope | Sets |
|---|---|---|
| `extraction_run(document_id)` | Full extraction graph | `run_id`, `document_id` |
| `chat_run()` | Single chat answer | `run_id` |
| `span_scope(span_id)` | Single span extraction | `span_id` |
| `current_context()` | Any point | Returns `{run_id, document_id, span_id}` snapshot |

### Structured Logging (`logger.py`)

`configure_logging()` is idempotent and called at startup by both `app/main.py` (FastAPI lifespan) and `app/cli/main.py`. It reads two env vars:

| Env var | Values | Default |
|---|---|---|
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |
| `LOG_FORMAT` | `json`, `text` | `json` |

`RunContextFilter` injects `run_id`, `document_id`, and `span_id` from the current `ContextVar` state into every log record, enabling log correlation across the extraction graph without passing IDs through function signatures.

### DB Tracing (`tracer.py`)

Three fire-and-forget functions write audit rows to Postgres. They never raise — failures are swallowed so tracing cannot break the hot path:

| Function | What it writes |
|---|---|
| `record_agent_run(...)` | Upserts `agent_runs` with `run_id`, `document_id`, `span_id`, `prompt_tokens`, `completion_tokens` |
| `record_span_extraction(...)` | Inserts/updates a `span_extractions` row (`status`, `attempts`, `error`) |
| `mark_document_timestamp(field, doc_id)` | Sets one of the four pipeline timestamps on `documents` |

## Evaluation Framework (`app/evaluation/`)

The `app/evaluation/` package implements LLM-as-a-Judge offline evaluation for Nexus pipeline components. It is invoked exclusively through the `nexus eval` CLI — it has no FastAPI routes and is not part of the hot path.

### Data flow

```text
gold YAML
  -> load_dataset()           # validates schema, computes SHA-256
  -> execute_run()            # runner.py: orchestrates SUT + judge
       -> SUT (T2 model)      # calls production claim extraction prompt
       -> ClaimExtractionJudge (T3 model)  # scores each (gold, predicted) claim pair
       -> _persist_result()   # writes eval_results row per example
  -> aggregate_scores         # precision, recall, f1, type_accuracy,
                              #   mean_groundedness, mean_factuality
  -> EvalRun (Postgres)       # persisted for diff and show commands
```

### Judge architecture

`ClaimExtractionJudge` is the only active judge. It uses `align_claims()` (Jaccard greedy matching) to pair gold and predicted claims, then calls the LLM judge for each pair to get a `ClaimPairVerdict` (match_status, groundedness, factuality scores). Deterministic metrics (precision, recall, f1) are computed from the verdicts in `metrics.py`.

`BriefSynthesisJudge` and `GroundedAnswerJudge` are Phase 4 stubs — they exist as class skeletons in `judges.py` but are not callable.

### Gold datasets

Gold-set YAML files live in `evals/gold/`. Each file must be registered with `nexus eval register-dataset` before it can be used in a run.

| File | Task | Examples |
|---|---|---|
| `evals/gold/claim_extraction/ai_tech_v1.yaml` | `claim_extraction` | 30 |
| `evals/gold/span_retrieval/queries_v1.yaml` | `span_retrieval` | 20 |

Human calibration labels for the judge live in `evals/human_labels/claim_extraction.yaml` (6-seed set). Use `nexus eval calibrate` to compute kappa against these.

## Current Boundary

The MVP implements the simplified hierarchy:

```text
Source -> Document -> Span -> Claim -> Brief
```

All 8 core tables are schema-ready (migration 0001). Migration 0002 extends `agent_runs` and `documents` with correlation/timestamp columns and adds `span_extractions`. Migration 0003 adds the 3 eval tables. Phases 1–3 populate `sources`, `documents`, `spans`, `claims`, `claim_evidence`, `agent_runs`, and `span_extractions`. The `eval_*` tables are populated by `nexus eval run`. Brief synthesis is Phase 4+.

The broader PoC hierarchy adds entities, relations, signals, clusters, theses, and decision artefacts. Those remain future-facing until the core ingestion-to-synthesis loop is stable.
