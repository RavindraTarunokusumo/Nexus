# Changelog

Track meaningful repository-level changes here.

## Format

- Date
- What changed
- Why it changed
- Any follow-up work or migration notes

## 2026-07-02 — Phase C Remainder: Thesis + Decision Artefact Writers

Shipped the deferred C3/C4 items from Phase C on branch `claude/telos-residuals-c`.

**What changed:**

- **C3 — Thesis writer.** New `app/intelligence/theses.py`: `build_thesis_row` (pure row construction) and `synthesize_theses_from_relations` (union-find clustering over binary `semantic_relations` within a domain; supports `dry_run`). Shared tier validation in `app/intelligence/tiers.py` (`validate_writer_tier`, `WRITER_TIERS = ("t2", "t3", "t4")`).
- **C3 CLI — `nexus theses synthesize`.** New `app/cli/theses.py`. Options: `--domain` (required), `--min-strength` (default 0.6), `--dry-run`, `--db-url`, `--json`. Clusters same-family capsules connected by strong relations into `theses` rows; no automatic extraction-graph trigger.
- **C4 — Decision artefact writer.** New `app/intelligence/decision_artefacts.py`: `build_decision_artefact_row` (pure row construction; this PR emits `artefact_type="memo"` only).
- **C4 CLI — `nexus artefacts create`.** New `app/cli/artefacts.py`. Options: `--domain`, `--question`, `--answer`, `--capsule-id` (repeatable), `--thesis-id` (repeatable), `--db-url`, `--json`. Manual one-at-a-time creation; no batch/backfill mode.
- **DB-bound integration tests.** New `tests/intelligence/test_reasoning_layer_db.py` (`@pytest.mark.slow`): real Postgres, mocked LLM — `judge_capsules` unary relation, `classify_relations` binary relation, and C1→C2→C3 thesis round-trip.
- **New unit tests.** `test_theses.py` (4), `test_decision_artefacts.py` (2), `test_tiers.py` (2). CLI `--help` smoke tests appended to `test_cli_e2e.py`.

**Why:** Closes the Phase C deferrals for first `theses` and `decision_artefacts` writers without wiring automatic per-document triggers that Phase E's consolidation/lifecycle worker would likely replace. Both writers are standalone + CLI-accessible for manual/reviewed use.

**Migration / setup:** None. Requires populated `semantic_capsules` and `semantic_relations` (from extraction or `nexus capsules backfill` + re-extract) before `nexus theses synthesize` can cluster anything. Automatic thesis/artefact creation remains Phase E scope.

**Discovered (not fixed):** Pre-existing `capsule_segments.role` CHECK mismatch — `build_capsule_row` writes `role="support"` but migration `0005_semantic_capsules.py`'s `ck_capsule_segments_role` CHECK only allows `"supports"` (plural). Breaks real-DB capsule writes (backfill and extraction dual-write); unrelated to this PR slice. Logged in `TODO.md`; surfaced while running the full test suite against real Postgres for Task 5.

## 2026-06-14 — Phase D Residual: Token-Budget Assembly + Evidence-Path UI

Closed the two buildable-now residual items from Phase D on branch `claude/phase-d-residual`.

**What changed:**

- **Token-budget context assembly.** `_run_retrieve_capsules` now assembles score-ranked capsules under the active pack's `context_assembly.max_tokens_by_tier["T2"]` budget instead of a flat `top_k` slice. Two pure helpers: `estimate_tokens(text)` (~4 chars/token heuristic) and `_assemble_within_budget(scored, top_k, token_budget)` (greedy by score; `top_k` caps the count; always keeps the top block; `None` budget → flat `top_k`).
- **Evidence-path UI.** New `CitationEvidence` model and `ChatCitation.evidence` field. After assembly, `_run_retrieve_capsules` runs one `capsule_segments ⨝ spans` query for the selected capsules and shapes it via `_build_evidence_map` (≤ `_MAX_EVIDENCE_SPANS=5` per capsule, each excerpt truncated to `_EVIDENCE_EXCERPT_CHARS=280`). `format_result` carries `evidence` into each citation. The web `CitationList` renders an expandable "Evidence" subsection (span index + excerpt) in the citation panel, omitted when empty.

**Why:** Retrieval now honors the pack's declared context budget rather than an arbitrary count, and answers expose the underlying span evidence for each cited capsule — improving grounding transparency.

**Migration / setup:** None. No schema change; `context_assembly` was already parsed on the pack. `max_tokens_by_tier["T3"]`/`["T4"]` remain unused (chat answers run on T2). The richer `context_assembly.include` categories and `ordering: evidence_strength` stay deferred to Phase E (they need the relation graph / lifecycle / evidence-quality signals).

## 2026-06-12 — Phase D: Retrieval & UI Over Meaning

Cut `/chat/answer` over from span-based retrieval to semantic-capsule retrieval across commits `d3183bc`–`92930a8` on branch `claude/phase-d-retrieval-ui`.

**What changed:**

- **D1 — Migration 0006: HNSW index.** Adds `ix_semantic_capsules_embedding_hnsw` on `semantic_capsules.embedding` (`vector_cosine_ops`, `m=16`, `ef_construction=64`). `CONCURRENTLY` is omitted because Alembic wraps migrations in a transaction.
- **D2 — `classify_intent.py` prompt.** New `app/intelligence/prompts/classify_intent.py`: `IntentClassification` schema, `SYSTEM_PROMPT`, `build_classify_prompt(question, intent_names)` for LLM query-intent classification against the active pack's `query_intents`.
- **D3 — `compute_hybrid_score`.** Telos-aware re-ranking blend: five active components (semantic similarity, domain object-type match, source authority, recency, salience) and two stubbed at `0.0` (relation relevance, evidence quality). Object-type match uses rank-based decay `_PRIORITY_SCORES = [1.0, 0.5, 0.25, 0.1]` over the intent's `retrieval_priorities`; recency is min-max normalized over the candidate set.
- **D4 — Chat graph rewrite.** `app/intelligence/chat.py` replaced its span graph with a four-node `StateGraph`: `classify_intent → retrieve_capsules → [conditional] → generate_answer → format_result`. `retrieve_capsules` runs HNSW cosine search (filtered to `lifecycle_state="active"`, `fetch_k = top_k * 3`) and applies `compute_hybrid_score`. `run_chat_with_context` loads a domain pack from `settings.default_pack_id` when no pack is passed, so existing callers work unchanged. `ChatCitation` now carries `capsule_id`, `document_title`, `url`, `score`, `object_type`, `object_family`, `lifecycle_state`, and `summary` (replacing `span_id`/`claim_ids`).
- **D5 — `default_pack_id` config.** New `settings.default_pack_id = "personal_ai_tech"` in `app/config.py`.
- **D6 — Capsule answer prompt.** `chat_answer.py`'s `build_user_prompt` now emits capsule blocks (`[C1]`, `Title:`, `URL:`, `Object type:`, `Score:`, `Capsule:`).
- **D7 — CLI + web UI.** `app/cli/render.py` citations table renamed "Span"→"Capsule" (reads `capsule_id`). `web/src/api/client.ts` `ChatCitation` type updated; `web/src/components/CitationList.tsx` rewritten with enriched cards — lifecycle dot (green/amber/gray), uppercase object-type pill badge, inline truncated summary, expandable panel.
- **New unit tests.** `test_chat_intent.py` (4), `test_chat_scoring.py` (5), `test_chat_graph.py` (6). Obsolete span-based integration tests removed from `tests/test_chat_graph.py` (1 observability test retained).

**Why:** Retrieval now operates over durable v0.7 semantic capsules rather than raw spans, so answers are grounded in deduplicated, lifecycle-managed meaning and ranked by telos-aware relevance instead of cosine distance alone.

**Migration / setup:** Run `alembic upgrade head` to create the HNSW index (migration 0006). `relation_relevance` and `evidence_quality` scoring weights remain stubbed at `0.0` pending Phase E relation-graph and evidence-quality signals; `source_authority` is stubbed at a uniform `0.5` until a source-authority field exists.

## 2026-06-11 — Phase C: Reasoning Layer

Landed the Phase C reasoning nodes across commits `af55ed0`–`ac769a2` on branch `claude/compassionate-varahamihira-1d61fa`.

**What changed:**

- **C1 — `judge_capsules` node.** New graph node wired after `store_claims`. Queries capsules with `escalation_state="flagged"`, reconstructs a minimal `SemanticObject` via `_capsule_to_obj_for_judge`, calls the T2 judge (`JudgeVerdict`), writes unary `SemanticRelation` rows (`target_capsule_id=NULL`), and updates capsule `escalation_state` to `"escalated"` or `"reviewed"`. Respects a per-run T2 budget via `t2_calls_used` on `ExtractionState`.
- **C2 — `classify_relations` node.** New graph node wired after `judge_capsules`. Groups same-document capsule pairs by `object_family`, calls the T2 classifier (`RelationClassification` from `classify_relations.py`), skips `"none"` results, and writes binary `SemanticRelation` rows (`source_capsule_id` + `target_capsule_id` both set). Shares the `t2_calls_used` budget counter with `judge_capsules`.
- **C3 — `classify_relations.py` prompt.** New `app/intelligence/prompts/classify_relations.py`: `RelationClassification` Pydantic schema, `build_relation_prompt()`, `SYSTEM_PROMPT` for the T2 relation classifier.
- **C4 — `ExtractionState` extensions.** Four new fields: `stored_capsule_ids` (output of `store_claims`, input to `judge_capsules`), `judge_results`, `relation_ids`, `t2_calls_used`. `run_with_context` initial state now includes all four.
- **C5 — Graph wiring helpers.** `_resolve_t2_model(pack, fallback)` reads `pack.model_extra["models"]["t2"]`. `_capsule_to_obj_for_judge(capsule)` reconstructs a minimal `SemanticObject` from a capsule row.
- **C6 — Backfill error isolation.** `backfill._write_batch` wraps commit in try/except; `capsules_written` / `capsule_segments_written` counters increment only after successful commit; FK `IntegrityError` from orphaned span refs is caught and appended to `result.errors`.
- **C7 — `slow` marker.** `pyproject.toml` registers the `slow` pytest marker. `tests/test_validation_harness.py` adds 5 integration tests (`@pytest.mark.slow`) for text ingest, RSS ingest, status, document inspection, and semantic search. Run with `-m "not slow"` to skip in fast-unit CI.
- **New unit tests.** `test_capsules.py` (7 tests for `build_capsule_row`), `test_judge_wiring.py` (6 tests for `_resolve_t2_model` and `_capsule_to_obj_for_judge`), `test_relation_classification.py` (9 tests for `build_relation_prompt`, `RelationClassification`, and `classify_relations` short-circuit / "none"-skip).

**Why:** Activates the knowledge-graph relation layer. `semantic_relations` is now populated at extraction time rather than being schema-only. Establishes the T2 budget-sharing pattern needed for any additional reasoning nodes in Phase D+.

**Migration / setup:** No new schema migrations required (migration 0005 already includes `semantic_relations`). Existing deployments gain relation rows automatically on the next extraction run. Run `nexus capsules backfill` to populate capsule rows for Phase A/B data before re-extracting if needed.

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
