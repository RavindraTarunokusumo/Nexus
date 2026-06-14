# Phase D Residual — Declarative Context Assembly + Evidence-Path UI

**Date:** 2026-06-14
**Branch:** `claude/phase-d-residual` (worktree `.claude/worktrees/phase-d-residual`, off merged `main` `48a4b09`)

> Brainstorm decisions were made autonomously using the recommended option for each open
> question, per explicit user delegation ("approve all recommended approach and proceed until
> finished").

## Goal

Close the two buildable-now residual items from Phase D:

- **A — Token-budget context assembly:** consume `pack.context_assembly.max_tokens_by_tier["T2"]`
  as a real token budget in chat retrieval, instead of the current flat `top_k` slice.
- **B — Evidence-path UI:** surface each citation's capsule→span evidence chain through the
  chat API and render it in the web `CitationList`.

## Scope

In scope: items A and B as defined below.

Explicitly **out of scope** (Phase-E-gated, with rationale):

- Richer `context_assembly.include` categories (`counter_evidence_and_caveats`,
  `superseding_or_superseded_objects`, `epistemic_notes`) and `ordering: evidence_strength` —
  these require the relation graph, lifecycle transitions, and `evidence_quality` signals, all
  of which are stubbed until Phase E.
- Un-stubbing `source_authority` / `relation_relevance` / `evidence_quality` scoring inputs.
- Dropping `claims` / `claim_evidence` tables (gated on 1 week of green production cutover).

## Item A — Token-budget context assembly

**Where:** `app/intelligence/chat.py`, `_run_retrieve_capsules`.

Current behavior selects `top = scored[:top_k]` after sorting candidates by hybrid score
(descending). This replaces that slice with a budget-aware greedy assembly.

**Pure helpers (unit-testable, no DB):**

- `estimate_tokens(text: str) -> int` — char heuristic: `ceil(len(text) / 4)`. Zero
  dependency; adequate for a soft budget gate. (The chat answer runs on the T2 deepseek model,
  for which no exact local tokenizer exists, so a precise tokenizer would be illusory accuracy.)
- `_assemble_within_budget(scored, top_k, token_budget) -> list[tuple[candidate, score]]`:
  - `scored` is the score-sorted `[(candidate, score), ...]` list.
  - If `token_budget is None` → return `scored[:top_k]` (current flat behavior; back-compat for
    packs without the field).
  - Otherwise iterate in score order, accumulating `estimate_tokens(candidate["text"])`. Include
    a block while `count < top_k` **and** `running_total + est <= token_budget`. **Always include
    at least the first (highest-scored) block**, even if it alone exceeds the budget — better to
    answer from the single most relevant capsule than to return nothing.

**Budget source:** `pack.context_assembly.max_tokens_by_tier.get("T2")`. The chat tier is T2.
When `pack is None` or the key is absent, `token_budget` is `None` → flat `top_k`.

**Note:** the budget governs only the capsule text sent to the LLM prompt (`build_user_prompt`
uses block text). Item B's evidence excerpts are UI-only and are NOT counted against the budget.

## Item B — Evidence-path UI

**Backend (`app/intelligence/chat.py`):**

- New `CitationEvidence(BaseModel)`: `span_id: uuid.UUID`, `span_index: int`, `text: str`.
- `ChatCitation` gains `evidence: list[CitationEvidence] = []`.
- After the assembled `top` blocks are chosen in `_run_retrieve_capsules`, run one query joining
  `CapsuleSegment` → `Span` (`CapsuleSegment.segment_id == Span.id`) with
  `WHERE CapsuleSegment.capsule_id IN (<assembled capsule ids>)`, ordered by `capsule_id` then
  `Span.span_index`.
- A pure helper `_build_evidence_map(rows, max_spans, excerpt_chars) -> dict[uuid.UUID, list[dict]]`
  shapes the rows: per capsule, keep up to `_MAX_EVIDENCE_SPANS = 5` spans (in span_index order),
  each `text` truncated to `_EVIDENCE_EXCERPT_CHARS = 280` (with an ellipsis when truncated).
  Unit-testable without a DB.
- Attach `evidence` to each block dict; `format_result` copies `block["evidence"]` into the
  emitted `ChatCitation`.

**Frontend:**

- `web/src/api/client.ts`: `ChatCitation` type gains
  `evidence: { span_id: string; span_index: number; text: string }[]`.
- `web/src/components/CitationList.tsx`: inside the existing expanded panel, render an
  "Evidence" subsection — a list of span excerpts (`#<span_index>` + truncated text). When
  `evidence` is empty, omit the subsection entirely.

## Data Flow

```
classify_intent
  → retrieve_capsules:  HNSW search → hybrid score → _assemble_within_budget
                        → fetch + _build_evidence_map for assembled capsules
  → generate_answer
  → format_result:      emit ChatCitation (incl. evidence) for cited labels
  → /chat/answer JSON   → web CitationList (expandable evidence chain)
```

## Error Handling

- Missing `max_tokens_by_tier["T2"]` → `token_budget=None` → flat `top_k` (no error).
- Capsule with no `CapsuleSegment` rows → empty `evidence` list → UI omits the subsection.
- The evidence query shares retrieval's session/transaction; an existing DB failure already
  aborts retrieval, so no new error path is introduced.

## Testing

**A (pure unit, no DB):**

- `estimate_tokens` — basic char/4 rounding.
- `_assemble_within_budget` — (1) stops when budget exceeded; (2) respects `top_k` as a hard
  count cap even when budget allows more; (3) always includes the first block when it alone
  exceeds budget; (4) `token_budget=None` → flat `top_k` slice.

**B backend:**

- `_build_evidence_map` (pure) — groups by capsule, caps at `_MAX_EVIDENCE_SPANS`, truncates to
  `_EVIDENCE_EXCERPT_CHARS`, orders by span_index, empty input → empty map.
- `_run_retrieve_capsules` integration (mocked session with two `execute` results: candidate
  rows then segment/span rows) — assembled blocks carry shaped `evidence`.

**B frontend (Vitest):**

- `CitationList` renders evidence excerpts in the expanded panel when present.
- Omits the Evidence subsection when `evidence` is empty.

## Files

- `app/intelligence/chat.py` — A helpers + budget assembly; B `CitationEvidence`, evidence query,
  `_build_evidence_map`, `format_result` wiring.
- `web/src/api/client.ts`, `web/src/components/CitationList.tsx` — B frontend.
- `tests/intelligence/test_chat_scoring.py` (or new `test_chat_assembly.py`) — A.
- `tests/intelligence/test_chat_graph.py` — B backend (update existing retrieve tests for the
  second query).
- `web/src/test/components.test.tsx` — B frontend.
