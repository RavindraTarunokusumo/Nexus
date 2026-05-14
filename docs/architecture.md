# Architecture

The implementation target is Nexus Lite: a private FastAPI application with background workers, PostgreSQL plus pgvector, Redis, local embeddings, and an LLM gateway.

Read [docs/specs/architecture.md](specs/architecture.md) for the full architecture spec.

## Runtime Flow

```text
external source
-> ingestion
-> document cleaner
-> chunking
-> embeddings
-> claim extraction
-> retrieval index
-> brief synthesis
-> query answering
```

## Current Boundary

The MVP implements the simplified hierarchy:

```text
Source -> Document -> Span -> Claim -> Brief
```

The broader PoC hierarchy adds entities, relations, signals, clusters, theses, and decision artefacts. Those remain future-facing until the core ingestion-to-synthesis loop is stable.
