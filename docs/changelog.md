# Changelog

Track meaningful repository-level changes here.

## Format

- Date
- What changed
- Why it changed
- Any follow-up work or migration notes

## 2026-05-16 — Phase 2.5: Operator CLI

Added the `nexus` console-script CLI (`app/cli/`) for monitoring and operating the system without a browser or API client.

**What changed:**

- `app/cli/` module: `config.py` (CLISettings), `db.py` (5 direct-Postgres readers), `http.py` (4 HTTP wrappers), `render.py` (5 Rich+JSON formatters), `main.py` (Typer app).
- 8 commands: `nexus status`, `nexus sources`, `nexus documents`, `nexus document <id>`, `nexus search`, `nexus ingest url`, `nexus ingest text`, `nexus ingest rss`.
- Hybrid access model: reads go direct to Postgres; ingest and search route through the FastAPI server.
- `pyproject.toml`: added `typer>=0.12.0`, `rich>=13.7.0`, and `[project.scripts]` entry `nexus = "app.cli.main:app"`.
- 28 new tests across `test_cli_db.py`, `test_cli_render.py`, `test_cli_e2e.py`.

**Why:** Provides operators a fast, scriptable interface to inspect pipeline health, browse documents, trigger ingestion, and run semantic searches without going through the API directly.

**Migration / setup:** Run `pip install -e .` to register the `nexus` command. No schema migrations required.

## 2026-05-12

- Added implementation-facing project specs under `docs/specs/`.
- Replaced scaffold placeholders in architecture, database, testing, commands, and patterns docs with Nexus Lite guidance.
- Linked source drafts and specs from the docs index.

Follow-up: create the first implementation plan from the specs before writing application code.
