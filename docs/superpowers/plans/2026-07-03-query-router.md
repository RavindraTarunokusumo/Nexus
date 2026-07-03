# Plan: Qwen Memory Query Router (H5)

**Spec:** `docs/superpowers/specs/2026-07-03-query-router.md`
**Branch:** `claude/router-h5` (worktree `.worktree/router-h5`)

Single-surface change; one implementation task, sequential. Orchestrator runs the live
benchmark validation itself (needs real Qwen credentials + scratch DB — not delegated).

## File structure

- `app/intelligence/router.py` — NEW. `RetrievalStrategy`, `QUESTION_SHAPES`,
  `STRATEGIES`, `resolve_strategy`.
- `app/intelligence/prompts/classify_intent.py` — extend model + prompts for shape.
- `app/intelligence/chat.py` — thread `question_shape` through state, retrieval, answer.
- `app/intelligence/prompts/chat_answer.py` — `build_user_prompt(..., hint="")`.
- `tests/intelligence/test_router.py` — NEW. Strategy-table unit tests.
- `tests/intelligence/test_chat_graph.py` — extend for shape fallback + hint threading.

## Task decomposition

### T-R1 — Router module + wiring (one task, one commit)

**Consumes:**
- `pack.retrieval_policy.hybrid_score_weights: dict[str, float]` (merge target)
- `ChatState` (TypedDict, `app/intelligence/chat.py:52`)
- `client.complete_json(model, system, user, response_model, run_type)` — existing call in
  `_run_classify_intent`
- `build_user_prompt(question, context_blocks)` — existing signature to extend

**Produces:**
- `resolve_strategy(shape: str) -> RetrievalStrategy` (unknown → `STRATEGIES["general"]`)
- `IntentClassification(intent: str, shape: str = "general")`
- `_run_classify_intent` → `{"query_intent": str, "question_shape": str}` — shape
  validated against `QUESTION_SHAPES`, `LLMError` → both fall back (`general`)
- `_run_retrieve_capsules` — applies `weight_overrides` merge, `fetch_k =
  max(1, top_k + top_k_delta) * fetch_k_multiplier`, effective top_k floor 1
- `generate_answer` — passes `resolve_strategy(state.get("question_shape",
  "general")).answer_hint` as `hint=` to `build_user_prompt`
- `run_chat_with_context` — seeds `"question_shape": "general"`

**Boundaries:** no git operations; no DB schema changes; no changes to
`ChatCitation`/API response models; no pack YAML edits. Self-check: full `ruff check`,
`ruff format --check`, `mypy app/`, `pytest` (6 pre-existing failures in
`test_extraction_graph.py`/`test_capsules_dual_write.py` are known — no new failures).
Single trailing newline on every file.

### T-R2 — Live benchmark validation (orchestrator, not delegated)

Fresh scratch DB (`nexus_router`), `alembic upgrade head`, then
`nexus eval memory run --benchmark nexus_synthetic --k 5`. Gate on spec success
criteria 3. Tune `STRATEGIES` values in a follow-up commit if a category regresses.

## Build order

T-R1 → orchestrator full-suite gate → commit + git note → T-R2 → (optional tuning
commit) → Submit PR flow.

## Risks

- **Prompt regression in the shared classify call** — adding shape to the intent prompt
  could degrade intent accuracy. Mitigation: keep the prompt additive (intent instructions
  unchanged, shape appended); fallback path covers failures.
- **factoid weight override overfits the synthetic benchmark** — values are declared
  "tuned by benchmark, not sacred" in the spec; T-R2 is the check.
- **`general` behavior drift** — regression-guarded by requiring the `general` strategy to
  be all-defaults and by existing `test_chat_graph.py` tests passing unmodified except
  where state gains the new key.
