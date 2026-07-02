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
| `theses` | `synthesize` | Direct Postgres |
| `artefacts` | `create` | Direct Postgres |
| `lifecycle` | `run` | Direct Postgres |
| `consolidation` | `run` | Direct Postgres |
| `eval memory` | `run`, `report` | Direct Postgres + Qwen Cloud |

## `capsules` Subcommand Group

The `capsules` group provides Phase B capsule management commands. Commands read and write Postgres directly — no server required.

### `nexus capsules backfill`

```sh
nexus capsules backfill
nexus capsules backfill --dry-run
nexus capsules backfill --batch-size 50
```

Reads `Claim.entities_json["_v0_7"]` for existing claims that predate the Phase B dual-write and writes the corresponding `SemanticCapsule` + `CapsuleSegment` rows. Idempotent — rows with a conflicting `idempotency_key` are skipped. `--dry-run` prints what would be written without persisting. `--batch-size` controls the number of claims processed per DB transaction (default: 100).

## `theses` Subcommand Group

The `theses` group provides Phase C thesis management commands. Commands read and write Postgres directly — no server required.

### `nexus theses synthesize`

```sh
nexus theses synthesize --domain personal_ai_tech
nexus theses synthesize --domain personal_ai_tech --min-strength 0.7
nexus theses synthesize --domain personal_ai_tech --dry-run
```

Clusters strongly-related same-family capsules into `theses` rows by union-finding over binary `semantic_relations` (strength >= `--min-strength`) within the given domain pack. Reads relations written by `classify_relations`; writes one thesis per connected component of size >= 2. `--dry-run` reports clusters without committing. Re-running is not idempotent in this first writer (no unique constraint on `theses`) — intended for manual/reviewed use.

## `artefacts` Subcommand Group

The `artefacts` group provides Phase C decision-artefact management commands. Commands read and write Postgres directly — no server required.

### `nexus artefacts create`

```sh
nexus artefacts create --domain personal_ai_tech --question "..." --answer "..."
nexus artefacts create --domain personal_ai_tech --question "..." --answer "..." --capsule-id <uuid> --thesis-id <uuid>
```

Manually creates a `memo`-type `decision_artefacts` row linking the given capsules and/or theses. `--capsule-id` and `--thesis-id` are repeatable. No batch/backfill mode — artefacts are created one at a time via this command until Phase E wires automatic creation.

## `lifecycle` Subcommand Group

The `lifecycle` group provides the Phase E living-knowledge worker. Reads and writes Postgres directly — no server required.

### `nexus lifecycle run`

```sh
nexus lifecycle run --domain personal_ai_tech
nexus lifecycle run --domain personal_ai_tech --dry-run
nexus lifecycle run --domain personal_ai_tech --json
```

Applies deterministic lifecycle transitions to `candidate`/`active` capsules in the given domain, in precedence order: `superseded` (incoming `supersedes` relation, or the same-actor/same-type/newer-date heuristic — restricted to `core_type="state_change"` so historical events/claims are never wrongly retired) → `contradicted` (higher-authority `contradicts` relation) → `qualified` (incoming `qualifies` relation) → `confirmed` (≥2 supporting relations) → `stale` (pack `retention_policy.stale_conditions`) → `archived` (`archive_after_days`). `--dry-run` reports transitions without committing. `--pack` overrides the domain pack id (defaults to `settings.default_pack_id`).

## `consolidation` Subcommand Group

The `consolidation` group provides the Phase E consolidation worker — a thin CLI wrapper over the Phase C thesis writer (`nexus theses synthesize` shares the same underlying clustering).

### `nexus consolidation run`

```sh
nexus consolidation run --domain personal_ai_tech
nexus consolidation run --domain personal_ai_tech --min-strength 0.7 --min-cluster-size 3
nexus consolidation run --domain personal_ai_tech --dry-run
```

Clusters strongly-related capsules (`--min-strength`, default 0.6) into `theses` rows for `--domain` (required). `--min-cluster-size` (default 2) sets the minimum connected-component size. `--dry-run` reports clusters without writing.

## `eval` Subcommand Group (updated flags)

`nexus eval run` and `nexus eval calibrate` now accept two additional options:

- `--pack-id <id>` — override the domain pack used to drive the SUT and judge.
- `--source-type <type>` — restrict evaluation to examples matching a specific source-type profile.

### `nexus eval memory run` / `nexus eval memory report`

```sh
nexus eval memory run --benchmark nexus_synthetic --k 5
nexus eval memory run --benchmark nexus_synthetic --k 5 --skip-ingest
nexus eval memory report --run-id <timestamp>
```

Runs the Phase F memory benchmark end to end: ingest fixture corpus (`evals/memory/<benchmark>/`) → extract → classify relations → `nexus lifecycle run` → `nexus consolidation run` → answer each fixture question via the chat graph → score (answer correctness, evidence recall@k, citation precision/faithfulness, temporal/supersession correctness, abstention accuracy, latency, token cost) → write `report.md` / `results.jsonl` / `run_meta.json` under `--out` (default `docs/benchmarks/runs/<UTC timestamp>/`). `--skip-ingest` assumes the corpus is already ingested. `eval memory report` prints a previously written run's `report.md`. See [docs/benchmarks/memory-benchmark-plan.md](benchmarks/memory-benchmark-plan.md) and the [README demo guide](../README.md#demo-guide).

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
