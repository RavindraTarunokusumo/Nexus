# Database / Persistence

> **Phase B Status: Durable capsule layer landed** — migration 0005 adds 6 new tables (`semantic_capsules`, `capsule_segments`, `semantic_relations`, `theses`, `decision_artefacts`, `domain_packs`). `semantic_capsules` and `capsule_segments` are actively populated by `store_claims` (dual-write) and `nexus capsules backfill`. `semantic_relations`, `theses`, `decision_artefacts`, and `domain_packs` are schema-ready but not yet populated by the pipeline.

The persistence layer is PostgreSQL 16 with the `pgvector` extension. SQLAlchemy 2.x async ORM + asyncpg is used throughout. Alembic manages migrations.

Read [docs/specs/data-model.md](specs/data-model.md) for the full data model spec.

## Connection

Set `DATABASE_URL` in `.env` (or the environment) in asyncpg format:

```
DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5432/nexus
```

The Docker Compose service uses `pgvector/pgvector:pg16` with database/user/password all set to `nexus`.

## Migrations

Migration files live in `app/db/migrations/versions/`. Run with:

```sh
alembic upgrade head
```

| Revision | Description |
|---|---|
| 0001 | Initial schema: all 8 tables + `CREATE EXTENSION IF NOT EXISTS vector` |
| 0002 | Observability: adds `run_id`, `document_id`, `span_id`, `prompt_tokens`, `completion_tokens` to `agent_runs`; adds `chunked_at`, `embedded_at`, `extraction_started_at`, `extraction_completed_at` to `documents`; creates `span_extractions` table |
| 0003 | Evaluation: creates `eval_datasets`, `eval_runs`, `eval_results` tables |
| 0004 | Chat session memory: creates `chat_sessions` and `chat_messages` tables |
| 0005 | Capsule layer: creates `semantic_capsules`, `capsule_segments`, `semantic_relations`, `theses`, `decision_artefacts`, `domain_packs` tables |

## Schema

### `sources`

Registered content origins (RSS feeds, manual pastes, API endpoints).

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| name | TEXT | Display name |
| source_type | TEXT | `rss`, `manual`, or `api` |
| url | TEXT | Unique; nullable for manual sources |
| domain_pack | TEXT | Default: `personal_ai_tech` |
| enabled | BOOLEAN | Default: true |
| credibility_score | FLOAT | 0.0–1.0, default 0.8 |
| created_at | TIMESTAMPTZ | Auto-set |

Indexes: `source_type`, `domain_pack`.

### `documents`

One row per fetched article/page/paste. Deduplication enforced on both `url` (unique) and `content_hash` (unique SHA-256 of normalized text).

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| source_id | UUID | FK → sources (CASCADE) |
| title | TEXT | Nullable |
| url | TEXT | Unique; nullable for text pastes |
| raw_text | TEXT | Original HTML or plain text |
| clean_text | TEXT | Trafilatura-extracted or normalized text |
| content_hash | TEXT | SHA-256 of `normalize_text(clean_text)`, unique |
| published_at | TIMESTAMPTZ | Nullable |
| fetched_at | TIMESTAMPTZ | Auto-set |
| status | TEXT | Pipeline stage: `fetched`, `chunked`, `embedded`, `claims_extracted`, `extraction_partial`, `extraction_failed` |
| chunked_at | TIMESTAMPTZ | Set after chunking completes; nullable |
| embedded_at | TIMESTAMPTZ | Set after embedding completes; nullable |
| extraction_started_at | TIMESTAMPTZ | Set when claim extraction begins; nullable |
| extraction_completed_at | TIMESTAMPTZ | Set when claim extraction finishes; nullable |

Indexes: `source_id`, `status`, `fetched_at`.

### `spans`

Text chunks of a document, with optional 384-dim vector embeddings.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| document_id | UUID | FK → documents (CASCADE) |
| span_index | INTEGER | Ordered position within document |
| text | TEXT | Chunk text |
| token_count | INTEGER | Nullable |
| embedding | vector(384) | BAAI/bge-small-en-v1.5 embeddings; nullable until Phase 2 |
| metadata_json | JSONB | Nullable |

Indexes: `document_id`, `(document_id, span_index)`.

### `claims`

Extracted factual claims linked to a document. Populated by Phase 3 claim extraction.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| document_id | UUID | FK → documents (CASCADE) |
| claim_text | TEXT | |
| claim_type | TEXT | One of the 11 taxonomy values (`model_release`, `benchmark_result`, `product_launch`, `pricing_change`, `research_finding`, `infrastructure_update`, `security_issue`, `funding_event`, `regulation`, `forecast`, `other`) |
| entities_json | JSONB | Nullable |
| topics_json | JSONB | Nullable |
| confidence | FLOAT | Nullable |
| status | TEXT | Default: `active`; may be `rejected` |
| created_at | TIMESTAMPTZ | Auto-set |

Indexes: `document_id`, `status`, `claim_type`.

### `claim_evidence`

Links a claim to supporting span(s). Populated by Phase 3 alongside `claims`.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| claim_id | UUID | FK → claims (CASCADE) |
| span_id | UUID | FK → spans (CASCADE) |
| evidence_role | TEXT | e.g. `support`, `context` |
| quote | TEXT | Nullable excerpt |
| confidence | FLOAT | Nullable |

Indexes: `claim_id`, `span_id`.

### `briefs`

Synthesized summaries grouped by domain pack.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| brief_type | TEXT | |
| title | TEXT | |
| summary | TEXT | Nullable |
| domain_pack | TEXT | |
| created_at | TIMESTAMPTZ | Auto-set |

Indexes: `brief_type`, `domain_pack`, `created_at`.

### `brief_items`

Individual line-items within a brief, each citing claim IDs.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| brief_id | UUID | FK → briefs (CASCADE) |
| title | TEXT | Nullable |
| summary | TEXT | Nullable |
| why_it_matters | TEXT | Nullable |
| confidence | FLOAT | Nullable |
| claim_ids | JSONB | Array of claim UUIDs |

Index: `brief_id`.

### `agent_runs`

Audit log for LLM/agent invocations with cost tracking and correlation IDs. Phase 3 writes one row per LLM call made during claim extraction.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| run_type | TEXT | |
| model | TEXT | Nullable |
| input_json | JSONB | Nullable |
| output_json | JSONB | Nullable |
| cost_estimate | FLOAT | Approximate USD cost (`0.30 / 1_000_000 * total_tokens`) |
| status | TEXT | |
| created_at | TIMESTAMPTZ | Auto-set |
| run_id | UUID | Correlation ID from `extraction_run()` context; nullable |
| document_id | UUID | Correlation ID — which document triggered this run; nullable |
| span_id | UUID | Correlation ID — which span was being processed; nullable |
| prompt_tokens | INTEGER | Token count for the prompt; nullable |
| completion_tokens | INTEGER | Token count for the completion; nullable |

Indexes: `run_type`, `status`, `created_at`.

### `span_extractions`

Per-span extraction audit rows. One row per (run, span) pair written during claim extraction by `tracer.record_span_extraction()`.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| run_id | UUID | FK → agent_runs; nullable |
| span_id | UUID | FK → spans (CASCADE) |
| document_id | UUID | FK → documents (CASCADE) |
| status | TEXT | `pending`, `success`, `failed` |
| attempts | INTEGER | Retry count; default 0 |
| error | TEXT | Last error message if failed; nullable |
| created_at | TIMESTAMPTZ | Auto-set |

Index: `run_id`, `span_id`, `document_id`.

### `eval_datasets`

Registry of gold-set YAML files. One row per registered dataset (name + task + version triple is unique in practice; `register-dataset` upserts on match).

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| name | TEXT | Dataset name (e.g. `ai_tech_v1`) |
| task | TEXT | Task type (`claim_extraction`, `span_retrieval`) |
| version | INTEGER | Schema/dataset version |
| checksum | TEXT | SHA-256 hex of the YAML file contents |
| example_count | INTEGER | Number of examples in the file |
| path | TEXT | Absolute path to the YAML at registration time |
| created_at | TIMESTAMPTZ | Auto-set |

No explicit indexes beyond the primary key.

### `eval_runs`

One row per `nexus eval run` invocation. Records the SUT config, judge config, cost, status, and rolled-up aggregate scores.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| dataset_id | UUID | FK → eval_datasets (RESTRICT — dataset cannot be deleted while runs reference it) |
| sut_model | TEXT | Model used as the system under test |
| sut_prompt_version | TEXT | Git SHA of the SUT prompt at run time |
| judge_name | TEXT | Judge class name (e.g. `ClaimExtractionJudge`) |
| judge_model | TEXT | Model used as the LLM judge |
| judge_prompt_version | TEXT | Git SHA of the judge prompt at run time |
| started_at | TIMESTAMPTZ | Nullable; set when run begins |
| completed_at | TIMESTAMPTZ | Nullable; set when run ends |
| status | TEXT | `pending`, `running`, `completed`, `partial` |
| aggregate_scores | JSONB | Nullable; keys: `precision`, `recall`, `f1`, `type_accuracy`, `mean_groundedness`, `mean_factuality` |
| total_cost_usd | Numeric(12,6) | Accumulated LLM cost in USD; default 0.0 |
| notes | TEXT | Optional free-text note from `--note` flag; nullable |
| created_at | TIMESTAMPTZ | Auto-set |

No explicit indexes beyond the primary key and FK.

### `eval_results`

One row per (run, example) pair. Stores raw SUT output, judge verdict, and deterministic metrics for each example.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| run_id | UUID | FK → eval_runs (CASCADE) |
| example_id | TEXT | Example identifier from the gold YAML |
| sut_output | JSONB | Nullable; `{"claims": [...]}` from the SUT |
| judge_verdict | JSONB | Nullable; full verdict dict from the judge including `per_pair_verdicts` |
| deterministic_metrics | JSONB | Nullable; per-example metric dict (precision, recall, f1, type_accuracy, mean_groundedness, mean_factuality) |
| status | TEXT | `scored` or `error` |
| error_message | TEXT | Nullable; populated on `error` status |
| created_at | TIMESTAMPTZ | Auto-set |

No explicit indexes beyond the primary key and FK.

### `chat_sessions`

One row per multi-turn chat session. The `id` is also the LangGraph `thread_id` used by `AsyncPostgresSaver` for conversation checkpointing.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key; also used as the LangGraph thread_id |
| title | TEXT | Display name; auto-derived from first 60 chars of the opening message; nullable |
| status | TEXT | `active` or `archived`; default `active` |
| created_at | TIMESTAMPTZ | Auto-set |
| updated_at | TIMESTAMPTZ | Updated on each new message |
| archived_at | TIMESTAMPTZ | Set when status transitions to `archived`; nullable |

Indexes: `status`, `created_at`.

### `chat_messages`

One row per user or assistant turn within a session. Both the user message and the assistant reply from a single `POST /chat/sessions/{id}/messages` call are inserted atomically.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| session_id | UUID | FK → chat_sessions (CASCADE) |
| role | TEXT | `user` or `assistant` |
| content | TEXT | Message text |
| run_id | UUID | Correlation ID linking to `agent_runs`; nullable (absent on user messages) |
| citations_json | JSONB | Serialized citation array from the assistant reply; nullable |
| retrieved_context_count | INTEGER | Number of spans retrieved for this turn; nullable |
| prompt_tokens | INTEGER | Nullable; populated on assistant messages |
| completion_tokens | INTEGER | Nullable; populated on assistant messages |
| tokens_used | INTEGER | Total tokens for the turn; nullable |
| cost_estimate_usd | FLOAT | Approximate USD cost for the turn; nullable |
| error | TEXT | Error message if the turn failed; nullable |
| created_at | TIMESTAMPTZ | Auto-set |

Indexes: `session_id`, `created_at`.

### `semantic_capsules`

Durable v0.7 semantic objects. One row per extracted `SemanticObject`, written by `store_claims` (B2 dual-write) or `nexus capsules backfill` (B3). The `idempotency_key` column is UNIQUE and is computed by `build_capsule_idempotency_key` in `app/intelligence/capsules.py`, preventing duplicate capsules from re-extraction or backfill reruns.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| document_id | UUID | FK → documents (CASCADE) |
| idempotency_key | TEXT | UNIQUE; deterministic hash of (document_id, span_index, core_type, claim_text) |
| core_type | TEXT | 15-value CHECK constraint (CoreType Literal) |
| claim_text | TEXT | Canonical claim text |
| salience | FLOAT | Salience score from extraction |
| epistemic_state | TEXT | Epistemic qualifier |
| facets_json | JSONB | Full SemanticObject facets dict |
| embedding | vector(384) | bge-small-en-v1.5 embedding of claim_text; written at ingest time |
| lifecycle_state | TEXT | 9-state CHECK: `active`, `superseded`, `retracted`, … |
| escalation_state | TEXT | 4-state CHECK: `none`, `flagged`, `escalated`, `resolved` |
| created_by_tier | TEXT | `extraction`, `backfill` |
| created_at | TIMESTAMPTZ | Auto-set |

Indexes: `document_id`, `idempotency_key` (unique), `core_type`, `lifecycle_state`.

### `capsule_segments`

Join table linking a `SemanticCapsule` to the `Span`(s) that support it. Populated in the same transaction as `semantic_capsules`. FK cascade on both sides ensures cleanup when a capsule or span is deleted.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| capsule_id | UUID | FK → semantic_capsules (CASCADE) |
| span_id | UUID | FK → spans (CASCADE) |
| role | TEXT | Evidence role (e.g. `support`, `context`) |

Index: `capsule_id`, `span_id`.

### `semantic_relations`

Directed edges between two `SemanticCapsule` rows. Represents the knowledge-graph relation layer. Not yet populated by the pipeline (Phase C+).

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| source_capsule_id | UUID | FK → semantic_capsules |
| target_capsule_id | UUID | FK → semantic_capsules |
| target_thesis_id | UUID | FK → theses; nullable |
| relation_type | TEXT | CHECK constraint on allowed relation types |
| confidence | FLOAT | Nullable |
| rationale | TEXT | Nullable |
| created_at | TIMESTAMPTZ | Auto-set |

### `theses`

Higher-order interpretations built from sets of capsules. Not yet populated by the pipeline (Phase C+).

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| title | TEXT | |
| summary | TEXT | Nullable |
| supporting_capsule_ids | UUID[] | Array of SemanticCapsule UUIDs |
| contradicting_capsule_ids | UUID[] | Array of SemanticCapsule UUIDs |
| created_at | TIMESTAMPTZ | Auto-set |

### `decision_artefacts`

Memos, alerts, and trade-ideas synthesized from theses and capsules. Not yet populated by the pipeline (Phase E+).

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| artefact_type | TEXT | e.g. `memo`, `alert`, `trade_idea` |
| title | TEXT | |
| body | TEXT | Nullable |
| linked_thesis_ids | UUID[] | Array of Thesis UUIDs |
| linked_capsule_ids | UUID[] | Array of SemanticCapsule UUIDs |
| created_at | TIMESTAMPTZ | Auto-set |

### `domain_packs`

Registry table for domain packs. The `parent_pack_id` self-FK supports pack inheritance hierarchies; inheritance resolution is deferred (ADR §8/Q4). Not yet populated by the pipeline — packs are currently loaded from YAML at runtime.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| pack_id | TEXT | UNIQUE; matches the YAML `id` field |
| version | TEXT | Pack schema version (e.g. `3.0`) |
| metadata_json | JSONB | Full pack metadata |
| parent_pack_id | UUID | FK → domain_packs (self-referential); nullable |
| created_at | TIMESTAMPTZ | Auto-set |

## Core Invariant

Accepted generated knowledge must preserve provenance:

```text
brief item -> claim -> span -> document -> source
```

No accepted claim should exist without at least one supporting evidence span (`claim_evidence` row).

## Deduplication

Documents are deduplicated at two levels:

1. **URL uniqueness** — normalized URL (lowercase scheme+host, stripped fragment and trailing slash) must be unique in `documents`.
2. **Content hash uniqueness** — SHA-256 of `normalize_text(clean_text)` must be unique. Two URLs with identical content will produce a skip on the second insert.
