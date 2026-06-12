# Phase C — Reasoning Layer (C1+C2) + Phase B Test Follow-ups

**Branch:** `claude/compassionate-varahamihira-1d61fa`
**PR:** [#20](https://github.com/RavindraTarunokusumo/Nexus/pull/20)
**Merge commit:** `75c3415`
**Merged at:** 2026-06-12T20:45:33Z
**Merged by:** RavindraTarunokusumo

## Summary

Wired the T2 reasoning layer into the extraction graph: a T2 evidence-sufficiency judge
(`judge_capsules`) and a T2 semantic relation classifier (`classify_relations`), both writing
`SemanticRelation` rows and sharing a per-source T2 budget counter. Also cleared the Phase B
test-plan WARN follow-ups (P1/P2a/P2b) and added the Phase 2 CLI validation harness.

Plan: [`docs/superpowers/plans/2026-06-11-phase-c-reasoning-layer.md`](../../superpowers/plans/2026-06-11-phase-c-reasoning-layer.md)
Spec: [`docs/superpowers/specs/2026-06-11-phase-c-reasoning-layer-design.md`](../../superpowers/specs/2026-06-11-phase-c-reasoning-layer-design.md)

## Tasks Completed

**WS1 — Phase B test-plan follow-ups**

- [x] P1 — `nexus capsules backfill --help` smoke test appended to `tests/test_cli_e2e.py` (commit: `af55ed0`)
- [x] P2a — 7 pure unit tests for `build_capsule_row` in `tests/intelligence/test_capsules.py`; no DB required (commit: `45eb329`)
- [x] P2b — Fixed orphaned-span `IntegrityError` in `app/intelligence/backfill.py::_write_batch`; counters now increment only after successful commit; regression test appended to `tests/intelligence/test_capsule_backfill.py` (commit: `e5e48a9`)

**WS2 — Phase 2 Validation Harness**

- [x] `tests/test_validation_harness.py` — 5 `@pytest.mark.slow` integration tests exercising text ingest, RSS ingest, status, document inspection, and semantic search CLI paths; `slow` marker registered in `pyproject.toml`; skip with `-m "not slow"` (commit: `e2c759d`)

**WS3 — Phase C C1: judge_capsules**

- [x] `ExtractionState` extended with `stored_capsule_ids`, `judge_results`, `relation_ids`, `t2_calls_used` (commit: `47b8440`)
- [x] `judge_capsules` nested node — queries flagged capsules, calls T2 judge (`JudgeVerdict`), writes unary `SemanticRelation` rows (`target_capsule_id=capsule.id` self-reference), updates capsule `escalation_state` to `"escalated"/"resolved"`, respects T2 budget (commit: `3860eec`)
- [x] `_resolve_t2_model` and `_capsule_to_obj_for_judge` module-level helpers (commit: `3860eec`)
- [x] 6 unit tests in `tests/intelligence/test_judge_wiring.py` (commit: `c0e6ee2`)

**WS3 — Phase C C2: classify_relations**

- [x] `app/intelligence/prompts/classify_relations.py` — `RelationClassification` schema + `build_relation_prompt()` + `SYSTEM_PROMPT` (commit: `c1041cb`)
- [x] `classify_relations` nested node — groups same-family capsule pairs, calls T2 classifier, skips `"none"` results, writes binary `SemanticRelation` rows, shares T2 budget with `judge_capsules` (commit: `6d72c2a`)
- [x] `_CANONICAL_RELATION_TYPES` frozenset to map LLM output to DB-constrained `relation_type`; domain-specific types stored in `domain_relation_type` (commit: `6e927ba`)
- [x] Graph rewired: `store_claims → judge_capsules → classify_relations → update_status` (commit: `6d72c2a`)
- [x] 9 unit tests in `tests/intelligence/test_relation_classification.py` (commits: `34c712e`, `b305bbd`)

**Pre-PR gates**

- [x] `/simplify` — `defaultdict` import moved to top-level (commit: `ac769a2`)
- [x] `doc-updater` — `architecture.md`, `database.md`, `patterns.md`, `testing.md`, `index.md`, `changelog.md` updated (commits: `0b74755`–`197011f`)

**Code-review fixes (Opus review on PR #20)**

- [x] `judge_capsules`: `relation_type="other"` (canonical); `domain_relation_type` carries `"judge_escalated"/"judge_cleared"`; `target_capsule_id=capsule.id` to satisfy XOR CHECK; `escalation_state="resolved"` not invalid `"reviewed"` (commit: `6453379`)
- [x] `classify_relations`: domain relation types mapped through `_CANONICAL_RELATION_TYPES` to satisfy `ck_semantic_relations_relation_type` CHECK (commit: `6e927ba`)
- [x] `RelationClassification.polarity` constrained to `Literal["positive","negative","neutral"] | None` (commit: `b7ed3c4`)
- [x] Extracted `_run_classify_relations` to module level; node tests now `await` it directly with controlled state (commit: `b305bbd`)

## Test Results

9/9 tests passing in `test_relation_classification.py` (pure, no DB).
6/6 tests passing in `test_judge_wiring.py` (pure, no DB).
7/7 tests passing in `test_capsules.py` (pure, no DB).
Validation harness (`test_validation_harness.py`) requires live DB — skipped with `-m "not slow"`.

## What Phase C Did Not Do (Phase C+ backlog)

- **C3** — Thesis layer: synthesise `theses` rows from capsule clusters.
- **C4** — Decision artefacts: emit `decision_artefacts` rows from answered queries.
- DB-bound integration tests for `judge_capsules` and `classify_relations` node paths (deferred to Phase C integration suite).
