# Nexus Lite — Full MVP Specification

Status: Draft  
Spec path: `docs/specs/nexus-lite-mvp.md`  
Related document: `proof_of_concept.md`  
Accepted by: TBD  
Accepted date: TBD

---

# 1. Overview

## Goal

Nexus Lite is the first functional implementation of the broader Nexus architecture described in `proof_of_concept.md`.

The MVP focuses on proving the complete intelligence loop:

```text
source ingestion
→ document normalization
→ span generation
→ claim extraction
→ retrieval
→ synthesis
→ query answering
```

The system is designed as a private, VPS-hosted research environment that converts heterogeneous information sources into structured, evidence-grounded knowledge.

The MVP intentionally avoids the full complexity of the long-term Nexus architecture while preserving its core principles:

- evidence-grounded reasoning;
- layered knowledge representation;
- reversible provenance;
- structured extraction;
- retrieval-first synthesis;
- domain-adaptable intelligence.

---

# 2. Objectives

The MVP must:

1. Ingest and normalize information from external sources.
2. Store source provenance and cleaned documents.
3. Generate citeable spans from documents.
4. Extract atomic claims from spans using LLMs.
5. Link claims back to evidence spans.
6. Support semantic retrieval over spans and claims.
7. Generate synthesized intelligence briefs.
8. Answer user questions through retrieval-augmented generation.
9. Log all agent/model activity.
10. Operate autonomously on a schedule.

---

# 3. Non-Goals

The MVP does NOT include:

- full thesis lifecycle management;
- signal/event clustering;
- multimodal figure extraction;
- autonomous trading execution;
- multi-user SaaS support;
- advanced dashboard UI;
- public deployment;
- fine-tuned local reasoning models;
- knowledge integrity audits;
- Telegram or WhatsApp integration;
- OpenClaw or NanoClaw orchestration;
- ontology graph editor;
- distributed infrastructure.

These features are deferred until the core ingestion-to-synthesis loop is stable.

---

# 4. Core Design Principles

## 4.1 Evidence First

Every synthesized output must be traceable to:

```text
brief item
→ claims
→ spans
→ document
→ source
```

No generated statement should exist without provenance.

---

## 4.2 Layered Knowledge

The MVP uses a simplified subset of the full Nexus hierarchy:

| Layer | Purpose |
|---|---|
| Source | Origin metadata and ingestion tracking |
| Document | Clean normalized content |
| Span | Citeable semantic chunks |
| Claim | Atomic evidence-grounded propositions |
| Brief | Synthesized higher-order output |

---

## 4.3 Retrieval Before Synthesis

The system must retrieve relevant spans and claims before generating outputs.

LLMs should synthesize from retrieved evidence rather than relying on prior world knowledge.

---

## 4.4 Structured Outputs

All extraction and synthesis operations should use:

- JSON schema outputs;
- validation;
- retry logic;
- deterministic prompts.

---

## 4.5 Cheap First

Operations should follow a simplified tiered reasoning model:

| Tier | Purpose |
|---|---|
| T0 | deterministic logic |
| T1 | local embeddings/search |
| T2 | cheap structured extraction |
| T3 | higher-quality synthesis/reasoning |

The MVP should minimize expensive frontier calls.

---

# 5. Initial Domain

## Personal AI/Tech Intelligence

The MVP's first domain pack is a personal AI and technology analyst.

### Initial Topics

- AI agents
- LLM releases
- open-source models
- inference infrastructure
- coding agents
- AI tooling
- research papers
- model benchmarks
- AI product announcements
- AI regulation and policy

### Initial Source Types

- RSS feeds
- manually submitted URLs
- pasted text

---

# 6. System Architecture

## 6.1 High-Level Flow

```text
external source
→ ingestion
→ document cleaner
→ chunking
→ embeddings
→ claim extraction
→ retrieval index
→ brief synthesis
→ query answering
```

---

## 6.2 Recommended Stack

| Layer | Technology |
|---|---|
| API Backend | FastAPI |
| Database | PostgreSQL |
| Vector Search | pgvector |
| Queue | Redis |
| Workers | Celery or RQ |
| Scheduling | APScheduler or cron |
| Embeddings | sentence-transformers |
| LLM Gateway | OpenRouter |
| Deployment | Docker Compose |
| Hosting | Private VPS |

---

# 7. Repository Structure

```text
nexus-lite/
│
├── app/
│   ├── main.py
│   ├── config.py
│   │
│   ├── api/
│   │   ├── routes_sources.py
│   │   ├── routes_documents.py
│   │   ├── routes_claims.py
│   │   ├── routes_briefs.py
│   │   └── routes_query.py
│   │
│   ├── db/
│   │   ├── models.py
│   │   ├── session.py
│   │   └── migrations/
│   │
│   ├── ingestion/
│   │   ├── rss.py
│   │   ├── url_fetcher.py
│   │   ├── cleaner.py
│   │   └── chunker.py
│   │
│   ├── intelligence/
│   │   ├── llm_client.py
│   │   ├── extraction.py
│   │   ├── synthesis.py
│   │   ├── retrieval.py
│   │   └── prompts/
│   │
│   ├── workers/
│   │   ├── tasks.py
│   │   └── scheduler.py
│   │
│   └── domain_packs/
│       └── personal_ai_tech.yaml
│
├── docker-compose.yml
├── .env.example
├── README.md
└── PLAN.md
```

---

# 8. Database Specification

## 8.1 Sources Table

Stores source definitions.

| Column | Type | Description |
|---|---|---|
| id | UUID | primary key |
| name | TEXT | source name |
| source_type | TEXT | rss/manual/api |
| url | TEXT | source URL |
| domain_pack | TEXT | active domain pack |
| enabled | BOOLEAN | ingestion enabled |
| credibility_score | REAL | source trust estimate |
| created_at | TIMESTAMP | creation time |

---

## 8.2 Documents Table

Stores raw and cleaned documents.

| Column | Type | Description |
|---|---|---|
| id | UUID | primary key |
| source_id | UUID | FK to source |
| title | TEXT | document title |
| url | TEXT | original URL |
| raw_text | TEXT | raw content |
| clean_text | TEXT | normalized content |
| content_hash | TEXT | deduplication hash |
| published_at | TIMESTAMP | publication date |
| fetched_at | TIMESTAMP | ingestion date |
| status | TEXT | pipeline status |

---

## 8.3 Spans Table

Stores semantic chunks.

| Column | Type | Description |
|---|---|---|
| id | UUID | primary key |
| document_id | UUID | FK to document |
| span_index | INTEGER | ordering |
| text | TEXT | span text |
| token_count | INTEGER | token estimate |
| embedding | VECTOR | pgvector embedding |
| metadata_json | JSONB | extra metadata |

---

## 8.4 Claims Table

Stores atomic extracted claims.

| Column | Type | Description |
|---|---|---|
| id | UUID | primary key |
| document_id | UUID | FK to document |
| claim_text | TEXT | atomic proposition |
| claim_type | TEXT | taxonomy type |
| entities_json | JSONB | extracted entities |
| topics_json | JSONB | topical tags |
| confidence | REAL | extraction confidence |
| status | TEXT | active/rejected/etc |
| created_at | TIMESTAMP | creation date |

---

## 8.5 Claim Evidence Table

Links claims to spans.

| Column | Type | Description |
|---|---|---|
| id | UUID | primary key |
| claim_id | UUID | FK to claim |
| span_id | UUID | FK to span |
| evidence_role | TEXT | support/context |
| quote | TEXT | supporting quote |
| confidence | REAL | evidence confidence |

---

## 8.6 Briefs Table

Stores synthesized reports.

| Column | Type | Description |
|---|---|---|
| id | UUID | primary key |
| brief_type | TEXT | daily/weekly/query |
| title | TEXT | brief title |
| summary | TEXT | executive summary |
| domain_pack | TEXT | domain |
| created_at | TIMESTAMP | generation time |

---

## 8.7 Brief Items Table

Stores brief sections.

| Column | Type | Description |
|---|---|---|
| id | UUID | primary key |
| brief_id | UUID | FK to brief |
| title | TEXT | section title |
| summary | TEXT | item summary |
| why_it_matters | TEXT | contextual explanation |
| confidence | REAL | synthesis confidence |
| claim_ids | JSONB | linked claims |

---

## 8.8 Agent Runs Table

Stores operational logs.

| Column | Type | Description |
|---|---|---|
| id | UUID | primary key |
| run_type | TEXT | extraction/query/etc |
| model | TEXT | model used |
| input_json | JSONB | request payload |
| output_json | JSONB | response payload |
| cost_estimate | REAL | estimated cost |
| status | TEXT | success/failure |
| created_at | TIMESTAMP | execution time |

This table is critical for:

- debugging;
- evaluation;
- prompt refinement;
- future fine-tuning;
- cost monitoring.

---

# 9. Ingestion System

## 9.1 Supported Ingestion Types

| Type | Supported |
|---|---|
| RSS feed | Yes |
| Manual URL | Yes |
| Pasted text | Yes |
| API source | Deferred |
| PDF ingestion | Deferred |
| YouTube transcripts | Deferred |

---

## 9.2 Ingestion Pipeline

```text
fetch source
→ clean text
→ deduplicate
→ chunk into spans
→ generate embeddings
→ extract claims
→ store evidence links
→ update retrieval index
→ synthesize brief
```

---

## 9.3 Deduplication

Documents should be deduplicated by:

- normalized URL;
- content hash;
- semantic similarity threshold.

The MVP should initially prioritize exact matching.

---

# 10. Chunking and Span Generation

## 10.1 Span Rules

Spans should:

- preserve semantic coherence;
- preserve local context;
- remain small enough for retrieval;
- maintain deterministic ordering.

### Recommended Defaults

| Parameter | Value |
|---|---|
| chunk size | 400–800 tokens |
| overlap | 50–100 tokens |
| max chunk size | 1000 tokens |

---

## 10.2 Span Metadata

Each span should store:

- document title;
- source name;
- publication date;
- chunk index;
- token count;
- domain pack.

---

# 11. Embedding System

## 11.1 Embedding Model

Initial recommendation:

- `BAAI/bge-small-en-v1.5`

Alternative:

- `all-MiniLM-L6-v2`

Embeddings should run locally.

---

## 11.2 Vector Storage

Use pgvector.

### Retrieval Targets

The MVP should support:

- span semantic search;
- claim semantic search;
- hybrid keyword + vector retrieval later.

---

# 12. Claim Extraction System

## 12.1 Goal

Convert spans into atomic evidence-grounded claims.

---

## 12.2 Claim Requirements

Every claim must:

- express one proposition;
- remain understandable independently;
- reference evidence spans;
- avoid unsupported inference;
- avoid hallucinated facts.

---

## 12.3 Claim Types

Initial taxonomy:

| Claim Type | Description |
|---|---|
| model_release | model launch/update |
| benchmark_result | quantitative benchmark |
| product_launch | new tool/product |
| pricing_change | pricing modification |
| research_finding | scientific claim |
| infrastructure_update | infra/system news |
| security_issue | vulnerability/security issue |
| funding_event | funding/acquisition |
| regulation | policy/regulation |
| forecast | prediction/speculation |
| other | fallback |

---

## 12.4 Extraction Schema

```json
{
  "type": "object",
  "properties": {
    "claims": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "claim_text": { "type": "string" },
          "claim_type": { "type": "string" },
          "entities": {
            "type": "array",
            "items": { "type": "string" }
          },
          "topics": {
            "type": "array",
            "items": { "type": "string" }
          },
          "evidence_span_ids": {
            "type": "array",
            "items": { "type": "string" }
          },
          "confidence": { "type": "number" },
          "rationale": { "type": "string" }
        },
        "required": [
          "claim_text",
          "claim_type",
          "entities",
          "topics",
          "evidence_span_ids",
          "confidence",
          "rationale"
        ]
      }
    }
  },
  "required": ["claims"]
}
```

---

## 12.5 Extraction Rules

Prompt constraints:

```text
Extract only claims directly supported by the text.
Each claim must map to one or more evidence spans.
Prefer fewer high-quality claims.
Do not use outside knowledge.
Do not summarize entire documents.
```

---

# 13. Retrieval System

## 13.1 Query Flow

```text
user query
→ query embedding
→ retrieve spans + claims
→ rerank
→ synthesis prompt
→ grounded answer
```

---

## 13.2 Retrieval Targets

Initial retrieval types:

| Type | Purpose |
|---|---|
| span retrieval | context reconstruction |
| claim retrieval | precise proposition retrieval |

---

## 13.3 Initial Search Features

Supported:

- semantic search;
- top-k retrieval;
- source filtering;
- date filtering.

Deferred:

- hybrid BM25 + vector fusion;
- reranking models;
- graph retrieval;
- contradiction search.

---

# 14. Brief Synthesis

## 14.1 Goal

Generate readable intelligence summaries from claims.

---

## 14.2 Brief Types

| Type | Description |
|---|---|
| daily | daily developments |
| weekly | longer synthesis |
| query | user-requested synthesis |

---

## 14.3 Brief Structure

Each brief should contain:

1. Executive summary.
2. Major developments.
3. Research updates.
4. Tooling/products.
5. Watch-next items.

---

## 14.4 Synthesis Rules

The synthesizer must:

- synthesize from claims;
- cite supporting claims;
- separate fact from interpretation;
- preserve uncertainty;
- avoid unsupported speculation.

---

## 14.5 Brief Output Schema

```json
{
  "title": "string",
  "executive_summary": "string",
  "items": [
    {
      "section": "string",
      "headline": "string",
      "what_happened": "string",
      "why_it_matters": "string",
      "claim_ids": ["string"],
      "confidence": 0.0,
      "watch_next": "string"
    }
  ]
}
```

---

# 15. Query Answering

## 15.1 Goal

Allow the user to ask grounded questions over the stored knowledge base.

---

## 15.2 Query Flow

```text
user question
→ retrieve spans and claims
→ build evidence context
→ T3 synthesis
→ grounded answer with references
```

---

## 15.3 Query Constraints

The system must:

- answer only from retrieved evidence;
- acknowledge uncertainty;
- avoid fabricated claims;
- provide source links.

---

# 16. Domain Pack Specification

## 16.1 Purpose

Domain packs configure extraction and synthesis behavior.

---

## 16.2 Initial MVP Format

Simple YAML configuration.

Example:

```yaml
id: personal_ai_tech
name: Personal AI Technology Analyst

topics:
  - AI agents
  - open-source LLMs
  - inference infrastructure

claim_types:
  - model_release
  - benchmark_result
  - product_launch

brief_sections:
  - top_developments
  - research_updates
  - tools_and_repos

models:
  t2: openrouter-cheap-model
  t3: openrouter-strong-model
```

---

# 17. LLM Gateway

## 17.1 Requirements

The MVP should implement one reusable LLM client.

Responsibilities:

- OpenRouter communication;
- schema validation;
- retries;
- token tracking;
- logging;
- cost estimation.

---

## 17.2 Suggested Interface

```python
class LLMClient:
    def complete_json(
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: dict,
        temperature: float = 0.1,
        max_tokens: int = 2000,
    ) -> dict:
        ...
```

---

# 18. Scheduling and Automation

## 18.1 Daily Schedule

Recommended default:

```text
07:00 UTC
→ ingest new documents
→ process pipeline
→ generate daily brief
```

---

## 18.2 Worker Jobs

| Job | Purpose |
|---|---|
| fetch_source | ingest content |
| clean_document | normalize text |
| chunk_document | create spans |
| embed_spans | create embeddings |
| extract_claims | claim extraction |
| generate_brief | synthesis |
| answer_query | retrieval answering |

---

# 19. API Specification

## 19.1 Sources

```text
POST /sources
GET  /sources
```

---

## 19.2 Ingestion

```text
POST /ingest/rss/{source_id}
POST /ingest/url
POST /ingest/text
```

---

## 19.3 Documents

```text
GET /documents
GET /documents/{document_id}
```

---

## 19.4 Claims

```text
GET /claims
POST /documents/{document_id}/extract-claims
```

---

## 19.5 Briefs

```text
POST /briefs/generate
GET  /briefs
GET  /briefs/{brief_id}
```

---

## 19.6 Query

```text
POST /query
```

Request:

```json
{
  "question": "What changed this week in open-source LLMs?"
}
```

---

# 20. Security and Deployment

## 20.1 Initial Deployment Model

The MVP should remain private.

Recommended:

- VPS only;
- SSH access;
- reverse proxy;
- HTTPS;
- basic authentication;
- restricted firewall.

---

## 20.2 Docker Compose Services

```text
app
worker
scheduler
postgres
redis
```

---

## 20.3 Environment Variables

```env
DATABASE_URL=
REDIS_URL=
OPENROUTER_API_KEY=
OPENROUTER_T2_MODEL=
OPENROUTER_T3_MODEL=
EMBEDDING_MODEL=
APP_SECRET=
```

---

# 21. Logging and Observability

## 21.1 Required Logs

The MVP must log:

- ingestion failures;
- extraction failures;
- schema violations;
- model calls;
- token usage;
- query execution;
- worker errors.

---

## 21.2 Metrics

Initial metrics:

| Metric | Purpose |
|---|---|
| documents ingested/day | ingestion health |
| extraction success rate | extraction quality |
| average claims/document | extraction density |
| query latency | retrieval performance |
| token usage/day | cost monitoring |
| brief generation time | synthesis performance |

---

# 22. Build Phases

## Phase 1 — Ingestion

Implement:

- FastAPI app;
- database schema;
- RSS ingestion;
- manual URL ingestion;
- cleaner.

Acceptance:

```text
The system stores clean documents from at least 5 sources.
```

---

## Phase 2 — Retrieval Foundation

Implement:

- chunking;
- embeddings;
- pgvector search.

Acceptance:

```text
Semantic search returns relevant spans.
```

---

## Phase 3 — Claim Extraction

Implement:

- OpenRouter client;
- structured extraction;
- evidence linking.

Acceptance:

```text
Claims are extracted and linked to spans.
```

---

## Phase 4 — Brief Generation

Implement:

- synthesis pipeline;
- daily brief creation.

Acceptance:

```text
The system generates readable evidence-backed briefs.
```

---

## Phase 5 — Query Answering

Implement:

- retrieval QA endpoint;
- grounded synthesis.

Acceptance:

```text
The system answers evidence-grounded questions.
```

---

## Phase 6 — Scheduling and Automation

Implement:

- scheduler;
- recurring daily runs.

Acceptance:

```text
The pipeline runs automatically every day.
```

---

# 23. Success Criteria

The MVP is successful when it can:

1. ingest multiple sources;
2. normalize and store documents;
3. generate spans and embeddings;
4. extract grounded claims;
5. retrieve semantically relevant evidence;
6. synthesize useful daily briefs;
7. answer grounded user queries;
8. log all operational activity;
9. run autonomously on a VPS.

---

# 24. Future Expansion

After MVP validation, future work may include:

- multimodal figure extraction;
- thesis layer;
- contradiction analysis;
- signal/event clustering;
- graph relationships;
- domain expansion;
- Indonesia Monitor;
- OpenClaw orchestration;
- agentic workflows;
- integrity audits;
- local model specialization;
- autonomous research loops.

---

# 25. Guiding Principle

The MVP should optimize for:

```text
clarity
reliability
traceability
incremental usefulness
```

The goal is not to build the final Nexus platform immediately.

The goal is to validate the operational intelligence loop:

```text
ingest
→ structure
→ extract
→ retrieve
→ synthesize
→ answer
```

Once that loop is stable, the system can evolve toward the broader architecture described in `proof_of_concept.md`.

