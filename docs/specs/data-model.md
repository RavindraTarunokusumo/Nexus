# Data Model Spec

## MVP Persistence Model

The MVP needs eight core tables:

- `sources`
- `documents`
- `spans`
- `claims`
- `claim_evidence`
- `briefs`
- `brief_items`
- `agent_runs`

All primary IDs should be UUIDs. Timestamps should use timezone-aware UTC values.

## Sources

Stores source definitions and ingestion settings.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `name` | TEXT | Human-readable source name |
| `source_type` | TEXT | `rss`, `manual`, `api`; MVP supports `rss`, `manual`, pasted text |
| `url` | TEXT | Source URL, nullable for pasted text |
| `domain_pack` | TEXT | Initial value: `personal_ai_tech` |
| `enabled` | BOOLEAN | Controls scheduled ingestion |
| `credibility_score` | REAL | Rule-based source trust estimate |
| `created_at` | TIMESTAMP | Creation time |

## Documents

Stores fetched and normalized content.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `source_id` | UUID | FK to `sources.id` |
| `title` | TEXT | Document title |
| `url` | TEXT | Original URL |
| `raw_text` | TEXT | Raw fetched content |
| `clean_text` | TEXT | Normalized text used downstream |
| `content_hash` | TEXT | Deduplication key |
| `published_at` | TIMESTAMP | Source publication date |
| `fetched_at` | TIMESTAMP | Ingestion timestamp |
| `status` | TEXT | Pipeline status |

## Spans

Stores citeable semantic chunks.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `document_id` | UUID | FK to `documents.id` |
| `span_index` | INTEGER | Stable document order |
| `text` | TEXT | Span text |
| `token_count` | INTEGER | Estimated token count |
| `embedding` | VECTOR | pgvector embedding |
| `metadata_json` | JSONB | Title, source, publication date, domain pack, extra anchors |

Span rules:

- preserve semantic coherence
- preserve local context
- stay small enough for retrieval
- maintain deterministic ordering
- default size: 400-800 tokens
- default overlap: 50-100 tokens
- maximum size: 1000 tokens

## Claims

Stores atomic extracted propositions.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `document_id` | UUID | FK to `documents.id` |
| `claim_text` | TEXT | One supported proposition |
| `claim_type` | TEXT | Initial taxonomy value |
| `entities_json` | JSONB | Extracted entities |
| `topics_json` | JSONB | Topic tags |
| `confidence` | REAL | Extraction confidence |
| `status` | TEXT | `active`, `rejected`, etc. |
| `created_at` | TIMESTAMP | Creation time |

Every claim must:

- express one proposition
- be independently understandable
- map to at least one evidence span
- avoid unsupported inference
- avoid hallucinated facts

Initial claim types:

- `model_release`
- `benchmark_result`
- `product_launch`
- `pricing_change`
- `research_finding`
- `infrastructure_update`
- `security_issue`
- `funding_event`
- `regulation`
- `forecast`
- `other`

## Claim Evidence

Links claims to spans.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `claim_id` | UUID | FK to `claims.id` |
| `span_id` | UUID | FK to `spans.id` |
| `evidence_role` | TEXT | `support` or `context` |
| `quote` | TEXT | Supporting quote |
| `confidence` | REAL | Evidence confidence |

Invariant: no accepted claim should exist without at least one `support` evidence row.

## Briefs

Stores synthesized reports.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `brief_type` | TEXT | `daily`, `weekly`, `query` |
| `title` | TEXT | Brief title |
| `summary` | TEXT | Executive summary |
| `domain_pack` | TEXT | Domain |
| `created_at` | TIMESTAMP | Generation time |

## Brief Items

Stores brief sections and evidence links.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `brief_id` | UUID | FK to `briefs.id` |
| `title` | TEXT | Section title |
| `summary` | TEXT | Item summary |
| `why_it_matters` | TEXT | Contextual interpretation |
| `confidence` | REAL | Synthesis confidence |
| `claim_ids` | JSONB | Linked claim IDs |

## Agent Runs

Stores operational logs for reproducibility, debugging, and cost monitoring.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `run_type` | TEXT | `extraction`, `query`, `brief`, etc. |
| `model` | TEXT | Model used |
| `input_json` | JSONB | Request payload |
| `output_json` | JSONB | Response payload |
| `cost_estimate` | REAL | Estimated cost |
| `status` | TEXT | `success` or failure state |
| `created_at` | TIMESTAMP | Execution time |

## Deduplication

MVP deduplication should prioritize exact matching:

1. Normalize URL and check for existing document.
2. Hash normalized content and check for duplicate content.
3. Defer semantic similarity deduplication until retrieval is stable.

## Future PoC Data Model

The broader PoC adds:

- entities
- relations
- signals
- clusters
- theses
- causal chains
- decision artefacts
- claim/signal enriched embeddings
- lifecycle storage tiers
- consolidation logs

These are not MVP requirements, but MVP names and provenance rules should not conflict with them.
