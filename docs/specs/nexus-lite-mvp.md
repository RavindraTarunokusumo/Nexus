# Nexus Lite MVP Spec

## Status

Drafted from:

- `nexus_full_mvp_spec_markdown.md`
- `proof_of_concept.md`

The split implementation specs live in:

- [Product](product.md)
- [Architecture](architecture.md)
- [Data Model](data-model.md)
- [Pipeline](pipeline.md)
- [API](api.md)
- [Domain Packs](domain-packs.md)
- [Operations](operations.md)

## Goal

Nexus Lite proves the complete intelligence loop:

```text
source ingestion
-> document normalization
-> span generation
-> claim extraction
-> retrieval
-> synthesis
-> query answering
```

The system is private, VPS-hosted, and optimized for evidence-grounded personal AI/technology intelligence.

## MVP Scope

Build a FastAPI/PostgreSQL/Redis worker application that can:

1. Ingest RSS feeds, manually submitted URLs, and pasted text.
2. Normalize and deduplicate documents.
3. Chunk documents into citeable spans.
4. Generate local embeddings for spans.
5. Extract atomic claims through structured LLM calls.
6. Link each claim to evidence spans.
7. Retrieve spans and claims semantically.
8. Generate evidence-backed daily, weekly, and query briefs.
9. Answer user questions only from retrieved evidence.
10. Log worker, model, token, cost, and failure data.
11. Run the pipeline on a daily schedule.

## Initial Domain

Domain pack: `personal_ai_tech`

Focus:

- AI agents
- LLM releases
- open-source models
- inference infrastructure
- coding agents
- AI tooling
- research papers
- benchmarks
- product announcements
- AI regulation and policy

## Core Objects

```text
Source -> Document -> Span -> Claim -> Brief
```

Operational records are stored in `agent_runs`.

## Evidence Invariant

Every accepted generated statement must be traceable:

```text
brief item -> claim -> span -> document/source
```

Claims without supporting spans are invalid.

## Recommended Stack

| Layer | Technology |
|---|---|
| API | FastAPI |
| Database | PostgreSQL |
| Vector search | pgvector |
| Queue | Redis |
| Workers | Celery or RQ |
| Scheduler | APScheduler or cron |
| Embeddings | sentence-transformers |
| LLM provider | OpenRouter |
| Deployment | Docker Compose |
| Hosting | Private VPS |

## Phases

1. Ingestion: clean documents from at least 5 sources.
2. Retrieval foundation: semantic search returns relevant spans.
3. Claim extraction: claims are extracted and linked to spans.
4. Brief generation: readable evidence-backed briefs are generated.
5. Query answering: grounded questions are answered from retrieved evidence.
6. Scheduling: the pipeline runs automatically every day.

## Non-Goals

Deferred until the core loop is stable:

- thesis lifecycle management
- signal/event clustering
- multimodal figure extraction
- trading execution
- multi-user SaaS
- advanced dashboard UI
- public deployment
- integrity audits
- chat integrations
- OpenClaw or NanoClaw orchestration
- distributed infrastructure

## Acceptance Criteria

The MVP is accepted when it can:

1. ingest multiple sources
2. store normalized documents with provenance
3. generate spans and embeddings
4. extract grounded claims
5. retrieve semantically relevant evidence
6. synthesize useful briefs
7. answer grounded questions with source links
8. log operational activity and model costs
9. run autonomously on a private VPS
