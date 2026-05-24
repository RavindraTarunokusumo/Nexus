# Eval Framework — LLM-as-a-Judge

**Branch:** `feature/eval-framework-impl`
**PR:** [pending]
**Merge commit:** [pending]
**Merged at:** [pending]
**Merged by:** RavindraTarunokusumo

## Summary

Implemented a full LLM-as-a-Judge evaluation framework for Nexus. Three new Postgres tables track gold-set registrations, run metadata, and per-example verdicts. A new `app/evaluation/` package covers dataset loading (Pydantic + SHA-256), deterministic metrics (P/R/F1, P@k, nDCG@k, Jaccard alignment), a LLM judge pipeline (`ClaimExtractionJudge` active; `BriefSynthesisJudge`/`GroundedAnswerJudge` Phase 4 stubs), an async runner with per-example error tolerance and a budget gate, and Cohen's κ / Pearson r meta-evaluation. Six `nexus eval` CLI commands expose register, run, show, diff, and calibrate. Gold-set YAML files (30 claim-extraction, 20 span-retrieval examples) and 6-seed human labels for judge calibration are included.

## Tasks Completed

- [x] **Plan** — 10-task TDD implementation plan written (commit: `c6e4861`)
- [x] **T1: ORM models + migration 0003** — `EvalDataset`, `EvalRun` (Numeric cost, created_at), `EvalResult`; Alembic migration with FK indexes (commits: `93d575d`, `6cf6af1`, `df3ef5f`)
- [x] **T2: `app/evaluation/datasets.py`** — `GoldClaim`, `ClaimExtractionExample`, `SpanRetrievalExample`, `Dataset`, `load_dataset` with SHA-256 checksum (commit: `bd78643`)
- [x] **T3: `app/evaluation/metrics.py`** — `precision_recall_f1`, `precision_at_k`, `ndcg_at_k`, `align_claims` (Jaccard greedy matching) (commit: `205efa2`)
- [x] **T4: `app/evaluation/prompts/claim_extraction_judge.py`** — `JUDGE_SYSTEM_PROMPT`, `build_judge_prompt`, `ClaimPairVerdict` Pydantic model (commit: `a4f3519`)
- [x] **T5: `app/evaluation/judges.py`** — `ClaimExtractionJudge` (active, name = "claim_extraction_judge_v1"); `BriefSynthesisJudge`, `GroundedAnswerJudge` (Phase 4 stubs) (commit: `ac8b317`)
- [x] **T6: `app/evaluation/runner.py`** — `execute_run`, `SUTConfig`, `EvalRunResult`, `_score_example`, `_persist_result`, `_aggregate_scores`; budget gate; per-example error tolerance (commit: `359890d`)
- [x] **T7: `app/evaluation/meta_eval.py`** — `compute_kappa` (Cohen's κ), `compute_pearson`, `load_human_labels` (commit: `034e3a1`)
- [x] **T8: `app/cli/eval.py`** — `eval_app` sub-app: `register-dataset`, `list-datasets`, `run`, `show`, `diff`, `calibrate`; wired into `app/cli/main.py` (commit: `745ab21`)
- [x] **T9: Gold-set YAML files** — `evals/gold/claim_extraction/ai_tech_v1.yaml` (30 examples, all 11 claim types), `evals/gold/span_retrieval/queries_v1.yaml` (20 queries), `evals/human_labels/claim_extraction.yaml` (6-seed labels) (commit: `6290347`)
- [x] **T10: TODO.md deferred items** — eval framework deferred items appended (commit: `86a72d2`)
- [x] **Critical fixes** — cost tracking (token accumulation), correct SUT system prompt, `EvalTask.value` enum comparison (commit: `8a72ab5`)
- [x] **Doc-updater** — `docs/database.md` (3 tables), `docs/commands.md` (6 commands), `docs/architecture.md` (eval package + data-flow), `docs/index.md` (module map) (commit: `1e70d28`)
- [x] **Security fixes** — CLI 50 USD budget ceiling guard, `database_url.strip()`, budget gate comment (commit: `f7f4049`)

## Key Decisions

- **Hybrid judge architecture** — Nexus owns harness/schemas/persistence; judges run via existing `LLMClient.complete_json` (auto-records `agent_runs` row). No new HTTP client needed.
- **Corpus-independent span retrieval** — `gold_span_texts: list[str]` (text substrings) instead of `gold_span_ids: list[UUID]`, so the gold set doesn't require a pre-ingested corpus.
- **`EvalRun.total_cost_usd` as `Numeric(12,6)`** — not `Float`; financial aggregates require precision.
- **`EvalDataset.task` FK comparison uses `.value`** — `EvalTask` is `str`-Enum; explicit `.value` is safe across Python 3.11 `Enum.__str__` changes.
- **Budget gate is approximate** — checked *before* each example; one example may overshoot by its own cost. CLI enforces a 50 USD hard ceiling.
- **`test_zero_agreement_beyond_chance` test fix** — fully disjoint categories yield κ = 0.0, not negative. Changed to overlapping anti-agreement (κ = −1.0) to validate below-chance detection correctly.
- **SUT uses production extraction prompt** — `runner.py` imports `SYSTEM_PROMPT` from `app.intelligence.prompts.extract_claims` (not the judge prompt) for realistic SUT evaluation.

## Test Results

194 tests passing (59 new: 7 migration smoke, 12 datasets, 19 metrics, 7 judges, 6 runner, 8 meta-eval). Pre-commit hooks green. No regressions into existing extraction, ingestion, CLI, or observability flows.

## Lessons

- **GitNexus detect_changes false-positive** — Adding `eval_app` to `main.py` makes `_run` appear as a "touched" symbol, flagging all existing CLI flows (Extract, Search, Ingest) as affected processes. Change was additive-only; all existing tests confirmed no regression.
- **Cohen's κ with disjoint rater categories** — When both raters have zero overlap in their marginal distributions, expected agreement pe = 0 and κ = 0, not negative. Need shared categories with positive marginals to produce κ < 0.
- **`asyncio.run()` in CLI commands** — importing top-level `app.config.settings` in a CLI module fails when no `.env` is present. Lazy import inside the command body defers Settings construction to actual execution time.
- **`subagent-driven-development` parallelism** — Dispatching fresh subagents per task with two-stage review (spec compliance then code quality) caught the `started_at` type annotation mismatch, missing `created_at` on `EvalRun`, `Float` vs `Numeric` for cost, wrong SUT system prompt, and dead `total_cost` variable — all before merge.
