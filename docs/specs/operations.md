# Operations Spec

## Deployment Model

The MVP is private infrastructure.

Recommended deployment:

- private VPS
- Docker Compose
- SSH access only
- reverse proxy if HTTP is exposed locally
- HTTPS for any reachable endpoint
- basic authentication for MVP UI/API access
- restricted firewall

Docker Compose services:

- `app`
- `worker`
- `scheduler`
- `postgres`
- `redis`

## Environment Variables

Required initial variables:

```env
DATABASE_URL=
REDIS_URL=
OPENROUTER_API_KEY=
OPENROUTER_T2_MODEL=
OPENROUTER_T3_MODEL=
EMBEDDING_MODEL=
APP_SECRET=
```

## Security Requirements

The MVP should:

- remain private by default
- avoid public database exposure
- avoid logging secrets
- store model API keys only in environment variables
- validate ingestion URLs and text payload sizes
- prevent arbitrary file access through ingestion
- keep raw model payloads available only to trusted operators

## Observability Requirements

Required logs:

- ingestion failures
- extraction failures
- schema validation failures
- model calls
- token usage
- query execution
- worker errors

Required metrics:

- documents ingested per day
- extraction success rate
- average claims per document
- query latency
- token usage per day
- brief generation time

## Build Phases

### Phase 1: Ingestion

Implement:

- FastAPI app
- database schema
- RSS ingestion
- manual URL ingestion
- cleaner

Acceptance:

```text
The system stores clean documents from at least 5 sources.
```

### Phase 2: Retrieval Foundation

Implement:

- chunking
- embeddings
- pgvector search

Acceptance:

```text
Semantic search returns relevant spans.
```

### Phase 3: Claim Extraction

Implement:

- OpenRouter client
- structured extraction
- evidence linking

Acceptance:

```text
Claims are extracted and linked to spans.
```

### Phase 4: Brief Generation

Implement:

- synthesis pipeline
- daily brief creation

Acceptance:

```text
The system generates readable evidence-backed briefs.
```

### Phase 5: Query Answering

Implement:

- retrieval QA endpoint
- grounded synthesis

Acceptance:

```text
The system answers evidence-grounded questions.
```

### Phase 6: Scheduling and Automation

Implement:

- scheduler
- recurring daily runs

Acceptance:

```text
The pipeline runs automatically every day.
```

## Validation Strategy

Each phase should include:

- focused unit tests for deterministic logic
- integration tests for database persistence
- schema validation tests for LLM outputs
- one end-to-end pipeline test over a small fixture source
- manual review of generated claims and briefs before expanding automation

## Cost Guardrails

The MVP should log model usage and estimated cost for every LLM call. Cost controls should include:

- per-run max token limits
- per-document claim caps
- retries with bounded attempts
- cheap model defaults for structured extraction
- explicit promotion to stronger models only for synthesis and difficult extraction

## Future PoC Operations

The broader PoC adds:

- Ollama local models
- VLM image triage
- NanoClaw or equivalent interface runtime
- WhatsApp or Telegram access
- lifecycle consolidation workers
- weekly knowledge integrity audits
- backup to external object storage
- dashboard cost and lifecycle monitoring
