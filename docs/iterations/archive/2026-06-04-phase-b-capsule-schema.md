# Phase B — Capsule-Schema Foundation

**Branch:** `claude/phase-b-implementation`
**PR:** [#19](https://github.com/RavindraTarunokusumo/Nexus/pull/19)
**Merge commit:** `166c65d`
**Merged at:** 2026-06-04T14:39:17Z
**Merged by:** RavindraTarunokusumo

## Summary

Promoted Phase A's in-memory v0.7 `SemanticObject` layer to six durable database
tables and retired the legacy `ExtractedClaim` / `ExtractionOutput` dual-path eval
contract. Chat / API still read `claims`; retrieval cutover is deferred to Phase D.

Plan: [`docs/superpowers/plans/2026-06-02-phase-b-capsule-schema.md`](../../superpowers/plans/2026-06-02-phase-b-capsule-schema.md).
Test plan: [`docs/test-plan-phase-b-capsule-schema.md`](../../test-plan-phase-b-capsule-schema.md).

## Tasks Completed

**B1 — Alembic migration 0005 + ORM models**
- [x] Six new tables: `semantic_capsules`, `capsule_segments`, `semantic_relations`, `theses`, `decision_artefacts`, `domain_packs`. 384-dim `bge-small-en-v1.5` embeddings on capsules; 15-value `core_type` / 9-state `lifecycle_state` / 4-state `escalation_state` CHECK constraints; named FK constraints; `idempotency_key UNIQUE` for safe re-runs; `domain_packs.parent_pack_id` self-FK reserved for Phase D pack inheritance. `tests/db/test_capsules_migration.py` (commit: `620a191`)
- [x] ORM models for all six tables (commit: `00b8f38`)
- [x] Migration round-trip + downgrade verification (commit: `d530c18`)

**B2 — Dual-write from `projection.project()` + `extraction.store_claims`**
- [x] `store_claims` writes a `SemanticCapsule` + N `CapsuleSegment` rows in the same transaction as the legacy `Claim` + `ClaimEvidence` writes; capsule text embedded at write time via shared `bge-small-en-v1.5` singleton (commit: `f84decd`)
- [x] `tests/intelligence/test_capsules_dual_write.py` — happy path, multi-source-ref, transaction atomicity, embedding present, idempotency_key deterministic (commit: `f542cf6`)
- [x] Code-review fixes (commit: `3c3c713`)
- [x] Integration polish (commit: `6d4c2df`)

**B3 — Backfill from `Claim.entities_json["_v0_7"]` blobs**
- [x] `nexus capsules backfill [--dry-run] [--batch-size N]` CLI — reads existing `_v0_7` stash payloads left by Phase A and constructs capsule rows; idempotent via `build_capsule_idempotency_key` (commit: `9952471`)
- [x] `tests/intelligence/test_capsule_backfill.py` — pure unit + idempotency + dry-run + skip-no-v07 + multi-source-ref (commit: `c99aefe`)
- [x] CLI wiring + integration (commit: `1cb9aab`)

**B4 — v3 source-type profile detection**
- [x] Replaces the `supported_source_types[0]` MVP fallback in `_resolve_pack_and_source_type` with a 4-pass classifier: URL hostname match (suffix-spoof safe) → title regex (case-insensitive with `(?-i)` opt-out) → pack fallback → safety net. `SourceTypeProfile` gained `url_domains` and `title_regex` fields; AI pack's 10 profiles populated. `tests/intelligence/test_resolve_pack_and_source_type.py` (23 tests) (commit: `bc05a61`)
- [x] Review fixes + edge cases (commit: `42dd3f0`)

**B5 — Eval-runner port + legacy schema retirement**
- [x] `app/evaluation/runner.py` ported to `response_model=SemanticExtractionOutput`; new `SemanticObjectJudge`; new gold set `evals/gold/semantic_objects/ai_tech_v3.yaml` (10 examples, 6 mvp_claim_types); `nexus eval run` + `eval calibrate` accept `--pack-id` and `--source-type` overrides. DELETED: `ExtractedClaim`, `ExtractionOutput`, `app/intelligence/prompts/extract_claims.py`, `ClaimExtractionJudge`. Eval tests ported to `SemanticObjectJudge` + `SemanticExtractionOutput` (commit: `2031b06`)
- [x] SUT overrides + aggregator denominator fix (commit: `0332700`)

**Step 6 — Pre-PR gates**
- [x] **`/simplify`** — New `app/intelligence/capsules.py` consolidates `get_embedder()`, `build_capsule_idempotency_key`, and `build_capsule_row`. Both `store_claims` (dual-write) and `capsule_from_claim` (backfill) delegate to `build_capsule_row` — single source of truth for the SemanticObject → SemanticCapsule + CapsuleSegment mapping. Precompiled `title_regex` on pack load; one-time `urlsplit` per classifier call; 6 dead/redundant paths dropped (commit: `4a052b4`)
- [x] **`doc-updater`** — `architecture.md`, `database.md`, `patterns.md`, `testing.md`, `cli.md`, `specs/domain-packs.md`, `specs/pipeline.md`, `changelog.md`, `index.md` updated (commit: `7a39b45`)
- [x] **`security-review`** — No HIGH or MEDIUM findings. Path-traversal guards still effective; URL parsing resists suffix spoof; JSONB handling via Pydantic validation.
- [x] **`test-plan-writer`** — Verdict: WARN. 3 follow-up coverage gaps documented (see below).
- [x] **`test-plan-writer` follow-up** — Documented as separate TODO items (P1 / P2); merged without blocking.

## Test Results

177 tests passing locally across `tests/intelligence`, `tests/evaluation`, `tests/domain_packs`. DB-bound tests (`tests/db/`, `test_capsules_dual_write.py`, `test_capsule_backfill.py`) require Docker — exercised in CI.

## Test Plan Follow-Up Gaps (WARN)

These were documented but not blocked on merge; carry forward as ongoing items:

- **P1** — `nexus capsules backfill --help` CLI smoke test in `test_cli_e2e.py`
- **P2** — Direct unit test for `build_capsule_row`
- **P2** — Orphaned-span backfill skip path

## What Phase B Did Not Do (Phase C+ backlog)

- Wire the A7 T2 judge prompt behind a feature flag; write escalations to `semantic_relations`.
- Relation classification (supports/contradicts/refines/qualifies/supersedes).
- Thesis layer synthesis (`theses` rows from capsule clusters).
- Decision artefact emission (`decision_artefacts` rows from answered queries).
- Capsule retrieval (pgvector HNSW on `semantic_capsules.embedding`) — Phase D.
- Pack inheritance resolution (`inherits_from` YAML loader; consumer of `domain_packs.parent_pack_id`) — Phase F.
