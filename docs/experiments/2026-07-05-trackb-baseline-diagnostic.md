# Track-B Baseline Diagnostic — Wall Sizing (2026-07-05)

**Goal:** size the three retrieval walls (B1/B2/B3) on the *current* full pipeline
before building any retrieval change — is the 0.90 gap a retrieval problem or an
answer-path problem?

**Result:** on the temporal-reasoning subset, the gap is **answer-path temporal
reasoning, not retrieval.** Wall 1 (un-retrieved evidence) is ~3 questions;
**18 of 21 failures are confident-wrong answers with evidence retrieved** — wrong
ordering / date arithmetic. This is precisely what the already-proven-but-
un-productionized Chain-of-Note prompt (H9a, +16 pts on temporal in replay) fixes.
Retrieval-breadth work (B1) has a ceiling of ~3 questions here.

## Method

Full pipeline, 55-instance subset (all temporal-reasoning), `conversation_v1`, 6
workers, `nexus_t1..t6`. **Current app answer prompt** (pre-CoN/lean — H9a not
productionized), so absolute accuracy reads low; the value here is the *failure
taxonomy*, which is answer-prompt-independent. Raw:
[`data/2026-07-05-trackb-baseline-results.jsonl`](data/2026-07-05-trackb-baseline-results.jsonl).

## Result

- Accuracy **0.618** (34/55). Abstention **7.3%** (4 qs; 3 graded wrong).
- **Wall 1 (evidence never retrieved → abstains): ~3 questions.** B1 (raise
  `fetch_k_multiplier`/`top_k_delta`) can recover at most these — its ceiling is
  ~5 pts on this subset, so it is **not** the lever.
- **18 confident-wrong** (evidence retrieved, model answered, wrong):

  | bucket | n | example |
  | --- | --- | --- |
  | ordering ("which of A/B came first") | 10 | "Which did I get first, S22 or Dell XPS?" → answered Dell (gold: S22) |
  | duration/counting arithmetic | 6 | "How many months ago booked Airbnb?" → 3 (gold: 5) |
  | recency / most-recent | 2 | "Which streaming service most recently?" → Apple TV+ (gold: Disney+) |

  Every hypothesis cites retrieved blocks (C1/C4) and reasons over dates — the
  evidence is present; the *temporal reasoning* is wrong.

## Conclusion

1. **The dominant temporal failure is wrong ordering/arithmetic over
   correctly-retrieved evidence** — an answer-path reasoning problem, not a
   retrieval-coverage problem. The three retrieval walls are secondary on this
   subset (Wall 1 ≈ 3 qs; Walls 2/3 as *retrieval* changes can't fix "model
   ordered two retrieved dates backwards").
2. **Chain-of-Note is the matched lever and it is already proven:** the H9
   answer-path experiment lifted temporal 0.647 → 0.812 (+16 pts) with the exact
   CoN instruction (resolve each block's absolute date, sort for ordering, compute
   deltas, enumerate for counting). It is un-productionized only because H9a was
   deferred.
3. **Recommendation — invert the H9b-before-H9a order:** productionize CoN + lean
   prompt (H9a) first; it is the highest-leverage accuracy lever for the 0.90
   story on this subset. Then re-measure and take the residual retrieval walls
   (B1 for the ~3 un-retrieved, B3 for genuine multi-comparand counting) on top of
   the lifted answer-path baseline.

This is the second experiment this session (after [E1](2026-07-05-pair-gate-characterization.md))
where measurement redirected away from a pre-assumed lever toward the one the data
actually supports.
