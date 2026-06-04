# Changelog

Track meaningful repository-level changes here.

## Format

- Date
- What changed
- Why it changed
- Any follow-up work or migration notes

## 2026-06-03 — Phase B: Durable Capsule Layer

Landed the Phase B capsule-schema foundation across commits `620a191`–`4a052b4` on branch `claude/phase-b-implementation`.

**What changed:**

- **B1 — Migration + ORM.** `app/db/migrations/versions/0005_semantic_capsules.py` adds 6 new tables: `semantic_capsules` (durable v0.7 semantic objects; `idempotency_key` UNIQUE; `core_type` / `lifecycle_state` / `escalation_state` CHECK constraints; 384-dim `embedding` column), `capsule_segments` (capsule × span join with `role`), `semantic_relations` (capsule × capsule edges), `theses`, `decision_artefacts`, and `domain_packs` (self-FK `parent_pack_id`). `app/db/models.py` adds ORM classes and backrefs: `Document.capsules`, `Span.capsule_segments`, `SemanticCapsule.segments`, `CapsuleSegment.capsule`, `CapsuleSegment.span`.
- **B2 — Dual-write.** `store_claims` in `app/intelligence/extraction.py` now writes `SemanticCapsule` + `CapsuleSegment` rows in the same transaction as `Claim` + `ClaimEvidence`. Capsule text is embedded at write time via the `bge-small-en-v1.5` shared singleton from `app/intelligence/capsules.py`.
- **B3 — Backfill.** New `app/intelligence/backfill.py` + `app/cli/capsules.py`. Exposes `nexus capsules backfill [--dry-run] [--batch-size N]`. Reads `Claim.entities_json["_v0_7"]` and constructs capsule rows. Idempotent via `idempotency_key`.
- **B4 — v3 source-type classifier.** `_resolve_pack_and_source_type` in `extraction.py` runs a 4-pass classifier: URL hostname match (`SourceTypeProfile.url_domains`), title regex match (`SourceTypeProfile.title_regex`), pack fallback, safety net `"ai_news_article"`. `SourceTypeProfile` gained `url_domains` and `title_regex` (empty defaults; non-breaking). Title regex is precompiled on pack load; URL parsed once per call.
- **B5 — Eval runner port + legacy schema retirement.** `app/evaluation/runner.py` now uses `response_model=SemanticExtractionOutput`. New `SemanticObjectJudge` replaces `ClaimExtractionJudge`. New gold set `evals/gold/semantic_objects/ai_tech_v3.yaml` (10 examples). `nexus eval run` and `nexus eval calibrate` accept `--pack-id` and `--source-type`. Deleted: `ExtractedClaim`, `ExtractionOutput`, `app/intelligence/prompts/extract_claims.py`, `app/evaluation/prompts/claim_extraction_judge.py`, `ClaimExtractionJudge`.
- **Pre-PR refactor.** New `app/intelligence/capsules.py` consolidates `get_embedder()`, `build_capsule_idempotency_key`, `build_capsule_row`. Precompiled title regex on pack load; URL parsed once per classifier call.

**Why:** Establishes the durable semantic-object storage layer needed for Phase C (capsule-based retrieval), Phase D (relations), and Phase E (lifecycle management and decision artefacts).

**Migration / setup:** Run `alembic upgrade head` to apply migration 0005. Run `nexus capsules backfill` to populate capsule rows from Phase A extraction data. No breaking API changes — chat and claim endpoints are unchanged.

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
