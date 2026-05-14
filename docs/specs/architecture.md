# Architecture Spec

## Runtime Shape

Nexus Lite is a private FastAPI application with background workers, PostgreSQL plus pgvector, Redis, local embeddings, and an LLM gateway.

Recommended MVP stack:

| Layer | Technology |
|---|---|
| API backend | FastAPI |
| Database | PostgreSQL |
| Vector search | pgvector |
| Queue | Redis |
| Workers | Celery or RQ |
| Scheduling | APScheduler or cron |
| Embeddings | sentence-transformers |
| LLM gateway | OpenRouter |
| Deployment | Docker Compose |
| Hosting | Private VPS |

## Core Flow

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

## MVP Repository Layout

Target layout once implementation starts:

```text
app/
  main.py
  config.py
  api/
    routes_sources.py
    routes_documents.py
    routes_claims.py
    routes_briefs.py
    routes_query.py
  db/
    models.py
    session.py
    migrations/
  ingestion/
    rss.py
    url_fetcher.py
    cleaner.py
    chunker.py
  intelligence/
    llm_client.py
    extraction.py
    synthesis.py
    retrieval.py
    prompts/
  workers/
    tasks.py
    scheduler.py
  domain_packs/
    personal_ai_tech.yaml
docker-compose.yml
.env.example
README.md
PLAN.md
```

## Module Responsibilities

**API layer.** Exposes source management, ingestion triggers, document/claim browsing, brief generation, and grounded query answering.

**Database layer.** Owns SQLAlchemy models, migrations, sessions, and persistence invariants. It should not contain LLM prompts or network ingestion logic.

**Ingestion layer.** Fetches RSS, URLs, and pasted text; cleans documents; deduplicates; chunks documents into spans.

**Intelligence layer.** Owns embeddings, retrieval, LLM gateway calls, claim extraction, and synthesis.

**Worker layer.** Runs asynchronous jobs and scheduled automation. Workers should compose services from ingestion and intelligence modules.

**Domain pack layer.** Provides domain-specific extraction taxonomies, source policies, prompt settings, brief sections, and model choices.

## MVP Boundary

The MVP stores a simplified hierarchy:

```text
Source -> Document -> Span -> Claim -> Brief
```

The broader PoC hierarchy is:

```text
Source -> Span -> Primitive -> Signal/Event -> Cluster/Timeline -> Thesis/Model -> Decision Artefact
```

The MVP implementation should avoid hard-coding assumptions that block the broader hierarchy, but it should not implement the broader layers until the core loop is stable.

## LLM Gateway

The system should expose one reusable model gateway responsible for:

- provider communication
- schema validation
- retries
- token tracking
- cost estimation
- agent run logging

Suggested interface:

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

## Automation

Default daily automation:

```text
07:00 UTC
-> ingest new documents
-> process pipeline
-> generate daily brief
```

Worker jobs:

- `fetch_source`
- `clean_document`
- `chunk_document`
- `embed_spans`
- `extract_claims`
- `generate_brief`
- `answer_query`

## Future PoC Architecture Constraints

The MVP should preserve these future-compatible constraints:

- every derived object must preserve a path back to evidence
- domain-specific behavior belongs in domain packs
- confidence should eventually support multi-component scoring
- storage lifecycle metadata should be possible to add without redesigning the core
- retrieval should be extensible from span/claim search to dual-index and hybrid scoring
