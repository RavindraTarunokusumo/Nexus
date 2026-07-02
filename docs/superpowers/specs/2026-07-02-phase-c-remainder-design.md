# Phase C Remainder — Thesis Writer, Decision Artefact Writer, DB Integration Tests

**Date:** 2026-07-02
**Status:** Approved (Ravindra, in-session)

## Context

Phase C (PR #20) shipped `judge_capsules` and `classify_relations` as extraction-graph
nodes writing `semantic_relations` rows. Three items were explicitly deferred
(`docs/iterations/archive/2026-06-12-phase-c-reasoning-layer.md`, "What Phase C Did Not
Do"):

- **C3** — Thesis layer: first `theses` writer.
- **C4** — Decision artefacts: first `decision_artefacts` writer.
- DB-bound integration tests for `judge_capsules` / `classify_relations` (existing
  coverage is unit-only, LLM+DB mocked).

This is the first PR slice of the Telos/v0.7 residuals. Phase D residuals (context
assembly `include`/`ordering`, un-stubbing hybrid scoring, dropping legacy
`claims`/`claim_evidence`) and Phase E (lifecycle worker, consolidation worker,
stale/superseded detection) are explicitly out of scope and logged in `TODO.md` as
remaining slices.

## Key finding that shaped the design

Migration `0005_semantic_capsules.py` comments the `theses` table as **"higher-order
interpretation; written first by Phase E"**, and both `_THESIS_TIERS` and
`_DECISION_TIERS` CHECK vocabularies are `("t2", "t3", "t4")` — no `t0`/`t1`/`backfill`.
This is the schema author's own recorded intent: both tables are meant to be populated
by a later consolidation/lifecycle process, not by an automatic per-document extraction
node. `docs/database.md` independently corroborates this for `decision_artefacts`
("Not yet populated by the pipeline (Phase E+)").

**Decision:** both C3 and C4 ship as standalone writer functions + CLI commands this PR,
with no automatic trigger wired into the extraction graph or `/chat/answer`. Phase E's
lifecycle/consolidation worker owns deciding *when* theses/artefacts get created
automatically. This avoids building per-document clustering logic that Phase E would
likely replace, and keeps the PR slice narrow.

## Components

### 1. `app/intelligence/theses.py` — thesis writer

Mirrors `app/intelligence/capsules.py`'s `build_capsule_row` pattern.

- `build_thesis_row(*, thesis_id, domain, thesis_type, statement, supporting_capsule_ids,
  contradicting_capsule_ids, confidence, created_by_tier, title=None) -> Thesis`
  — pure row construction, no I/O. `created_by_tier` must be one of `t2`/`t3`/`t4`
  (validated at the call site, matching the CHECK constraint).
- `synthesize_theses_from_relations(session, *, domain, min_strength=0.6,
  min_cluster_size=2) -> list[Thesis]` — orchestration:
  1. Query `semantic_relations` rows where both `source_capsule_id` and
     `target_capsule_id` are set (binary relations only — skip judge_capsules' unary
     self-reference rows), `strength >= min_strength`, joined to `semantic_capsules`
     filtered by `domain`.
  2. Union-find over capsule ids using these edges to find connected components.
  3. For each component with `len >= min_cluster_size`: split member capsules into
     `supporting_capsule_ids` (reached via edges with `polarity != 'negative'` and
     `relation_type != 'contradicts'`) and `contradicting_capsule_ids` (the rest).
  4. `thesis_type` = the shared `object_family` of the component's capsules (capsules
     are only clustered within a single object_family already, since `classify_relations`
     only pairs same-family capsules — this is a re-statement of an existing invariant,
     not new logic).
  5. `statement` = the `text` of the capsule with highest `salience` in the component
     (no new LLM call — keeps this a T2-tier-labeled but LLM-free rule-based writer,
     consistent with "first writer", not a synthesis engine).
  6. `confidence` = mean of the component's edge `confidence` values.
  7. Skip a component if a `Thesis` already exists with the same `domain` +
     `thesis_type` + identical `supporting_capsule_ids` set (idempotent re-run guard —
     simple set-equality check via a pre-query, no new unique index needed for a
     first writer).

### 2. `app/cli/theses.py` — `nexus theses synthesize`

Mirrors `app/cli/capsules.py::backfill`. Options: `--domain` (required — pack id),
`--min-strength` (default 0.6), `--dry-run`, `--json`. Calls
`synthesize_theses_from_relations`, reports clusters found / theses written.

### 3. `app/intelligence/decision_artefacts.py` — decision artefact writer

- `build_decision_artefact_row(*, artefact_id, artefact_type, domain, question, answer,
  linked_thesis_ids, linked_capsule_ids, source_refs, created_by_tier) -> DecisionArtefact`
  — pure row construction. `artefact_type` has no CHECK constraint in the schema (free
  text); this PR only emits `"memo"`. `created_by_tier` validated against `t2`/`t3`/`t4`.

### 4. `app/cli/artefacts.py` — `nexus artefacts create`

Manual creation only (no batch/backfill mode — there's no existing corpus to backfill
from, unlike capsules). Options: `--domain`, `--question`, `--answer`,
`--capsule-id` (repeatable), `--thesis-id` (repeatable, optional), `--json`. Writes one
`memo` artefact.

### 5. DB-bound integration tests

`tests/intelligence/test_reasoning_layer_db.py`, `@pytest.mark.slow`, real Postgres
(via the existing `run_migrations` session fixture — same pattern as
`test_validation_harness.py`). LLM client is mocked (deterministic `JudgeVerdict` /
`RelationClassification` responses); DB is real. Covers:

- `judge_capsules`: flagged capsule → real `SemanticRelation` row lands with correct
  XOR self-reference, `escalation_state` transition persists.
- `classify_relations`: two same-family capsules → real binary `SemanticRelation` row
  lands with correct FK values; "none" classification writes no row (real DB round
  trip, not a mock assertion).
- Round-trip: `synthesize_theses_from_relations` against relation rows written by the
  above, confirming the full C1→C2→C3 pipeline is DB-consistent end to end.

## Error handling

- `build_thesis_row`/`build_decision_artefact_row` raise `ValueError` on an invalid
  `created_by_tier` (caught at the CLI layer, reported via `typer.Exit(code=1)`) —
  same shape as existing `_require_db_url` validation in `app/cli/capsules.py`.
- `synthesize_theses_from_relations` with zero qualifying relations returns `[]`, not
  an error — matches `classify_relations`' "gracefully do nothing" behavior when there
  isn't enough data.

## Testing

- Unit tests (no DB) for `build_thesis_row`, `build_decision_artefact_row`, and the
  union-find clustering helper in isolation (`tests/intelligence/test_theses.py`,
  `tests/intelligence/test_decision_artefacts.py`).
- New DB-bound integration suite as described above.
- CLI smoke tests (`--help`) appended to `tests/test_cli_e2e.py`, matching the existing
  `capsules backfill --help` pattern.

## Out of scope (logged in TODO.md)

- Any automatic trigger for thesis/artefact creation (Phase E).
- Cross-document clustering (Phase E consolidation worker).
- Phase D residuals (context assembly, hybrid scoring, legacy claims cutover).
