# Changelog

Track meaningful repository-level changes here.

## Format

- Date
- What changed
- Why it changed
- Any follow-up work or migration notes

## 2026-05-17 — Phase 3: Claim Extraction

Added the `app/intelligence/` module and claim extraction API.

**What changed:**

- `app/intelligence/llm_client.py`: `LLMClient.complete_json` — calls OpenRouter, validates responses with Pydantic, logs every invocation to `agent_runs` (model, tokens, cost estimate, status). Error hierarchy: `LLMError` → `LLMNetworkError`, `LLMSchemaError` (with `raw_output` attribute). Exports `ExtractedClaim` and `ExtractionOutput` Pydantic schemas.
- `app/intelligence/extraction.py`: LangGraph `StateGraph` with 4 nodes: `load_spans` → `extract_spans` → `store_claims` → `update_status`. Per-span concurrent extraction via `asyncio.gather` + `Semaphore(5)`. Correction-prompt retry (max 2 per span). Exports status constants: `STATUS_EMBEDDED`, `STATUS_CLAIMS_EXTRACTED`, `STATUS_EXTRACTION_PARTIAL`, `STATUS_EXTRACTION_FAILED`, `POST_EXTRACTION_STATUSES`.
- `app/intelligence/prompts/extract_claims.py`: `SYSTEM_PROMPT`, `build_user_prompt`, `build_correction_prompt`.
- `app/api/routes_claims.py`: `POST /documents/{id}/extract-claims[?force=true]` and `GET /claims`.
- `pyproject.toml`: added `langgraph>=0.2.0` dependency.
- `documents.status` lifecycle extended: `embedded` → `claims_extracted` | `extraction_partial` | `extraction_failed`.

**Why:** Turns embedded spans into typed, evidence-grounded claims — the prerequisite for Phase 4 brief synthesis.

**Migration / setup:** No schema migrations required (all 8 tables were created in migration 0001). Set `OPENROUTER_API_KEY` in `.env` and optionally `OPENROUTER_T2_MODEL` (default: `openai/gpt-4o-mini`).

## 2026-05-19 — Phase 3 CLI + Model Tier Config

Extended the `nexus` CLI with Phase 3 extraction commands and centralised model configuration.

**What changed:**

- `nexus extract <doc_id>` — new CLI command that POSTs to `/documents/{id}/extract-claims`; supports `--force` re-extraction and `--json` output. HTTP timeout raised to 5 min (LLM calls over all spans).
- `nexus document --claims` — new flag appending extracted claims table (or `"claims"` JSON key) to document detail view.
- `app/config.py`: model fields renamed to `t1_model` / `t2_model` / `t3_model` with per-tier comments; defaults switched to `BAAI/bge-small-en-v1.5` / `deepseek/deepseek-v4-flash` / `deepseek/deepseek-v4-pro`.
- `app/intelligence/llm_client.py`: cost estimate updated to DeepSeek flash pricing (~$0.14/1M tokens).
- `scripts/run_phase3_cli_validation.ps1`: end-to-end smoke-test script.
- Docs: `commands.md` updated with `nexus extract` reference and extended operator workflow.

**Why:** Gives operators CLI-level access to claim extraction without curl; unifies model selection in one config file.

**⚠ Breaking:** `.env` env var names changed — rename before upgrading:

| Old | New |
|---|---|
| `EMBEDDING_MODEL` | `T1_MODEL` |
| `OPENROUTER_T2_MODEL` | `T2_MODEL` |
| `OPENROUTER_T3_MODEL` | `T3_MODEL` |

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
