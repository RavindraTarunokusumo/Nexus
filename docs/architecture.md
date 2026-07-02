# Architecture

> **Phase D Status: Capsule retrieval live. `/chat/answer` now retrieves from `semantic_capsules` via HNSW cosine search (migration 0006) with LLM query-intent classification and telos-aware hybrid scoring. Phase C established the reasoning layer — `judge_capsules` and `classify_relations` write `SemanticRelation` rows at extraction time. Phase B established the durable capsule layer (`semantic_capsules` + `capsule_segments`). The Phase C remainder adds manual thesis-clustering (`nexus theses synthesize`) and decision-artefact (`nexus artefacts create`) writers — still with no automatic trigger; Phase E owns lifecycle-driven creation.**

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
    routes_chat.py         # POST /chat/answer; POST /chat/sessions; GET /chat/sessions;
                           #   GET /chat/sessions/{id}; POST /chat/sessions/{id}/messages;
                           #   PATCH /chat/sessions/{id}
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
    models.py              # SQLAlchemy ORM models (all 16 tables + Phase B capsule ORM;
                           #   backrefs: Document.capsules, Span.capsule_segments,
                           #   SemanticCapsule.segments, CapsuleSegment.capsule/span)
    session.py             # make_engine / make_session_factory helpers
    migrations/
      env.py               # Alembic env wired to DATABASE_URL
      versions/
        0001_initial_schema.py  # All 8 tables + pgvector extension
        0002_observability.py   # Adds correlation ID columns to agent_runs/documents; new span_extractions table
        0003_evaluation.py      # Adds eval_datasets, eval_runs, eval_results tables
        0004_chat_sessions.py   # Adds chat_sessions and chat_messages tables
        0005_semantic_capsules.py  # Adds semantic_capsules, capsule_segments, semantic_relations,
                                   #   theses, decision_artefacts, domain_packs tables
        0006_hnsw_capsule_index.py # Adds HNSW index on semantic_capsules.embedding
                                   #   (vector_cosine_ops, m=16, ef_construction=64)
  ingestion/
    cleaner.py             # normalize_text, content_hash, normalize_url, extract_text
    rss.py                 # fetch_rss_entries (feedparser + async httpx)
    url_fetcher.py         # fetch_and_clean (httpx + trafilatura)
  intelligence/
    chat.py                # LangGraph chat answer graph (classify_intent → retrieve_capsules
                           #   → generate_answer → format_result); HNSW cosine search over
                           #   semantic_capsules + telos-aware hybrid scoring (compute_hybrid_score
                           #   — real source_authority/evidence_quality/relation_relevance inputs
                           #   as of Phase D, no longer stubbed); retrieval lifecycle filter is
                           #   active/confirmed/qualified (was active-only); context assembly
                           #   honors pack.context_assembly.include categories (primary /
                           #   counter_evidence / supersession auxiliary blocks, capped 2 each,
                           #   epistemic_note per block) and evidence_strength ordering;
                           #   validates citation labels against retrieved context; wraps graph
                           #   in chat_run context
    lifecycle.py           # Phase E living-knowledge worker: apply_lifecycle_transitions(session,
                           #   domain, pack, dry_run) — deterministic precedence superseded >
                           #   contradicted > qualified > confirmed > stale > archived over
                           #   candidate/active capsules; supersession heuristic restricted to
                           #   core_type="state_change" (events/claims/results stay permanent);
                           #   LifecycleReport(transitions, counts)
    consolidation.py       # Phase E consolidation worker: consolidate_domain(session, domain,
                           #   pack, min_strength, min_cluster_size, dry_run) — thin wrapper over
                           #   theses.synthesize_theses_from_relations; ConsolidationReport
                           #   (theses_created, thesis_ids)
    prompts/classify_intent.py  # IntentClassification model + build_classify_prompt; LLM
                           #   query-intent classification against pack query_intents
    llm_client.py          # LLMClient.complete_json — OpenAI-compatible calls (Qwen Cloud by
                           #   default via settings.llm_base_url/llm_api_key, OpenRouter-compatible),
                           #   Pydantic validation;
                           #   CoreType (15-entry Literal), EpistemicState, SemanticObject,
                           #   SemanticExtractionOutput — v0.7 extraction schemas (production path);
                           #   ExtractedClaim / ExtractionOutput — DELETED in Phase B (legacy eval
                           #   runner ported to SemanticExtractionOutput);
                           #   LLMError / LLMNetworkError / LLMSchemaError hierarchy;
                           #   uses tracer.record_agent_run; tracks prompt_tokens / completion_tokens;
                           #   supports run_type for claim extraction and chat answers
    extraction.py          # LangGraph StateGraph (load_spans → extract_spans → validate_and_project
                           #   → store_claims → judge_capsules → classify_relations → update_status);
                           #   asyncio.gather concurrency (Semaphore 5);
                           #   correction-prompt retry (max 2); status constants exported;
                           #   wraps graph in extraction_run context; span_scope per span;
                           #   writes span_extractions rows; marks extraction timestamps;
                           #   run_with_context() entry point; loads Source + DomainPack per run;
                           #   _resolve_pack_and_source_type: 4-pass classifier (URL domain match →
                           #   title regex → pack fallback → safety net); source_type → v3 profile;
                           #   store_claims dual-writes SemanticCapsule+CapsuleSegment alongside
                           #   Claim+ClaimEvidence in the same transaction (Phase B);
                           #   judge_capsules: T2 quality judge → unary SemanticRelation rows,
                           #   capsule escalation_state update (Phase C);
                           #   classify_relations: T2 same-family pair classifier → binary
                           #   SemanticRelation rows (Phase C);
                           #   _resolve_t2_model(pack, fallback): extracts pack.model_extra["models"]["t2"];
                           #   _capsule_to_obj_for_judge(capsule): reconstructs minimal SemanticObject
                           #   from capsule row; ExtractionState.t2_calls_used: shared T2 budget counter
    capsules.py            # Shared capsule assembly: get_embedder() singleton (bge-small-en-v1.5),
                           #   build_capsule_idempotency_key, build_capsule_row —
                           #   single source of truth for SemanticObject → SemanticCapsule +
                           #   CapsuleSegment mapping; called by store_claims (B2) and
                           #   capsule_from_claim backfill (B3)
    backfill.py            # Phase A → B backfill: reads Claim.entities_json["_v0_7"], constructs
                           #   capsule rows via build_capsule_row; idempotent; batched
    projection.py          # ProjectedClaim dataclass; validate_object, project, enforce_budgets;
                           #   SALIENCE_THRESHOLD = 0.3; maps SemanticObject → legacy Claim+ClaimEvidence
                           #   shape via mvp_claim_type; splits facets into entities_json / topics_json;
                           #   stashes full v0.7 payload under entities_json["_v0_7"] plus _function
                           #   and _domain_family traceability keys
    session_memory.py      # run_session_turn() — LangGraph graph backed by AsyncPostgresSaver;
                           #   thread_id = session_id; _to_psycopg_url(); _derive_title()
    prompts/
      chat_answer.py       # SYSTEM_PROMPT plus question/context prompt builder for grounded chat
      extract_semantic_objects.py  # SYSTEM_PROMPT, build_user_prompt(segment_text, metadata, pack,
                           #   source_type), build_correction_prompt; injects telos, applicable
                           #   semantic-object families, salience rules, facet keys, per-segment
                           #   budgets, and response schema from the domain pack
      judge_semantic_object.py     # SYSTEM_PROMPT, JudgeVerdict schema, build_judge_prompt — T2
                           #   judge for semantic-object quality escalation; wired into graph as
                           #   judge_capsules node (Phase C)
      classify_relations.py        # SYSTEM_PROMPT, RelationClassification schema,
                           #   build_relation_prompt — T2 classifier for same-family capsule pairs;
                           #   wired into graph as classify_relations node (Phase C)
  domain_packs/
    loader.py              # Pydantic v2 loader for v3 (telos-based purpose-grammar) domain packs
    personal_ai_tech.yaml  # Default domain pack — full v3 pack (telos, 10 source-type profiles,
                           #   10 semantic-object families with mvp_claim_type, salience policy,
                           #   relation grammar, epistemic policy, T0–T4 routing, per-source budgets,
                           #   retention windows, retrieval intents + hybrid weights;
                           #   legacy top-level keys preserved for back-compat)
  evaluation/
    __init__.py
    datasets.py            # Pydantic schemas (GoldClaim, ClaimExtractionExample,
                           #   SpanRetrievalExample, Dataset); load_dataset(path) with SHA-256 checksum
    metrics.py             # precision_recall_f1, precision_at_k, ndcg_at_k, align_claims (Jaccard greedy)
    judges.py              # SemanticObjectJudge (active, Phase B — replaces ClaimExtractionJudge);
                           #   BriefSynthesisJudge, GroundedAnswerJudge (Phase 4 stubs)
    runner.py              # execute_run(*) entry point; SUTConfig / EvalRunResult dataclasses;
                           #   budget gate; per-example error tolerance; Postgres persistence;
                           #   response_model=SemanticExtractionOutput (Phase B)
    meta_eval.py           # compute_kappa, compute_pearson, load_human_labels
    prompts/
      __init__.py
  cli/
    __init__.py
    config.py              # CLISettings (API_URL, DB_URL, rich/json output flags)
    db.py                  # direct-Postgres readers (asyncpg, short-lived sessions);
                           #   includes list_runs() and show_run()
    http.py                # HTTP wrappers for ingest/search/chat/extract (FastAPI server)
    render.py              # Rich+JSON formatters; includes search/chat/extract and run renderers
    eval.py                # Typer sub-app — nexus eval commands:
                           #   register-dataset, list-datasets, run (--pack-id, --source-type),
                           #   show, diff, calibrate (--pack-id, --source-type);
                           #   memory run/report (Phase F) — lazy-imports
                           #   scripts.benchmarks.run_memory_benchmark.run_benchmark
    capsules.py            # Typer sub-app — nexus capsules commands:
                           #   backfill [--dry-run] [--batch-size N]
    lifecycle.py           # Typer sub-app — nexus lifecycle run [--domain] [--pack] [--dry-run]
                           #   [--json]; calls app.intelligence.lifecycle.apply_lifecycle_transitions
    consolidation.py       # Typer sub-app — nexus consolidation run --domain [--pack]
                           #   [--min-strength] [--min-cluster-size] [--dry-run] [--json];
                           #   calls app.intelligence.consolidation.consolidate_domain
    main.py                # Typer app — nexus console-script entry point;
                           #   registers `runs` sub-app with `list` and `show` commands;
                           #   registers `eval`, `capsules`, `theses`, `artefacts`, `lifecycle`,
                           #   `consolidation` sub-apps
scripts/
  benchmarks/
    scoring.py              # Pure F5 metric functions: score_answer (per-question), aggregate
                           #   (per-category + overall means, None-excluded, latency p50/p95,
                           #   total tokens) — no I/O
    run_memory_benchmark.py  # async run_benchmark(fixtures, k, out, skip_ingest, domain) — ingest
                           #   corpus.jsonl (idempotent by URL) → extract → classify_relations →
                           #   apply_lifecycle_transitions → consolidate_domain → answer every
                           #   questions.jsonl question via make_chat_graph → score → write
                           #   results.jsonl / report.md / run_meta.json
    demo_answer.py           # Ad-hoc driver: prints live chat answers + citations (role,
                           #   epistemic_note) for a list of questions against a populated DB
evals/
  memory/
    nexus_synthetic/         # Phase F synthetic memory benchmark fixtures: corpus.jsonl
                           #   (14 fictional AI-tech docs), questions.jsonl (22 questions across
                           #   6 categories: timeline, multi_doc, superseded, authority_conflict,
                           #   thesis, abstention), README.md (schema)
tests/
  conftest.py              # testcontainers fixtures, Alembic migration, per-test DB clean
  test_sources.py          # Source CRUD integration tests (8 tests)
  test_ingestion.py        # Ingestion integration tests (12 tests)
  test_cli_db.py           # CLI DB reader unit tests (8 tests)
  test_chat_api.py         # Chat API integration tests
  test_chat_graph.py       # Chat graph integration tests
  test_cli_render.py       # CLI render/formatter tests
  test_cli_e2e.py          # CLI end-to-end integration tests (10 tests)
  domain_packs/
    test_loader.py         # Unit tests for the v3 domain-pack loader (no DB, no LLM)
  db/
    test_capsule_schema.py            # DB-bound: migration 0005 schema + ORM backref integration
  intelligence/
    test_semantic_object_schema.py    # CoreType / SemanticObject / SemanticExtractionOutput schema tests
    test_extract_semantic_objects_prompt.py  # build_user_prompt / build_correction_prompt unit tests
    test_projection.py                # validate_object / project / enforce_budgets unit tests
    test_a6_projection_regression.py  # No-DB no-LLM regression smoke: 5 representative SemanticObjects
                                      #   through the full validate→budgets→project chain using the real
                                      #   personal_ai_tech pack; asserts _v0_7 / _function / _domain_family
    test_judge_semantic_object_prompt.py  # build_judge_prompt / JudgeVerdict unit tests
    test_capsules_dual_write.py       # DB-bound: store_claims dual-writes SemanticCapsule+CapsuleSegment
                                      #   alongside Claim+ClaimEvidence in the same transaction
    test_capsule_backfill.py          # DB-bound: backfill reads _v0_7 stash, writes capsule rows;
                                      #   idempotency via build_capsule_idempotency_key
    test_resolve_pack_and_source_type.py  # No-DB: 4-pass URL/title classifier; spoof-resistance;
                                          #   fallback + safety-net coverage
    test_capsules.py                  # 7 pure unit tests for build_capsule_row (Phase C)
    test_judge_wiring.py              # 6 unit tests for _resolve_t2_model and _capsule_to_obj_for_judge
                                      #   helpers (Phase C)
    test_relation_classification.py   # 9 unit tests: build_relation_prompt, RelationClassification schema,
                                      #   classify_relations node short-circuit / "none" skipping (Phase C)
  test_validation_harness.py          # 5 integration tests @pytest.mark.slow (text ingest, RSS ingest,
                                      #   status, document inspection, semantic search); run against real
                                      #   DB; skipped in fast-unit CI via -m "not slow"
evals/
  gold/
    semantic_objects/
      ai_tech_v3.yaml               # 10 examples, 6 mvp_claim_types — gold set for SemanticObjectJudge
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
-> claim extraction (LangGraph, OpenRouter T2):
     span
     -> _resolve_pack_and_source_type  (4-pass classifier: URL domain → title regex →
                                        pack fallback → safety net "ai_news_article")
     -> semantic-object extraction  (telos-aware prompt + SemanticExtractionOutput,
                                     extract_semantic_objects.py)
     -> validate-and-project        (validate_object → enforce_budgets → project,
                                     projection.py; uses source's domain pack)
     -> store_claims (dual-write, same transaction):
          Claim + ClaimEvidence      (legacy read path; full v0.7 SemanticObject
                                      stashed under entities_json["_v0_7"])
          SemanticCapsule +          (durable Phase B native storage; 384-dim
          CapsuleSegment              embedding written at ingest time via
                                      bge-small-en-v1.5 shared singleton)
     -> judge_capsules (T2, Phase C):
          queries flagged capsules → JudgeVerdict → unary SemanticRelation
          (target_capsule_id=NULL) + capsule escalation_state update;
          respects t2_calls_used budget counter
     -> classify_relations (T2, Phase C):
          groups same-family capsule pairs by object_family → RelationClassification;
          skips "none" results; writes binary SemanticRelation rows
          (target_capsule_id SET); respects remaining T2 budget
-> query answering:
     single-turn  POST /chat/answer  (stateless, no session)
                    -> classify_intent (LLM, against pack query_intents)
                    -> retrieve_capsules (HNSW cosine over semantic_capsules,
                         lifecycle_state='active') + telos-aware hybrid scoring
     multi-turn   POST /chat/sessions/{id}/messages
                    -> run_session_turn() (LangGraph + AsyncPostgresSaver checkpoint)
                    -> persists chat_messages rows (user + assistant) atomically
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
| POST | /chat/answer | Chatbot answer over semantic capsules via HNSW retrieval + telos-aware hybrid scoring (single-turn) |
| POST | /chat/sessions | Create a new chat session |
| GET | /chat/sessions | List sessions (`status`, `limit`, `offset` query params) |
| GET | /chat/sessions/{id} | Session detail with full message transcript |
| POST | /chat/sessions/{id}/messages | Send a user message and receive an assistant reply (persisted atomically) |
| PATCH | /chat/sessions/{id} | Rename or archive a session |
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

Retrieval runs HNSW cosine search over `semantic_capsules` (filtered to `lifecycle_state='active'`), then re-ranks candidates with `compute_hybrid_score` — a telos-aware blend of five active components (semantic similarity, domain object-type match, source authority, recency, salience) plus two stubbed at zero (relation relevance, evidence quality). Component weights come from the active domain pack's `retrieval_policy.hybrid_score_weights`; an LLM `classify_intent` step selects the pack query-intent that supplies retrieval priorities. Score-ranked candidates are then assembled under the pack's declarative token budget (`context_assembly.max_tokens_by_tier["T2"]`, estimated at ~4 chars/token) — `_assemble_within_budget` adds blocks in score order until the budget or `top_k` is reached, always keeping at least the top block; when the pack omits the budget it falls back to the flat `top_k` slice.

Each citation carries `capsule_id`, `document_id`, `document_title`, `url`, `score`, `object_type`, `object_family`, `lifecycle_state`, a `summary` (the capsule text), and `evidence` — the supporting capsule→span excerpts (`span_id`, `span_index`, `text`) drawn from `capsule_segments`, capped per capsule and truncated for display. If retrieval finds no usable capsule embeddings, the route returns `200` with the insufficient-evidence answer, empty citations, and zero token usage without making a model call.

Citation safety behavior: the model may reference only retrieved context labels such as `C1`. The API normalizes and validates those labels against retrieved capsules, drops unknown labels, and falls back to the insufficient-evidence answer if no valid citations remain.

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

Claims are typed using an 11-entry Pydantic `Literal`:

`model_release`, `benchmark_result`, `product_launch`, `pricing_change`, `research_finding`, `infrastructure_update`, `security_issue`, `funding_event`, `regulation`, `forecast`, `other`

As of Phase A, this 11-type list is the **projection target**, not the direct extraction output. The v3 domain pack maps each semantic-object type to one of these values via the `mvp_claim_type` field on each semantic-object family. The production extraction path produces a `SemanticObject` (with `CoreType` from a 15-entry Literal), and the projection layer in `app/intelligence/projection.py` maps it to the legacy `claim_type` column via `mvp_claim_type` from the active domain pack.

As of Phase B, the `claims` + `claim_evidence` tables remain the **read path** (chat retrieval is unchanged until Phase D). The `semantic_capsules` + `capsule_segments` tables are the durable native storage for v0.7 semantic objects written at extraction time. Both paths are populated in the same transaction by `store_claims`. Chat and claim-retrieval endpoints continue to read from `claims`; the capsule tables are populated but not yet served via any API (Phase C/D will add capsule-based retrieval, relations, and lifecycle management).

## LLM Tier Model

As of Phase D/G, T2+ default to **Qwen Cloud** (DashScope, OpenAI-compatible). `LLMClient` takes a `base_url` (default `settings.llm_base_url`); `settings.llm_api_key` resolves to `qwen_cloud_api_key` if set, else `openrouter_api_key` — so a non-Qwen OpenAI-compatible provider still works by leaving `QWEN_CLOUD_API_KEY` unset and pointing `LLM_BASE_URL` elsewhere.

| Tier | Purpose | Config key | Default |
|---|---|---|---|
| T1 | Embedding (local; not yet Qwen-routed — `EMBEDDING_MODEL` is reserved, unused) | `settings.t1_model` | `BAAI/bge-small-en-v1.5` |
| T2 | Telos-aware semantic-object extraction (`extract_semantic_objects.py`) + relation classification (`classify_relations.py`) + chat answer + query-intent classification (`classify_intent.py`) | `settings.t2_model` | `qwen3.6-flash` |
| T3 | Brief synthesis (Phase 4); consolidation (`nexus consolidation run`, default `created_by_tier`); LLM judge for eval | `settings.t3_model` | `qwen3.7-max` |
| T4 | Integrity audits | — | Aspirational |

The T2 prompt is the telos-aware semantic-object prompt (`app/intelligence/prompts/extract_semantic_objects.py`). The legacy `extract_claims.py` prompt was deleted in Phase B; `app/evaluation/runner.py` now uses `SemanticExtractionOutput` and `SemanticObjectJudge`. Capsule embeddings (384-dim) are computed at write time via the T1 `bge-small-en-v1.5` shared singleton in `app/intelligence/capsules.py`; one batched embed call per `store_claims` invocation. As of Phase C, T2 is also used by two reasoning nodes wired into the extraction graph: `judge_capsules` (calls `judge_semantic_object.py`) and `classify_relations` (calls `classify_relations.py`). Both nodes share a single `t2_calls_used` budget counter on `ExtractionState` to limit total T2 spend per run. The per-run T2/T3 model is resolved by `_resolve_t2_model(pack, fallback)` which reads `pack.model_extra["models"]["t2"]` (and `["t3"]`) with fallback to `settings.t2_model`/`t3_model` — **the domain pack's top-level `models:` block, not just `settings`, controls the effective model**; a stale model id there silently overrides the env-configured default (this caused relation classification to 404 against a hardcoded `deepseek/deepseek-v4-flash` in the pack until Phase G fixed it).

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

`SemanticObjectJudge` is the active judge (Phase B replacement for the retired `ClaimExtractionJudge`). It uses the same `align_claims()` (Jaccard greedy matching) approach to pair gold and predicted objects, then calls the LLM judge. Deterministic metrics (precision, recall, f1) are computed in `metrics.py`. The `mvp_claim_type_projection_accuracy` metric (target > 90%, defined in `personal_ai_tech.yaml` `evaluation_contract`) is tracked alongside `type_accuracy`.

`BriefSynthesisJudge` and `GroundedAnswerJudge` are Phase 4 stubs — they exist as class skeletons in `judges.py` but are not callable.

### Gold datasets

Gold-set YAML files live in `evals/gold/`. Each file must be registered with `nexus eval register-dataset` before it can be used in a run.

| File | Task | Examples |
|---|---|---|
| `evals/gold/semantic_objects/ai_tech_v3.yaml` | `semantic_object_extraction` | 10 |
| `evals/gold/span_retrieval/queries_v1.yaml` | `span_retrieval` | 20 |

Human calibration labels for the judge live in `evals/human_labels/claim_extraction.yaml` (6-seed set). Use `nexus eval calibrate --pack-id <id> --source-type <type>` to compute kappa against these.

### Phase A — Dual extraction paths and eval compatibility contract (historical)

Phase A introduced a second extraction path alongside the legacy eval path. Both paths were active simultaneously in Phase A:

- The legacy eval path drove the SUT using `ExtractionOutput` / `ExtractedClaim` schemas; the gold set `evals/gold/claim_extraction/ai_tech_v2.yaml` was the compatibility fixture.
- The production extraction path produced `SemanticExtractionOutput` and stashed full `SemanticObject` payloads under `entities_json["_v0_7"]` as a forward-compat bridge.

**Phase B retired the dual-path eval contract.** `ExtractedClaim`, `ExtractionOutput`, `app/intelligence/prompts/extract_claims.py`, `app/evaluation/prompts/claim_extraction_judge.py`, and `ClaimExtractionJudge` are all deleted. `app/evaluation/runner.py` now uses `SemanticExtractionOutput` and `SemanticObjectJudge` exclusively. The regression smoke test `test_a6_projection_regression.py` remains as a no-DB contract test for the projection layer.

## Current Boundary

The MVP implements the simplified hierarchy:

```text
Source -> Document -> Span -> SemanticObject -> SemanticCapsule (durable, Phase B)
                                              -> Claim (projection, legacy read path)
                                              -> Brief (Phase 4+)
```

As of Phase C, the extraction graph includes two T2 reasoning nodes that actively populate `semantic_relations`. The `claims` + `claim_evidence` tables remain the active read path (chat retrieval, claim listing) pending the deferred cutover. The `semantic_capsules` + `capsule_segments` tables are the durable native storage — capsule retrieval (`/chat/answer`, `nexus chat`) reads exclusively from capsules, not `claims`. `semantic_relations` is populated at extraction time: unary rows (target_capsule_id=NULL) record judge verdicts; binary rows (target_capsule_id SET) record classified capsule-pair relations.

As of Phase D/E (`main` @ `b57d21c`, PR #25), the pipeline is fully wired end to end: **retrieval** (`app/intelligence/chat.py`) assembles context by `pack.context_assembly.include` categories (primary/counter-evidence/supersession blocks + epistemic notes) with real hybrid-score inputs; **lifecycle** (`nexus lifecycle run`) transitions capsules through `active → confirmed/qualified/superseded/stale/archived`; **consolidation** (`nexus consolidation run`) clusters relations into `theses` rows. `theses` and `decision_artefacts` are populated by these workers (no automatic trigger yet — both are explicit CLI invocations, not wired into the extraction graph). See [Phase F benchmark baseline](benchmarks/baseline-2026-07-02.md) for measured behavior on a synthetic corpus (22/22 relations classified, 7–9 theses formed per run).

Migrations: 0001 (8 core tables), 0002 (observability columns + `span_extractions`), 0003 (eval tables), 0004 (`chat_sessions` + `chat_messages`), 0005 (6 capsule-layer tables: `semantic_capsules`, `capsule_segments`, `semantic_relations`, `theses`, `decision_artefacts`, `domain_packs`). All 6 Phase B tables are actively populated as of Phase D/E; `domain_packs` (the registry table, distinct from the YAML pack loader) remains unused.

The broader PoC hierarchy adds entities, relations, signals, clusters, theses, and decision artefacts. Those remain future-facing until the core ingestion-to-synthesis loop is stable.
