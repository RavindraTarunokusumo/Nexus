# Database / Persistence

> **Phase 1 Status: Implemented** — all 8 tables created by migration 0001; `sources` and `documents` are actively populated by the ingestion API.

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
| status | TEXT | Default: `fetched` |

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

Extracted factual claims linked to a document.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| document_id | UUID | FK → documents (CASCADE) |
| claim_text | TEXT | |
| claim_type | TEXT | |
| entities_json | JSONB | Nullable |
| topics_json | JSONB | Nullable |
| confidence | FLOAT | Nullable |
| status | TEXT | Default: `active` |
| created_at | TIMESTAMPTZ | Auto-set |

Indexes: `document_id`, `status`, `claim_type`.

### `claim_evidence`

Links a claim to supporting span(s).

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

Audit log for LLM/agent invocations with cost tracking.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| run_type | TEXT | |
| model | TEXT | Nullable |
| input_json | JSONB | Nullable |
| output_json | JSONB | Nullable |
| cost_estimate | FLOAT | Nullable |
| status | TEXT | |
| created_at | TIMESTAMPTZ | Auto-set |

Indexes: `run_type`, `status`, `created_at`.

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
