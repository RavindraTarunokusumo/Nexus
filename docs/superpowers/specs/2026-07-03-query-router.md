# Spec: Qwen Memory Query Router (H5)

**Date:** 2026-07-03
**Status:** Accepted (hackathon fast-path; interactive acceptance skipped per standing instruction)
**TODO ref:** H5 — Implement a Qwen memory query router before the next benchmark pass.

## Problem

The chat pipeline runs one fixed retrieval/answer path for every question. The existing
`classify_intent` node (T2 Qwen) classifies into pack-defined domain intents, but the
intent only feeds `retrieval_priorities` — one input of seven in `compute_hybrid_score`.
Nothing about candidate breadth, score weighting, or answer instructions adapts to the
*shape* of the question. Benchmark evidence (`docs/benchmarks/baseline-2026-07-02.md`):

- `timeline` (single-fact date lookups) is the weakest category, 0.25–0.5 across runs —
  short factoid queries embed poorly and the fixed weights let salience/recency drown the
  one capsule that holds the fact.
- `superseded` sits at ~0.556 — the superseding fact is retrieved but the answer does not
  reliably prefer it.
- `authority_conflict` answers do not consistently distinguish primary evidence from rumor.

## Requirements

1. Classify each incoming question into a **question shape** using the same single T2 Qwen
   call that already classifies domain intent (no added LLM round-trip, no added latency).
2. Dispatch a per-shape **retrieval strategy**: hybrid-score weight overrides, candidate
   fetch breadth, and effective top_k.
3. Dispatch a per-shape **answer hint** appended to the answer prompt.
4. Fallback to current behavior (`general` shape, no overrides) on any classification
   failure — the router must never make an answer path worse than today's fixed path.
5. Shapes are domain-neutral (they describe question form, not domain content) and live in
   code, not the domain pack. Pack `query_intents` remain the domain-content axis;
   the two compose (intent → retrieval_priorities, shape → strategy).

## Question-shape taxonomy

| Shape | Trigger | Strategy intent |
|---|---|---|
| `factoid` | Single-fact lookup: a date, number, name, score ("When did X GA?") | Semantic-similarity-dominant weights; widen fetch pool; answer states the specific value |
| `multi_doc` | Aggregation/comparison across sources ("How did pricing change between Nov and Feb?") | Larger effective top_k; answer synthesizes across all blocks, cites each |
| `current_state` | Present-tense state query ("What is the price *today*?") | Boost recency weight; answer prefers superseding fact and names what it replaced |
| `conflict` | Verification / disputed claims ("Did X train on Y?", "Is there verified evidence…") | Boost source_authority + evidence_quality weights; answer separates verified primary evidence from rumor |
| `general` | Everything else | No overrides — identical to current behavior |

## Data model

New module `app/intelligence/router.py`:

```python
# Amended post-/simplify: frozen dataclass (repo precedent: projection.py), and
# QUESTION_SHAPES is derived as tuple(STRATEGIES) so the registry is the single
# source of truth (prompt enumeration, validation, resolution all read from it).
class RetrievalStrategy:  # @dataclass(frozen=True)
    weight_overrides: dict[str, float] = {}   # merged over pack hybrid_score_weights
    fetch_k_multiplier: int = 3               # fetch_k = top_k * multiplier (today: 3)
    top_k_delta: int = 0                      # effective top_k = state top_k + delta
    answer_hint: str = ""                     # appended to the answer user prompt

QUESTION_SHAPES: tuple[str, ...]              # the 5 shapes above
STRATEGIES: dict[str, RetrievalStrategy]      # per-shape table; "general" is empty defaults
def resolve_strategy(shape: str) -> RetrievalStrategy   # unknown shape -> general
```

Strategy values (initial; tuned by benchmark, not sacred):

- `factoid`: weights `{semantic_similarity: 0.6, salience: 0.05, recency: 0.05}`,
  `fetch_k_multiplier: 6`, hint "State the specific date, number, or value asked for,
  taken verbatim from the evidence."
- `multi_doc`: `top_k_delta: +3`, `fetch_k_multiplier: 4`, hint "Synthesize across all
  relevant context blocks and cite every block you draw from."
- `current_state`: weights `{recency: 0.25}`, hint "Prefer the most recent superseding
  fact; explicitly note the fact it replaced."
- `conflict`: weights `{source_authority: 0.25, evidence_quality: 0.25}`, hint
  "Distinguish verified primary-source evidence from rumor or unverified reports; state
  the authority of your sources."
- `general`: all defaults.

Weight overrides are a **merge** (`dict.update`) over the pack's
`hybrid_score_weights`, not a replacement — pack keys not named in the override survive.

## Interfaces / touched surfaces

1. `app/intelligence/prompts/classify_intent.py` — `IntentClassification` gains
   `shape: str = "general"`; `SYSTEM_PROMPT`/`build_classify_prompt` list the shapes with
   one-line definitions and require both keys in the JSON.
2. `app/intelligence/chat.py`:
   - `ChatState` gains `question_shape: str`.
   - `_run_classify_intent` returns `{"query_intent": ..., "question_shape": ...}`;
     invalid/unknown shape or `LLMError` → `"general"`.
   - `_run_retrieve_capsules` resolves the strategy and applies
     `weights.update(strategy.weight_overrides)`,
     `fetch_k = effective_top_k * strategy.fetch_k_multiplier`,
     `effective_top_k = state["top_k"] + strategy.top_k_delta` (floor 1).
   - `generate_answer` passes `strategy.answer_hint` into `build_user_prompt`.
   - `run_chat_with_context` seeds `question_shape: "general"` in the initial state.
3. `app/intelligence/prompts/chat_answer.py` — `build_user_prompt` gains
   `hint: str = ""`; non-empty hint renders as a final `Answer guidance: {hint}` line.

No DB schema changes. No API contract changes (`ChatCitation`/response shape untouched;
`question_shape` may be surfaced in the result dict for observability but is additive).

## Workflows

```
question → classify_intent (ONE T2 Qwen call → intent + shape)
         → retrieve_capsules (pack weights ∘ shape overrides; shape-scaled fetch_k/top_k)
         → generate_answer (prompt + shape answer_hint)
         → format_result (unchanged)
```

## Edge cases

- LLM error or malformed shape → `general` (requirement 4).
- Pack with no `query_intents` → intent path short-circuits as today, but shape
  classification still runs (the shapes don't depend on the pack).
  — Correction: today the node returns early before the LLM call when the pack has no
  intents. Keep the single-call design: when there are no intents, still make the call
  with an empty intent list and accept only the shape. Simpler alternative if the prompt
  degrades: classify shape-only in that branch. Implementer's choice; behavior contract is
  "shape is always classified unless the LLM errors."
- `top_k_delta` pushing effective top_k below 1 → floor at 1.
- `pack is None` (degenerate direct-invocation path; `run_chat_with_context` and the API
  always load a pack) → intentional exception to "shape is always classified": classify
  short-circuits to `general` with no LLM call, and retrieval skips weight overrides
  (merging onto empty base weights would score on the overridden components alone).
  Fetch/top_k scaling and hints still apply.
- `general` strategy must be behaviorally identical to pre-router code (regression guard).

## Success criteria

1. Full validation suite green (no new failures vs. the 6 pre-existing).
2. Unit tests: strategy resolution (known/unknown shapes), classify-node shape fallback,
   weight-merge semantics, prompt hint rendering, top_k floor.
3. Live benchmark rerun (`nexus eval memory run --benchmark nexus_synthetic --k 5`) on a
   scratch DB: `timeline` category improves over 0.25–0.5 baseline; `citation_faithfulness`
   stays 1.000; `forbidden_violation` stays 0.000; `abstention_accuracy` does not regress
   below 0.7.

## Constraints

- One LLM call for classification (shared with intent) — no added per-question latency.
- Router model = T2 Qwen (`state["model"]`), consistent with the Qwen-native submission story.
- Strategy table in code (`router.py`), not the pack — shapes are domain-form, not
  domain-content. Pack-level override is explicitly out of scope for H5.
