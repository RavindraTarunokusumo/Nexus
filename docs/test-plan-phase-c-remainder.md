# Test Plan — Phase C Remainder: Thesis Writer, Decision Artefact Writer, DB Integration Tests

| Field | Value |
|---|---|
| **VERDICT** | WARN |
| **MERGE_BLOCKING** | no |
| **Date** | 2026-07-02 |
| **Branch** | `claude/telos-residuals-c` |
| **Diff base** | `main..HEAD` (4 commits per `TODO.md`: `c51ddea` C3a, `a4ff9e4` C4a, `a0ffafe` C3b/C4b CLI, `5199516` C5 DB tests; ~11 files touched in `app/intelligence/`, `app/cli/`, `tests/intelligence/`, `tests/test_cli_e2e.py`) |
| **Author** | test-plan-writer subagent |

**Verdict rationale:** P0 acceptance paths from the accepted design
(`docs/superpowers/specs/2026-07-02-phase-c-remainder-design.md`) are covered at a
minimum viable level: pure row builders, one mocked-session clustering test, and three
real-Postgres integration tests that all pass. Four gaps prevent PASS: (1) the `dry_run`
rollback fix in `synthesize_theses_from_relations` has **no regression test** proving
rows are not persisted — the bug was found and fixed on this branch but never checked
into the suite; (2) union-find clustering edge cases called out in the design (3+
capsule chains, contradict/negative-polarity split within a cluster, unary/self-reference
interaction) have **no dedicated tests** — only the 2-capsule happy path is exercised;
(3) CLI argument validation (`--capsule-id` malformed UUID, `--min-strength` out of
`[0,1]`) is **unguarded in code and untested**; and (4) the new `--help` smoke tests in
`test_cli_e2e.py` are **brittle** — they fail in practice because Rich ANSI escape codes
split option strings (e.g. `\x1b[1m-domain` vs literal `--domain`) even though
`exit_code == 0`. All gaps are non-blocking follow-ups. Pre-existing
`capsule_segments.role="support"` CHECK failures (6 tests in backfill/dual-write) are
correctly scoped in `TODO.md` Ongoing as **out-of-scope / pre-existing**, not gaps in
this PR's own coverage.

---

## 1. Summary

Phase C remainder ships the first standalone writers for `theses` (C3) and
`decision_artefacts` (C4), Typer CLI commands (`nexus theses synthesize`,
`nexus artefacts create`), shared `validate_writer_tier` extraction
(`app/intelligence/tiers.py`), and DB-bound integration tests for
`judge_capsules` / `classify_relations` / thesis round-trip (C5). No extraction-graph
or `/chat/answer` wiring — Phase E owns automatic triggering.

Key implementation details verified in source:

- `build_thesis_row` validates `created_by_tier` via `validate_writer_tier` and
  `confidence ∈ [0, 1]`.
- `build_decision_artefact_row` validates tier only (no confidence field).
- `synthesize_theses_from_relations` union-finds over binary relations
  (`target_capsule_id IS NOT NULL`, `strength >= min_strength`, domain-filtered),
  splits supporting vs contradicting by `polarity == "negative"` or
  `relation_type == "contradicts"`, and on `dry_run=True` calls `session.add_all` then
  `await session.rollback()` (not merely skipping `commit`).
- `nexus artefacts create` parses `--capsule-id` / `--thesis-id` with bare
  `uuid.UUID(...)` — no Typer validator or friendly error handling.

**Test execution (this session):**

| Suite | Command | Result |
|---|---|---|
| Phase C unit tests | `pytest tests/intelligence/test_theses.py tests/intelligence/test_decision_artefacts.py tests/intelligence/test_tiers.py -v --noconftest` | **8/8 PASS** |
| C5 DB integration | `DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5434/nexus pytest tests/intelligence/test_reasoning_layer_db.py -v -m slow` | **3/3 PASS** |
| Broader fast suite | `pytest tests/intelligence/ tests/test_cli_e2e.py -v -m "not slow"` | **174 pass, 9 fail** — 6 failures are pre-existing `ck_capsule_segments_role` (`role="support"` vs `"supports"`); 3 failures are CLI `--help` substring assertions broken by Rich ANSI (includes 2 new Phase C help tests + 1 pre-existing `test_capsules_backfill_help_works`) |

---

## 2. Scope

### In scope

- **C3a** — `build_thesis_row`, `synthesize_theses_from_relations` (union-find clustering).
- **C3b** — `nexus theses synthesize` CLI (`--domain`, `--min-strength`, `--dry-run`, `--json`).
- **C4a** — `build_decision_artefact_row`.
- **C4b** — `nexus artefacts create` CLI.
- **C5** — DB-bound `@pytest.mark.slow` tests: `judge_capsules`, `classify_relations`,
  C2→C3a round-trip.
- **Shared** — `validate_writer_tier` / `WRITER_TIERS` in `app/intelligence/tiers.py`.

### Out of scope

- Automatic thesis/artefact creation triggers (Phase E).
- Cross-document consolidation clustering (Phase E).
- Phase D residuals (context assembly, hybrid scoring, legacy claims cutover).
- `classify_relations` "none" → no-row DB test (listed in design spec §Components item 5
  but **not** in the implementation plan Task 5 or the landed test module — noted as
  spec/plan drift, not a regression in landed plan scope).
- Pre-existing `capsule_segments.role="support"` CHECK violation (`TODO.md` Ongoing) —
  breaks 6 real-DB tests unrelated to Phase C remainder writers; discovered while
  validating this branch, confirmed pre-existing on `main`.

---

## 3. Environment Constraints

| Category | Status |
|---|---|
| Pure unit tests (`test_theses.py`, `test_decision_artefacts.py`, `test_tiers.py`) | Runnable locally with `--noconftest` |
| DB integration (`test_reasoning_layer_db.py`) | Requires real Postgres — `DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5434/nexus`; marked `@pytest.mark.slow` |
| CLI `--help` smoke (`test_cli_e2e.py`) | No DB required; **currently fails** substring assertions due to Rich ANSI formatting |
| LLM calls | None in Phase C tests — `AsyncMock` / canned `JudgeVerdict` / `RelationClassification` |

Local run commands:

```
# Phase C unit only
pytest tests/intelligence/test_theses.py tests/intelligence/test_decision_artefacts.py tests/intelligence/test_tiers.py -v --noconftest

# C5 DB integration
DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5434/nexus \
  pytest tests/intelligence/test_reasoning_layer_db.py -v -m slow
```

---

## 4. Coverage Mapping

| Acceptance Criterion | Test IDs | Status |
|---|---|---|
| **C3a** — `build_thesis_row` constructs valid `Thesis` with correct field mapping | TH-1 | Covered |
| **C3a** — `created_by_tier` validated (`t2`/`t3`/`t4` only) | TH-2, TR-1, TR-2, DA-2 | Covered (tier rejection); t3/t4 acceptance only via TR-1 testing `t2` |
| **C3a** — `confidence ∈ [0, 1]` enforced | TH-3 | Covered (upper bound only — see Gap section) |
| **C3a** — Union-find clusters connected capsules; isolated capsules below `min_cluster_size` skipped | TH-4 | Covered (2-capsule path only; cap_c isolated) |
| **C3a** — 3+ capsule chain clusters into one thesis | *(no test)* | **Gap (P1)** |
| **C3a** — Contradicting/negative-polarity edges split `supporting` vs `contradicting` within cluster | *(no test)* | **Gap (P1)** |
| **C3a** — Unary/self-referencing relations do not spuriously form multi-capsule clusters | *(no test)* | **Gap (P2)** — query filters `target_capsule_id IS NOT NULL` but does not exclude `source == target`; single-node self-ref clusters are harmless at `min_cluster_size=2`, but interaction with binary edges is untested |
| **C3a** — `dry_run=True` reports clusters but does not persist rows | *(no test)* | **Gap (P0 follow-up)** — fix landed (`rollback` after `add_all`) but no regression test |
| **C3a** — Zero qualifying relations returns `[]` | *(no test)* | **Gap (P2)** |
| **C3a** — `min_strength` filters weak edges | *(no test)* | **Gap (P2)** |
| **C3b** — `nexus theses synthesize --help` smoke | CLI-1 | **Implemented but failing** (ANSI brittle assertion) |
| **C3b** — `nexus theses synthesize --dry-run` CLI end-to-end | *(no test)* | **Gap (P1)** |
| **C4a** — `build_decision_artefact_row` basic shape | DA-1 | Covered |
| **C4a** — `created_by_tier` validated | DA-2 | Covered |
| **C4b** — `nexus artefacts create --help` smoke | CLI-2 | **Implemented but failing** (ANSI brittle assertion) |
| **C4b** — `nexus artefacts create` writes real `DecisionArtefact` row | *(no test)* | **Gap (P2)** — manual CLI path has no DB integration test |
| **C4b** — Malformed `--capsule-id` / `--thesis-id` handled gracefully | *(no test)* | **Gap (P1)** — unguarded `uuid.UUID()` raises raw `ValueError` |
| **C5** — `judge_capsules` writes real unary self-reference + escalates capsule | RL-1 | Covered |
| **C5** — `classify_relations` writes real binary relation with correct FKs | RL-2 | Covered |
| **C5** — C2→C3a round-trip: relations cluster into real `Thesis` row | RL-3 | Covered (2-capsule minimum only) |
| **C5** — `classify_relations` "none" classification writes no row | *(no test)* | **Gap (P2)** — in design spec, omitted from landed plan/tests |
| **Shared** — `validate_writer_tier` accepts `t2`/`t3`/`t4`, rejects others | TR-1, TR-2 | Partially covered — TR-1 only exercises `t2`; `t3`/`t4` not explicitly asserted |

---

## 5. Test Cases

### 5.1 Thesis writer (C3a) — `tests/intelligence/test_theses.py`

| ID | Priority | Test Name | What It Verifies | Status |
|---|---|---|---|---|
| TH-1 | P0 | `test_build_thesis_row_basic_shape` | All `Thesis` columns map correctly; `title` defaults `None` | **Implemented** |
| TH-2 | P0 | `test_build_thesis_row_rejects_invalid_tier` | `created_by_tier="t0"` → `ValueError` via `validate_writer_tier` | **Implemented** |
| TH-3 | P0 | `test_build_thesis_row_rejects_confidence_out_of_range` | `confidence=1.5` → `ValueError` | **Implemented** (upper bound only) |
| TH-4 | P0 | `test_synthesize_theses_from_relations_clusters_connected_capsules` | Mocked `AsyncSession`: A–B edge clusters; isolated C skipped; anchor = highest salience; `thesis_type` from `object_family` | **Implemented** (2-capsule only; does not assert `commit`/`rollback`; does not cover `dry_run`) |
| TH-5 | P1 | 3-capsule chain `A–B–C` → single thesis with 3 supporting members | Union-find transitive closure | **Gap** |
| TH-6 | P1 | Mixed `supports` + `contradicts` edges in one cluster → correct `supporting`/`contradicting` split | `_thesis_from_cluster` polarity logic | **Gap** |
| TH-7 | P0 | `dry_run=True` → `add_all` called, `rollback` called, `commit` not called, 0 `theses` rows in DB | Regression for branch bug fix | **Gap** |
| TH-8 | P2 | Empty relations list → `[]`, no `add_all` | Graceful no-op per spec | **Gap** |
| TH-9 | P2 | `confidence=-0.1` → `ValueError` | Lower bound of `[0, 1]` | **Gap** |

### 5.2 Decision artefact writer (C4a) — `tests/intelligence/test_decision_artefacts.py`

| ID | Priority | Test Name | What It Verifies | Status |
|---|---|---|---|---|
| DA-1 | P0 | `test_build_decision_artefact_row_basic_shape` | `memo` artefact fields map correctly | **Implemented** |
| DA-2 | P0 | `test_build_decision_artefact_row_rejects_invalid_tier` | `created_by_tier="t1"` → `ValueError` | **Implemented** |
| DA-3 | P2 | `nexus artefacts create` DB round-trip (real Postgres) | One `decision_artefacts` row with linked capsule IDs | **Gap** |

### 5.3 Shared tier validation — `tests/intelligence/test_tiers.py`

| ID | Priority | Test Name | What It Verifies | Status |
|---|---|---|---|---|
| TR-1 | P1 | `test_validate_writer_tier_accepts_valid_tier` | `t2` accepted | **Implemented** |
| TR-2 | P0 | `test_validate_writer_tier_rejects_invalid_tier` | `t0` rejected | **Implemented** |
| TR-3 | P2 | `test_validate_writer_tier_accepts_t3_and_t4` | Both boundary tiers accepted | **Gap** |

### 5.4 DB integration (C5) — `tests/intelligence/test_reasoning_layer_db.py` (slow)

| ID | Priority | Test Name | What It Verifies | Status |
|---|---|---|---|---|
| RL-1 | P0 | `test_judge_capsules_writes_real_relation_row` | Flagged capsule → unary self-ref `SemanticRelation` + `escalation_state="escalated"` persists | **Implemented** |
| RL-2 | P0 | `test_classify_relations_writes_real_binary_relation` | Two capsules → binary `supports` relation with correct FKs | **Implemented** |
| RL-3 | P0 | `test_classify_relations_to_thesis_round_trip` | classify → `synthesize_theses_from_relations` → 1 `Thesis` with both capsule IDs in `supporting_capsule_ids` | **Implemented** (2-capsule minimum) |
| RL-4 | P1 | 3-capsule DB cluster round-trip | Seed 3 capsules + 2 relations forming a chain; assert 1 thesis with 3 members | **Gap** |
| RL-5 | P2 | `classify_relations` returns "none" → 0 new `semantic_relations` rows | Design spec §Components item 5 | **Gap** |
| RL-6 | P0 | `synthesize_theses_from_relations(dry_run=True)` → 0 rows in `theses` table after call | DB-level dry-run regression | **Gap** |

### 5.5 CLI smoke — `tests/test_cli_e2e.py`

| ID | Priority | Test Name | What It Verifies | Status |
|---|---|---|---|---|
| CLI-1 | P1 | `test_theses_synthesize_help_works` | `--help` exits 0; output mentions `--domain` | **Implemented but failing** — Rich ANSI splits `--domain` literal; `exit_code == 0` |
| CLI-2 | P1 | `test_artefacts_create_help_works` | `--help` exits 0; output mentions `--question` | **Implemented but failing** — same ANSI issue |
| CLI-3 | P1 | `test_theses_synthesize_dry_run_cli` | `CliRunner` invoke with `--dry-run`; assert 0 `theses` rows | **Gap** |
| CLI-4 | P1 | `test_artefacts_create_rejects_bad_capsule_id` | `--capsule-id not-a-uuid` → non-zero exit, friendly message | **Gap** — currently raw `ValueError` |
| CLI-5 | P2 | `test_theses_synthesize_rejects_min_strength_out_of_range` | `--min-strength 1.5` rejected or clamped | **Gap** — Typer accepts any float; no validation in orchestration |

---

## 6. Edge Cases and Negative Tests

| ID | Priority | Description | Status |
|---|---|---|---|
| NEG-1 | P0 | Invalid `created_by_tier` on `build_thesis_row` / `build_decision_artefact_row` | **Implemented** (TH-2, DA-2) |
| NEG-2 | P0 | `confidence` above 1.0 on `build_thesis_row` | **Implemented** (TH-3) |
| NEG-3 | P1 | `confidence` below 0.0 on `build_thesis_row` | **Not tested** |
| NEG-4 | P1 | Contradicting capsule in an otherwise supporting cluster | **Not tested** |
| NEG-5 | P1 | 3+ capsule transitive cluster | **Not tested** |
| NEG-6 | P0 | `dry_run` does not persist thesis rows (DB count assertion) | **Not tested** — critical regression hole |
| NEG-7 | P2 | Capsule with only unary self-reference relation (no binary edges) | **Not tested** |
| NEG-8 | P2 | `min_strength` threshold excludes weak edge → no thesis | **Not tested** |
| NEG-9 | P1 | Malformed UUID on `nexus artefacts create --capsule-id` | **Not tested**; code unguarded |
| NEG-10 | P2 | `synthesize` with wrong/empty domain → `[]` | **Not tested** |
| NEG-11 | — | `capsule_segments.role="support"` CHECK on real Postgres | **Pre-existing / out-of-scope** — 6 failing tests in backfill/dual-write; logged in `TODO.md` Ongoing; not introduced by Phase C remainder |

---

## 7. Gaps and Required Actions

| Gap ID | Priority | Description | Recommended Location |
|---|---|---|---|
| **GAP-1** | P0 | **`dry_run` DB regression test missing.** `synthesize_theses_from_relations` now rolls back after `add_all` when `dry_run=True` (lines 194–199 of `app/intelligence/theses.py`). No test asserts `session.rollback` is awaited or that `SELECT COUNT(*) FROM theses` is unchanged. The bug was found and fixed on this branch via manual spot-check only. | `tests/intelligence/test_theses.py` (mocked session: assert `rollback` called, `commit` not called) **and** `tests/intelligence/test_reasoning_layer_db.py` (RL-6: real DB count) |
| **GAP-2** | P1 | **Clustering edge cases untested.** Only 2-capsule `A–B` path covered (TH-4, RL-3). Missing: 3+ capsule chain, contradict/negative-polarity split within cluster, confidence = mean of edge confidences assertion. | `tests/intelligence/test_theses.py` (TH-5, TH-6 with mocked relations) |
| **GAP-3** | P1 | **CLI validation unguarded and untested.** `artefacts.py` uses `uuid.UUID(c)` without try/except; `theses.py` passes `--min-strength` through with no range check. No `CliRunner` negative tests. | `tests/test_cli_e2e.py` (CLI-4, CLI-5); optionally add Typer validators in `app/cli/artefacts.py` / `app/cli/theses.py` |
| **GAP-4** | P1 | **CLI `--help` smoke tests brittle.** New `test_theses_synthesize_help_works` and `test_artefacts_create_help_works` fail because Rich inserts ANSI codes between `-` and `domain`/`question`. Commands work (`exit_code == 0`). | Fix assertions: strip ANSI (`re.sub(r'\x1b\[[0-9;]*m', '', stdout)`) or match on `domain`/`question` without requiring contiguous `--` |
| **GAP-5** | P2 | **DB integration only covers 2-capsule minimum.** RL-3 does not prove union-find works for chains of 3+. | `tests/intelligence/test_reasoning_layer_db.py` (RL-4) |
| **GAP-6** | P2 | **`validate_writer_tier` t3/t4 acceptance not explicitly tested.** TR-1 only passes `t2`. | `tests/intelligence/test_tiers.py` (TR-3) |
| **GAP-7** | P2 | **No `nexus artefacts create` DB integration test.** C4b CLI write path unverified against real Postgres. | `tests/intelligence/test_reasoning_layer_db.py` or new `test_decision_artefacts_db.py` |
| **GAP-8** | P2 | **Design spec "none" classification no-row test absent.** Listed in accepted design §5 but omitted from plan Task 5. | `tests/intelligence/test_reasoning_layer_db.py` (RL-5) — post-merge if spec is re-affirmed |

**REQUIRED_ACTIONS** (post-merge follow-up, not blocking):

1. Add GAP-1 dry-run regression tests (mock + DB) before next manual use of `--dry-run`.
2. Add GAP-2 clustering edge-case unit tests (3-capsule chain, contradict split).
3. Fix GAP-4 help-test assertions; add GAP-3 CLI negative tests (and optionally input validators).
4. Add GAP-5 three-capsule DB round-trip when clustering correctness becomes load-bearing.

**Pre-existing / out-of-scope (do not block this PR):**

- `TODO.md` Ongoing item **Fix `capsule_segments.role="support"` CHECK violation** — causes 6 real-DB test failures in `test_capsule_backfill.py` and `test_capsules_dual_write.py`; confirmed unrelated to Phase C remainder; correctly logged as discovered during this branch's full-suite run, not introduced by it.

---

## 8. Fixtures and Setup Requirements

### Local (no DB, `--noconftest`)

- `test_theses.py::test_synthesize_theses_from_relations_clusters_connected_capsules` — uses
  `unittest.mock.AsyncMock` session; no fixtures.
- `test_decision_artefacts.py`, `test_tiers.py` — pure unit, no I/O.

### DB-required (slow)

- `tests/conftest.py` — `session_factory`, `clean_db`, `run_migrations` (same pattern as
  other intelligence DB tests).
- Requires Postgres with migrations at head; this session used
  `postgresql+asyncpg://nexus:nexus@localhost:5434/nexus`.
- LLM mocked via `AsyncMock` returning canned pydantic models.

### CLI e2e

- `test_cli_e2e.py` — `CliRunner` on `app.cli.main.app`; help tests need no DB.
- Functional CLI tests (dry-run, create artefact) would need `db_url` fixture like existing
  e2e patterns.

---

## 9. Out of Scope

| Area | Reason |
|---|---|
| Automatic thesis/artefact triggers | Phase E |
| Cross-document consolidation | Phase E |
| Phase D context assembly / hybrid scoring | Separate residual slice |
| `classify_relations` "none" no-row test | Omitted from landed plan Task 5 (design spec drift) |
| `capsule_segments.role` CHECK fix | Pre-existing on `main`; `TODO.md` Ongoing |
| Thesis idempotency guard (same `supporting_capsule_ids` set) | Described in early design draft but **not implemented** — CLI docstring explicitly states re-run is not idempotent; no test needed for unimplemented behaviour |
| `decision_artefacts` confidence validation | No `confidence` column on artefact rows |

---

## 10. Open Questions

| # | Question | Owner | Priority |
|---|---|---|---|
| OQ-1 | Should `dry_run` regression live in mocked unit test only, or is DB count assertion (RL-6) mandatory given the bug was DB-visible? | Backend | P0 |
| OQ-2 | Should `nexus artefacts create` wrap `uuid.UUID` parse failures in `typer.BadParameter` for consistent exit code 2? | Backend | P1 |
| OQ-3 | Is filtering `source_capsule_id == target_capsule_id` required to match design intent ("skip unary self-reference rows"), or is current `IS NOT NULL` filter sufficient given `min_cluster_size=2`? | Backend | P2 |
| OQ-4 | Should the design spec's `classify_relations` "none" no-row test be added to close spec/plan drift, or is the design spec stale? | Backend | P2 |
| OQ-5 | Should CLI help tests strip ANSI globally (fixing pre-existing `test_capsules_backfill_help_works` too) or use `CliRunner(color=False)` if supported? | Backend | P1 |