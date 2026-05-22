# Database / Persistence

> **Phase 3 Status: Implemented** — migration 0001 creates all 8 tables; migration 0002 extends `agent_runs` and `documents` with correlation/timestamp columns and adds `span_extractions`. `sources`, `documents`, `spans`, `claims`, `claim_evidence`, `agent_runs`, and `span_extractions` are actively populated by the pipeline.

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
