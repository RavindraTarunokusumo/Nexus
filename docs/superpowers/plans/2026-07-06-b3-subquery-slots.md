# Plan: B3 — Per-Sub-Query Retrieval Slots

**Date:** 2026-07-06
**Session:** `claude/h9b-walls`
**Spec:** [`2026-07-05-ingestion-retrieval-opt-h8h9.md`](../specs/2026-07-05-ingestion-retrieval-opt-h8h9.md) §B3; design history in [`2026-07-03-longmemeval-adapter.md`](../specs/2026-07-03-longmemeval-adapter.md) Amendment 2 R2.
**Goal:** ordering/comparison/counting questions (Wall 3, 6/37 taxonomy failures) stop losing one comparand outside top-k. This is the **corrected R2**: the reverted pool-then-global-rerank (`bc8fe83`, reverted `ec1962a`) regressed because one sub-query's candidates crowd out the other's; the fix is a guaranteed per-sub-query floor before any shared rerank. Consult `git show bc8fe83` for the classifier/state plumbing to restore — the merge policy is the only part that changes.

## Task 1 — classifier emits sub-queries (restore from bc8fe83)

**File scope:** `app/intelligence/prompts/classify_intent.py`, the intent-output model + graph state it flows through (trace from `bc8fe83`), tests.

**Interfaces:**
- Classify output gains `sub_queries: list[str]` (max 3, default `[]`): for questions that compare, order, or count across ≥2 distinct entities/events, one short retrieval query per entity/event; empty for single-target questions. Prompt wording may be taken from `bc8fe83` as-is.
- State carries `sub_queries` to retrieval unchanged.

## Task 2 — slotted retrieval merge

**File scope:** `app/intelligence/chat.py::_run_retrieve_capsules` (impact: LOW, single caller `retrieve_capsules`), `app/config.py`, tests.

**Interfaces:**
- Config: `settings.retrieval_subquery_slots: bool = False` (default off until the A/B gate passes; flipped by env for the benchmark arm).
- `_run_retrieve_capsules`: when the flag is on and `len(sub_queries) >= 2`:
  - Embed the full question plus each sub-query; ANN-fetch `fetch_k` candidates per vector; score every candidate with the existing `compute_hybrid_score` against its own vector's similarity; dedup by capsule id keeping the best score.
  - **Slot allocation:** `floor = ceil(effective_top_k / (1 + len(sub_queries)))`. Each vector (full question counts as one) gets its top-`floor` capsules guaranteed; a capsule already claimed counts toward the vector that claimed it first and is skipped by later vectors (no double fill). Remaining `effective_top_k − claimed` slots top up by global best score.
  - Feed `_assemble_within_budget` the slotted picks **first** (in slot order), then the top-up tail, so the floor survives the token budget; aux-evidence discovery (`_discover_counter_evidence_ids` / `_discover_supersession_links`) stays untouched.
  - Flag off or `sub_queries < 2` → exactly today's single-vector path (byte-identical behavior; existing tests must pass unmodified).
- Extract the slot-merge as a pure function (candidate lists in → ordered capsule ids out) so the starvation property is unit-testable without a DB.

**Tests:** slot-merge unit tests — starvation case (one vector with uniformly higher scores cannot evict another's floor), dedup-across-vectors, remainder top-up by global score, `sub_queries=[]` no-op; classifier sub_queries emission (adapt `bc8fe83` tests); flag-off regression (existing retrieval tests untouched).

## Build order

Task 1 → Task 2 (state plumbing must exist before retrieval reads it). Single Grok handoff — the tasks share `bc8fe83` context and the state interface.

## Risks

- Re-introducing the R2 regression: mitigated by the floor (the reverted design's exact failure) and by the A/B gate below.
- Slot floor displacing good global candidates on questions mis-classified as multi-entity: bounded — the classifier emits `sub_queries` only for compare/order/count shapes, and floor ≤ half of `effective_top_k` at 1 sub-query… verify `ceil` math at len=2/3.
- Token budget silently dropping slotted picks: covered by feeding slot picks first into `_assemble_within_budget`.

## Validation gate

Full suite + `ruff check` + `ruff format --check` + `mypy app/` (orchestrator re-runs independently). Benchmark A/B, port 5432 workers:
- n=50 mixed gate (`--per-category-limit 25`) flag-off vs flag-on;
- targeted wall-3 run: `--question-ids gpt4_a1b77f9c,gpt4_7abb270c,gpt4_2312f94c,gpt4_7de946e7,gpt4_c27434e8,gpt4_f420262c` both arms.
Pass = wall-3 up, gate not down beyond noise → flip `retrieval_subquery_slots` default to `True` in a separate commit.
