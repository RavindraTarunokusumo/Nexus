# Product Spec

## Project

Nexus is a private agentic AI environment for turning heterogeneous information sources into structured, evidence-grounded knowledge.

The first implementation target is **Nexus Lite**, an MVP that validates the complete intelligence loop before the broader Nexus architecture is built.

## Vision

Nexus should behave like a continually learning research substrate. It ingests external material, structures it into layered knowledge, retrieves relevant evidence before synthesis, and produces traceable briefs or answers that can always be followed back to source material.

## MVP Goal

Build a private, VPS-hosted system that can:

1. Ingest RSS feeds, manually submitted URLs, and pasted text.
2. Normalize and store source documents.
3. Split documents into citeable spans.
4. Generate embeddings for semantic retrieval.
5. Extract atomic, evidence-backed claims.
6. Link claims to their supporting spans.
7. Retrieve spans and claims for user queries.
8. Generate daily or query-driven intelligence briefs.
9. Answer questions only from retrieved evidence.
10. Log model calls, worker activity, failures, and cost estimates.
11. Run the ingestion-to-brief loop on a schedule.

## Initial Domain

The MVP domain pack is `personal_ai_tech`: a personal AI and technology analyst.

Initial topics:

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

Initial source types:

- RSS feeds
- manually submitted URLs
- pasted text

## Users

The initial user is a single technical operator running Nexus privately. Multi-user roles, public access, and SaaS packaging are out of scope.

## Principles

**Evidence first.** Generated outputs must be traceable through:

```text
brief item -> claim -> span -> document/source
```

**Layered knowledge.** The MVP uses Source, Document, Span, Claim, Brief, and Agent Run layers. The broader PoC extends this to entities, relations, signals, clusters, theses, and decision artefacts.

**Retrieval before synthesis.** Synthesis and query answering must use retrieved evidence, not unsupported model prior knowledge.

**Structured outputs.** Extraction and synthesis should use JSON schemas, validation, retries, deterministic prompts, and logged failures.

**Cheap first.** Prefer deterministic logic, SQL, local embeddings, and cheap structured calls before expensive reasoning calls.

## MVP Non-Goals

The MVP does not include:

- full thesis lifecycle management
- signal and event clustering
- multimodal figure extraction
- autonomous trading execution
- multi-user SaaS support
- advanced dashboard UI
- public deployment
- fine-tuned local reasoning models
- knowledge integrity audits
- Telegram or WhatsApp integration
- OpenClaw or NanoClaw orchestration
- ontology graph editor
- distributed infrastructure

## MVP Success Criteria

The MVP is successful when it can:

1. Ingest multiple sources.
2. Store normalized documents with provenance.
3. Create spans and embeddings.
4. Extract claims linked to evidence spans.
5. Retrieve semantically relevant evidence.
6. Generate useful evidence-backed daily briefs.
7. Answer grounded user queries with source links.
8. Log operational and model activity.
9. Run automatically on a VPS.

## Expansion Path

After MVP validation, Nexus can expand toward the PoC architecture:

- entities and relations
- signals, clusters, timelines, and theses
- contradiction analysis
- graph relationships
- multimodal figure extraction
- domain expansion
- OpenClaw or NanoClaw orchestration
- integrity audits
- local model specialization
- autonomous research loops
