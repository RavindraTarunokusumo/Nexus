# Commands

> **Phase 1 Status: Implemented**

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

Line length is set to 100 in `pyproject.toml`.

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
