# Phase 4 — Observability: Centralized Logger & DB-Backed Tracer

**Branch:** `observability`
**PR:** #7
**Merge commit:** _(pending merge)_
**Merged at:** _(pending merge)_
**Merged by:** RavindraTarunokusumo

## Summary

Added a centralized stdlib JSON logger and DB-backed pipeline tracer. Every LLM call, span extraction outcome, and document status transition is now recorded to Postgres and correlated by `run_id`. Two new CLI commands (`nexus runs list`, `nexus runs show`) make the trace queryable without opening Postgres directly.

## Tasks Completed

- [x] T0: Pre-flight — refresh GitNexus index and baseline test run
- [x] T1: Migration 0002 — `agent_runs` correlation columns, `documents.*_at` timestamps, `span_extractions` table (commits: `3fe4a8d`, `5d77df4`)
- [x] T2: `app/db/models.py` — `AgentRun` observability columns, new `SpanExtraction` model, `Document` timestamp columns (commit: `b30de82`)
- [x] T3: `app/observability/run_context.py` — `ContextVar` binding + `extraction_run`/`span_scope` context managers (commit: `38ba4be`)
- [x] T4: `app/observability/logger.py` — JSON formatter + `RunContextFilter` + `configure_logging()` (commit: `e711526`)
- [x] T5: `app/observability/tracer.py` — `record_agent_run`, `record_span_extraction`, `mark_document_timestamp` (commit: `8e61cac`)
- [x] T6: `app/intelligence/llm_client.py` — replace `_log` with `tracer.record_agent_run`; remove truncation; split token accounting (commit: `043c00d`)
- [x] T7: `app/intelligence/extraction.py` — wrap graph in `extraction_run`, `span_scope` per span, `span_extractions` rows, `*_at` timestamps, `run_with_context()` (commit: `2c74cae`)
- [x] T8: `app/api/routes_claims.py` — `ExtractionSummary.run_id`; use `run_with_context` (commits: `70518bb`, `f526643`)
- [x] T9: `app/api/routes_ingestion.py` — mark `chunked_at`/`embedded_at` after pipeline stages (commit: `3207709`)
- [x] T10: `app/main.py` + `app/cli/main.py` — `configure_logging()` at startup (commit: `887c614`)
- [x] T11: `app/cli/db.py` + `app/cli/render.py` + `app/cli/main.py` — `nexus runs list`/`nexus runs show` commands (commit: `e875f18`)
- [x] T12: `TODO.md` — append deferred observability work items (commit: `0e07665`)
- [x] T13: Final validation — 135 tests pass, ruff clean, CLI smoke OK (commits: `b988403`)
- [x] Doc-updater: architecture, database, commands, cli.md, index (commits: `5e98e51`, `61c4fe8`, `6c3fdce`, `aca8146`)
- [x] GitNexus stat update: 2007 symbols, 3023 relationships, 61 flows (commit: `2a1daff`)

## Key Decisions

- **`ContextVar.reset(token)` over `.set(None)`** — Token-reset prevents asyncio.gather tasks from bleed on reset; `.set(None)` would corrupt sibling task context.
- **Fire-and-forget tracer helpers** — All three tracer functions catch all exceptions and log at WARNING; extraction and LLM paths never fail due to observability errors.
- **`run_with_context()` wrapper** — Keeps `extraction_run` context manager inside `routes_claims.py` rather than exposing it in the route handler; `run_id` is returned in final graph state.
- **Nullable-only migration** — All new `agent_runs`/`documents` columns nullable; `span_extractions` is a new table. Zero risk to existing rows.
- **Blended cost rate** — `_COST_PER_TOKEN_USD = 0.14/1_000_000` is a placeholder; proper input/output rate split deferred to backlog.

## Test Results

135 tests passing (41 new: 6 context, 6 logger, 7 tracer, 5 CLI runs, plus extensions to extraction, ingestion, LLM client, claims route tests). Pre-commit hooks green. ruff clean.

## Lessons

- `CliRunner` (Typer/Click) captures output to its own buffer — subprocess capture returns empty when the tool exits 0 cleanly; use `CliRunner.invoke` to inspect output content.
- `gitnexus_detect_changes` with `scope: compare` shows 0 when working tree is clean (all changes committed) — this is expected post-commit; use `git diff main...HEAD --stat` to verify branch scope instead.
- mypy not installed in this env — skip or install before pre-PR in future sessions.
