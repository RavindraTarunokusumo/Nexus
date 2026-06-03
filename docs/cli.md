# Nexus CLI

The `nexus` CLI is installed as a console script by `pip install -e .`. It uses a hybrid access model: read-only commands go direct to Postgres; ingest, extract, search, and chat commands POST to the running FastAPI server.

See [docs/commands.md](commands.md) for full flag reference and examples for every command.

## Command Groups

| Group | Commands | Access |
|---|---|---|
| _(root)_ | `status` | Direct Postgres |
| `sources` | _(root)_ | Direct Postgres |
| `documents` | _(root)_ | Direct Postgres |
| `document` | _(root)_ | Direct Postgres |
| `runs` | `list`, `show` | Direct Postgres |
| `search` | _(root)_ | HTTP → FastAPI |
| `chat` | _(root)_ | HTTP → FastAPI |
| `ingest` | `url`, `text`, `rss` | HTTP → FastAPI |
| `extract` | _(root)_ | HTTP → FastAPI — uses the telos-aware semantic-object extraction path; dual-writes capsules |
| `capsules` | `backfill` | Direct Postgres |

## `capsules` Subcommand Group

The `capsules` group provides Phase B capsule management commands. Commands read and write Postgres directly — no server required.

### `nexus capsules backfill`

```sh
nexus capsules backfill
nexus capsules backfill --dry-run
nexus capsules backfill --batch-size 50
```

Reads `Claim.entities_json["_v0_7"]` for existing claims that predate the Phase B dual-write and writes the corresponding `SemanticCapsule` + `CapsuleSegment` rows. Idempotent — rows with a conflicting `idempotency_key` are skipped. `--dry-run` prints what would be written without persisting. `--batch-size` controls the number of claims processed per DB transaction (default: 100).

## `eval` Subcommand Group (updated flags)

`nexus eval run` and `nexus eval calibrate` now accept two additional options:

- `--pack-id <id>` — override the domain pack used to drive the SUT and judge.
- `--source-type <type>` — restrict evaluation to examples matching a specific source-type profile.

## `runs` Subcommand Group

The `runs` group exposes the `agent_runs` audit table (populated by `tracer.record_agent_run()` during claim extraction and chat answers). Both commands read Postgres directly — no server required.

### `nexus runs list`

```sh
nexus runs list
nexus runs list --limit 20
nexus runs list --json
```

Lists recent agent runs ordered by `created_at` descending. Columns: ID (short), Run type, Model, Status, Tokens, Cost, Created At.

### `nexus runs show <run_id>`

```sh
nexus runs show <run_id>
nexus runs show <run_id> --json
```

Shows full detail for one run including correlation IDs (`run_id`, `document_id`, `span_id`), token split (`prompt_tokens` / `completion_tokens`), status, cost estimate, and related `span_extractions` rows.

## Universal Flags

Every command accepts:

| Flag | Default | Description |
|---|---|---|
| `--json` | off | Machine-readable JSON instead of a Rich table |
| `--api-url <url>` | `http://localhost:8000` | Override the FastAPI server address |
| `--db-url <url>` | `$DATABASE_URL` | Override the Postgres connection string |

## Settings Resolution

`CLISettings` resolves connection settings in this order: explicit flag → env var (`API_BASE_URL` / `DATABASE_URL`) → `.env` file default. `DATABASE_URL` is only required for commands that read Postgres directly.

## Observability Integration

When `configure_logging()` is called at CLI startup, all log output goes through `RunContextFilter`, which injects `run_id`, `document_id`, and `span_id` from the active `ContextVar` state into every log record. This means CLI-driven extractions produce the same structured, correlated log lines as server-driven extractions.
