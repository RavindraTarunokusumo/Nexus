# Commands

> **Phase 3 Status: Claim extraction + hybrid chatbot implemented**

## Prerequisites

- Docker (required for the full local stack and integration tests)
- Python 3.11+
- A `.env` file with at minimum:

```sh
DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5432/nexus
APP_SECRET=changeme
```

Copy `.env.example` as a starting point.

---

## Local Environment Setup

Create and activate a virtual environment at the project root (`.venv/` is git-ignored):

```sh
# Create once
python -m venv .venv

# Activate — Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Activate — Windows (Git Bash / WSL)
source .venv/Scripts/activate

# Activate — macOS / Linux
source .venv/bin/activate

# Install the project + all dev deps (includes nexus CLI, ruff, pytest, pre-commit)
pip install -e ".[dev]"
```

Wire pre-commit hooks once per clone (after activating the venv):

```sh
pre-commit install
```

---

## Start the Application

**With Docker Compose (recommended):**

```sh
docker compose up
```

Starts PostgreSQL (`pgvector/pgvector:pg16`), Redis (`redis:7-alpine`), and the FastAPI app on port 8000. The app mounts the local directory and runs with `--reload`.

The HuggingFace model cache (`BAAI/bge-small-en-v1.5`, ~130 MB) is persisted in the `hf_cache` Docker volume — it downloads once and is reused on subsequent starts.

**Directly (requires a running Postgres):**

```sh
uvicorn app.main:app --reload
```

---

## Run Migrations

```sh
alembic upgrade head
```

Creates the `vector` extension and all 8 tables (`sources`, `documents`, `spans`, `claims`, `claim_evidence`, `briefs`, `brief_items`, `agent_runs`). Migration `0001` is idempotent — safe to re-run.

---

## Run Tests

**Full integration suite** (requires Docker):

```sh
python -m pytest tests/ -v
```

testcontainers spins up a fresh `pgvector/pgvector:pg16` container per session. `DATABASE_URL` and `APP_SECRET` must be present in `.env` (the test container overrides the URL at runtime).

**Fast unit tests** (no Docker, < 15s):

```sh
python -m pytest tests/test_chunker.py tests/test_cli_render.py -v
```

**Useful flags:**

```sh
# Run a single file
python -m pytest tests/test_ingestion.py -v

# Run tests matching a keyword
python -m pytest -k "dedup" -v

# Stop on first failure
python -m pytest -x -v

# Skip the slow embedder test (downloads model)
python -m pytest --ignore=tests/test_embedder.py -v
```

---

## Linting / Formatting

```sh
# Lint (reports issues)
ruff check .

# Lint and auto-fix
ruff check --fix .

# Format check (dry run)
ruff format --check .

# Format in place
ruff format .
```

Rules active: `E`, `W`, `F` (pyflakes), `I` (isort), `C90` (mccabe, max complexity 10).
Line length: 100. Configuration in `[tool.ruff]` in `pyproject.toml`.

---

## Pre-Commit Hooks

Each `git commit` automatically runs:

| Hook | What it checks |
|---|---|
| `ruff check --fix` | Lint, imports, cyclomatic complexity ≤ 10 |
| `ruff format` | Consistent formatting |
| `trailing-whitespace` | No trailing spaces |
| `end-of-file-fixer` | Files end with a newline |
| `check-yaml` / `check-toml` | Config syntax |
| `check-merge-conflict` | No leftover conflict markers |
| `check-added-large-files` | Files under 1 MB |
| `pytest` (fast) | `test_chunker.py` + `test_cli_render.py` — no Docker |

Run on demand against the full tree:

```sh
pre-commit run --all-files
```

---

## Nexus CLI (Operator)

The `nexus` command is installed as a console script by `pip install -e .`.

**Access model:**

| Command group | Access path | Server required? |
|---|---|---|
| `status`, `sources`, `documents`, `document` | Direct Postgres | No |
| `runs list`, `runs show` | Direct Postgres | No |
| `search` | HTTP → FastAPI | Yes |
| `chat` | HTTP → FastAPI | Yes |
| `extract` | HTTP → FastAPI | Yes |
| `ingest url / text / rss` | HTTP → FastAPI | Yes |

**Universal flags** available on every command:

| Flag | Default | Description |
|---|---|---|
| `--json` | off | Machine-readable JSON output instead of a rich table |
| `--api-url <url>` | `http://localhost:8000` | Override the FastAPI server address |
| `--db-url <url>` | `$DATABASE_URL` | Override the Postgres connection string |

---

### `nexus status`

Pipeline health snapshot — reads Postgres directly, no server required.

```sh
nexus status
nexus status --json
```

Shows document counts by status (`fetched` / `chunked` / `embedded` / `claims_extracted` / `extraction_partial` / `extraction_failed`), total spans, source count, and timestamp of the last ingestion. Documents stuck in `fetched` or `chunked` for more than one hour are highlighted yellow.

**JSON output keys:**

```json
{
  "docs_by_status": {"fetched": 0, "chunked": 0, "embedded": 10, "claims_extracted": 235},
  "total_documents": 245,
  "total_spans": 1843,
  "total_sources": 8,
  "enabled_sources": 7,
  "last_ingest_at": "2026-05-17T14:23:00+00:00",
  "stuck_count": 0
}
```

---

### `nexus sources`

List configured sources — reads Postgres directly.

```sh
nexus sources
nexus sources --enabled          # enabled sources only
nexus sources --disabled         # disabled sources only
nexus sources --json             # machine-readable
```

Columns: ID (short), Name, Type, URL, Domain pack, Enabled, Credibility score.

---

### `nexus documents`

List documents with optional filters — reads Postgres directly.

```sh
nexus documents
nexus documents --status embedded
nexus documents --status fetched
nexus documents --source <uuid>
nexus documents --since 2026-05-01T00:00:00
nexus documents --limit 100
nexus documents --status embedded --json | jq '.[].title'
```

| Flag | Description |
|---|---|
| `--status` | Filter by pipeline status (`fetched`, `chunked`, `embedded`, `claims_extracted`, `extraction_partial`, `extraction_failed`) |
| `--source <uuid>` | Filter by source ID |
| `--since <ISO timestamp>` | Only documents fetched after this time |
| `--limit N` | Maximum rows returned (default: 50) |

Columns: ID (short), Title, Source, Status (colour-coded), Fetched At.

---

### `nexus document <id>`

Show one document and all its spans — reads Postgres directly.

```sh
nexus document 3f8a2c1d-7e4b-4a9f-b2d5-1c6e8f3a9b7d
nexus document <id> --json
nexus document <id> --claims          # include extracted claims below the span table
nexus document <id> --claims --json   # JSON with "claims" array included
```

Prints two tables: document metadata (title, URL, source, status, content hash, timestamps) and a span table (index, token count, embedding presence, 80-char text preview). The raw embedding vectors are never shown. With `--claims`, a third table lists every extracted claim (type, confidence, entities, claim text).

---

### `nexus search`

Semantic span search — POSTs to `/search/spans` on the running FastAPI server.

```sh
nexus search "open-source LLM releases"
nexus search "Claude API tool use" --top-k 5
nexus search "infrastructure benchmark" --json
```

| Flag | Default | Description |
|---|---|---|
| `--top-k N` | 10 | Maximum results returned |

Results are ranked by cosine similarity (score 0–1). Score is colour-coded: ≥ 0.7 green, 0.5–0.7 yellow, < 0.5 white.

The server must be running and at least one document must have `status = embedded` before results are returned. Returns an empty table (not an error) if the index has no embedded spans.

---

### `nexus chat`

Ask a single-turn question answered from embedded spans and extracted claims.

```sh
nexus chat "What changed in recent open-source LLM releases?"
nexus chat "What changed?" --top-k 5
nexus chat "What changed?" --json
```

| Flag | Default | Description |
|---|---|---|
| `--top-k N` | 8 | Maximum retrieved context spans to use, from 1 to 20 |

The command POSTs to `/chat/answer` on the running FastAPI server. The server must have the embedder initialised. Human output prints the answer first and a compact citation table when citations are available; `--json` prints the raw API response.

---

### `nexus ingest`

Trigger ingestion — POSTs to the FastAPI server.

**Ingest a URL:**

```sh
nexus ingest url https://arxiv.org/abs/2605.12345
nexus ingest url https://example.com/post --source-name research --domain-pack personal_ai_tech
```

Calls `POST /ingest/url`. The server fetches, cleans, deduplicates, stores, and triggers background chunk+embed.

**Ingest a local text file:**

```sh
nexus ingest text --title "Meeting notes" --file ./notes.md
nexus ingest text --title "Paper summary" --file ./summary.txt --source-name papers
```

Reads the file from disk and calls `POST /ingest/text`.

**Trigger RSS feed ingestion:**

```sh
nexus ingest rss 9e343479-f9d1-1f54-52b0-eb9e9cbf2c8c
nexus ingest rss <source_id> --json
```

Calls `POST /ingest/rss/{source_id}`. The source must already be registered (via `POST /sources`) with `source_type=rss`.

**Ingest flags:**

| Flag | Default | Description |
|---|---|---|
| `--source-name` | `manual` | Name for auto-created manual source |
| `--domain-pack` | `personal_ai_tech` | Domain pack for the ingested document |

---

### `nexus extract <id>`

Run claim extraction for a document — POSTs to `/documents/<id>/extract-claims` on the running FastAPI server.

```sh
nexus extract 3f8a2c1d-7e4b-4a9f-b2d5-1c6e8f3a9b7d
nexus extract <id> --json             # machine-readable ExtractionSummary
nexus extract <id> --force            # re-extract even if claims already exist
```

| Flag | Default | Description |
|---|---|---|
| `--force` | off | Delete existing claims and re-run extraction |

The document must have `status = embedded` (or a post-extraction status when using `--force`). The server must be running; exits non-zero on 4xx/5xx.

**Output (human-readable table):**

```
Metric              Value
──────────────────────────
Claims extracted       12
Spans processed         8
Spans failed            0
Tokens used          4200
Cost estimate    $0.001260
```

**Output (--json):**

```json
{
  "document_id": "<uuid>",
  "run_id": "<uuid>",
  "claims_extracted": 12,
  "spans_processed": 8,
  "spans_failed": 0,
  "tokens_used": 4200,
  "cost_estimate_usd": 0.00126,
  "claim_ids": ["<uuid>", "..."]
}
```

---

### `nexus runs list`

List recent agent runs — reads Postgres directly, no server required.

```sh
nexus runs list
nexus runs list --limit 20
nexus runs list --json
nexus runs list --db-url postgresql+asyncpg://nexus:nexus@host:5432/nexus
```

| Flag | Default | Description |
|---|---|---|
| `--limit N` | 50 | Maximum rows returned |
| `--json` | off | Machine-readable JSON output |
| `--db-url <url>` | `$DATABASE_URL` | Override the Postgres connection string |

Columns: ID (short), Run type, Model, Status, Tokens (prompt / completion), Cost estimate, Created At.

---

### `nexus runs show <run_id>`

Show detail for a single agent run — reads Postgres directly, no server required.

```sh
nexus runs show 3f8a2c1d-7e4b-4a9f-b2d5-1c6e8f3a9b7d
nexus runs show <run_id> --json
```

| Flag | Default | Description |
|---|---|---|
| `--json` | off | Machine-readable JSON output |
| `--db-url <url>` | `$DATABASE_URL` | Override the Postgres connection string |

Displays the run record including correlation IDs (`run_id`, `document_id`, `span_id`), token split (`prompt_tokens`, `completion_tokens`), status, cost estimate, and associated `span_extractions` rows.

---

### Typical operator workflow

```sh
# 1. Check pipeline state
nexus status

# 2. List sources
nexus sources --enabled

# 3. Trigger a feed
nexus ingest rss <source_id>

# 4. Watch documents land
nexus documents --status fetched
nexus documents --status embedded

# 5. Inspect a document
nexus document <doc_id>

# 6. Test retrieval
nexus search "your query here" --top-k 5

# 7. Extract claims (requires OPENROUTER_API_KEY)
nexus extract <doc_id>

# 8. Review extracted claims
nexus document <doc_id> --claims

# 9. Ask a grounded question over spans and claims
nexus chat "What changed in the latest ingested sources?"
```

---

### Error handling

| Situation | Output |
|---|---|
| `DATABASE_URL` not set for a DB-read command | `API error: DATABASE_URL is not set` + exit 1 |
| FastAPI server not running | `Network error: ...` + exit 1 |
| API returns 4xx/5xx | `API error: POST /ingest/url → 422: ...` + exit 1 |
| Document not found | `Document <id> not found.` + exit 1 |
| No embedded documents for search | Empty results table (not an error) |
| Invalid `--since` format | `Invalid --since value '...': ...` (Typer validation error) |

---

## Chat Answer API (Phase 3)

Use `nexus chat` for CLI access (see above). The raw HTTP endpoint is also available directly.

### Ask a grounded question

```sh
curl -X POST "http://localhost:8000/chat/answer" \
  -H "Content-Type: application/json" \
  -d '{"question":"What changed in recent open-source LLM releases?","top_k":8}'
```

Response (200):

```json
{
  "answer": "Grounded answer text.",
  "citations": [
    {
      "document_id": "<uuid>",
      "span_id": "<uuid>",
      "document_title": "Document title",
      "url": "https://example.com/article",
      "score": 0.82,
      "claim_ids": ["<uuid>"]
    }
  ],
  "retrieved_context_count": 3,
  "run_id": "<uuid>",
  "tokens_used": 900,
  "cost_estimate_usd": 0.000126
}
```

| Status | Meaning |
|---|---|
| 200 | Returns a grounded answer or the insufficient-evidence fallback |
| 422 | Blank question or invalid `top_k` |
| 503 | Embedder not initialised or OpenRouter/chat execution failed |

Citation safety behavior:

- The model may cite only retrieved labels such as `C1`.
- The API normalizes and validates returned labels against retrieved context.
- Unknown labels are dropped, and if no valid citations remain the route falls back to the insufficient-evidence answer.

---

## Claim Extraction API (Phase 3)

Use `nexus extract` / `nexus document --claims` for CLI access (see above). The raw HTTP endpoints are also available directly.

### Extract claims for a document

```sh
curl -X POST "http://localhost:8000/documents/<document_id>/extract-claims"
# Re-extract even if claims already exist
curl -X POST "http://localhost:8000/documents/<document_id>/extract-claims?force=true"
```

Response (200):

```json
{
  "document_id": "<uuid>",
  "run_id": "<uuid>",
  "claims_extracted": 12,
  "spans_processed": 8,
  "spans_failed": 0,
  "tokens_used": 4200,
  "cost_estimate_usd": 0.00126,
  "claim_ids": ["<uuid>", "..."]
}
```

| Status | Meaning |
|---|---|
| 200 | Extraction complete |
| 404 | Document not found |
| 409 | Claims already exist — pass `?force=true` to re-extract |
| 422 | Document not in `embedded` or a post-extraction status |
| 503 | OpenRouter unreachable |

### List claims

```sh
curl "http://localhost:8000/claims?document_id=<uuid>"
curl "http://localhost:8000/claims?document_id=<uuid>&claim_type=model_release&status=active&limit=20"
```

Query params: `document_id` (required), `claim_type`, `status` (`active`|`rejected`), `limit`, `offset`.

---

## GitNexus Workflow

Use GitNexus when you need repo intelligence:

```sh
npx gitnexus status           # freshness check
npx gitnexus analyze          # rebuild index (incremental)
npx gitnexus analyze --force  # full rebuild
```

Via MCP tools in Claude Code:

```
gitnexus://repo/Nexus/context   → codebase overview
gitnexus_query({query: "..."})  → find execution flows
gitnexus_context({name: "..."}) → 360° symbol view
gitnexus_impact({target: "..."})→ blast radius
gitnexus_detect_changes()       → what do my edits affect
```
