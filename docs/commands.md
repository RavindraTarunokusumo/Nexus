# Commands

> **Phase 2.5 Status: CLI implemented**

## Prerequisites

- Docker (required for both local stack and tests)
- Python 3.11+
- A `.env` file with at minimum:

```sh
DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5432/nexus
APP_SECRET=changeme
```

Copy `.env.example` as a starting point.

## Start the Application

**With Docker Compose (recommended):**

```sh
docker compose up
```

Starts PostgreSQL (pgvector/pgvector:pg16), Redis (redis:7-alpine), and the app on port 8000. The app container mounts the local directory and runs with `--reload`.

**Directly (requires a running Postgres):**

```sh
uvicorn app.main:app --reload
```

The app reads `DATABASE_URL` from `.env` or the environment.

## Run Migrations

```sh
alembic upgrade head
```

Requires `DATABASE_URL` to be set in the environment or `.env`. Creates the `vector` extension and all 8 tables. Migration 0001 is idempotent — safe to re-run.

## Run Tests

```sh
python -m pytest tests/ -v
```

Requires Docker (testcontainers spins up a real `pgvector/pgvector:pg16` container) and a `.env` file with `DATABASE_URL` and `APP_SECRET` present (values don't need to point at a running DB — the test container overrides the URL at runtime).

Run a specific file:

```sh
python -m pytest tests/test_sources.py -v
python -m pytest tests/test_ingestion.py -v
```

## Linting / Formatting

```sh
ruff check .
ruff format --check .
```

Line length is set to 100 in `pyproject.toml`. Enabled lint groups: `E`, `W`, `F`, `I`, `C90` (cyclomatic complexity ≤ 10).

## Pre-Commit Hooks

Install once after cloning:

```sh
pip install -e ".[dev]"
pre-commit install
```

Each `git commit` then runs (locally, before the commit is written):

- `ruff check --fix` — lint + imports + cyclomatic complexity (C90, max 10)
- `ruff format` — code formatting
- trailing-whitespace, end-of-file-fixer, yaml/toml/merge-conflict/large-file checks
- `pytest tests/test_chunker.py tests/test_cli_render.py` — fast unit tests, no Docker needed

Run against the whole tree on demand:

```sh
pre-commit run --all-files
```

Integration tests (testcontainers) are intentionally not part of the pre-commit gate — they need Docker and take longer than a commit should. CI runs the full suite.

## Nexus CLI (Operator)

Install the CLI once (requires `pip install -e .` or equivalent):

```sh
pip install -e .
```

This registers the `nexus` console-script from `app.cli.main:app`.

Every command accepts three universal flags:

| Flag | Default | Description |
|---|---|---|
| `--json` | off | Machine-readable JSON output |
| `--api-url` | `http://localhost:8000` | FastAPI server base URL |
| `--db-url` | `$DATABASE_URL` | Postgres connection string for direct reads |

### Pipeline Status

```sh
nexus status
```

Shows document counts by status, totals, and last ingest timestamp. Reads Postgres directly.

### Sources

```sh
nexus sources
nexus sources --enabled
nexus sources --disabled
```

Lists all registered sources. Filter by enabled/disabled state.

### Documents

```sh
nexus documents
nexus documents --status embedded
nexus documents --source <uuid>
nexus documents --since 2026-05-01T00:00:00
nexus documents --limit 50
```

Lists documents with optional filters. Reads Postgres directly.

### Document Detail

```sh
nexus document <id>
```

Shows a single document with all its spans. Reads Postgres directly.

### Semantic Search

```sh
nexus search "query text"
nexus search "query text" --top-k 20
```

Semantic span search via `POST /search/spans` on the FastAPI server.

### Ingest

```sh
# Ingest a URL
nexus ingest url https://example.com/article

# Ingest local text
nexus ingest text --title "My Note" --file ./note.txt

# Trigger RSS ingest for a registered source
nexus ingest rss <source_id>
```

All ingest commands go through the FastAPI server (`POST /ingest/*`).

## GitNexus Workflow

Use GitNexus when you need repo context:

```sh
gitnexus status
gitnexus analyze
gitnexus query "search concept"
gitnexus context <symbol>
gitnexus impact <symbol>
gitnexus detect-changes
gitnexus mcp
```
