# LongMemEval — Answer-Path Optimization (2026-07-04)

**Goal:** push LongMemEval (oracle split, knowledge-update + temporal-reasoning,
n=211) from the H7 baseline (0.709) toward ≥0.90, **or** ≥0.80 with significant
token efficiency.

**Result:** answer-path-only changes reach **0.834 at 1487 tokens/question**
(from a 0.72 / 2346-token baseline) — **+11 pts accuracy AND −37% tokens**. The
≥0.80-with-efficiency target is met decisively. **≥0.90 is not reachable on the
answer path** (it plateaus at ~0.83); the residual is three retrieval-side walls,
documented below for the follow-up.

No app code changed in this experiment — findings are proven in the lab
(`scripts/benchmarks/replay_answer.py`); productionization is a separate step.

---

## Method — extract-once / replay-many

Each LongMemEval instance normally re-ingests and re-extracts its evidence
(~10 min/55-q, stochastic) before answering. Since the winning levers are all
**answer-path** (model, reasoning mode, block ordering, prompt shape), we froze
the expensive part:

1. `run_longmemeval.py --dump-context` serializes each question's retrieved
   `context_blocks` (+ `as_of`, `question_shape`) into `results.jsonl` — one
   34-min full run builds a reusable capsule cache (also a fresh baseline: 0.720).
2. `replay_answer.py` re-runs **only the answer LLM + judge** over that fixed
   cache under any variant. This isolates the answer path from extraction noise
   and skips ingestion entirely — the token-efficient way to search the design
   space. All variants below share one judge pass, so intra-table comparisons are
   clean; compare against the **replay baseline 0.692** (≈ the 0.720 full-run
   baseline minus judge-pass noise).

Cache: 211 instances, mean 10.1 blocks/instance (5–15). Token split on the
baseline answer call: **prompt 2234 / completion 389** — prompt (context) is
**85%** of the total, so efficiency lives in the prompt.

## Levers tested

- **Chain-of-Note (CoN):** add a `notes` field before `answer` in the response
  JSON; instruct the model to first list each block's resolved absolute date,
  sort for ordering, compute date deltas explicitly, enumerate for counting, and
  abstain on entity-mismatch distractors. In-band reasoning — cheaper than
  DashScope thinking mode (~+460 completion tok vs ~+1200).
- **Lean prompt:** drop per-block boilerplate the answer model ignores (Title,
  URL, Object type, Score, Epistemic note); keep label, Date, Role, capsule text,
  1 excerpt. Keeps **every** evidence block — only trims per-block fat.
- **Chronological ordering** of blocks; **thinking mode**; **T3 model**
  (qwen3.7-max vs qwen3.6-flash); **context trim** (drop low-score blocks).

## Results (replay harness, n=211, same judge)

| variant | accuracy | tokens | abst | temporal | know-update |
| --- | --- | --- | --- | --- | --- |
| baseline | 0.692 | 2346 | 28 | 0.647 | 0.769 |
| chrono | 0.716 | 2375 | 24 | 0.677 | 0.782 |
| **cot** | **0.829** | 2806 | 31 | 0.812 | 0.859 |
| cot_chrono | 0.791 | 2779 | 34 | 0.759 | 0.846 |
| think_chrono | 0.829 | 3520 | 20 | 0.805 | 0.872 |
| t3 | 0.810 | 2334 | 27 | 0.774 | 0.872 |
| t3_chrono | 0.825 | 2334 | 25 | 0.789 | 0.885 |
| t3_cot | 0.806 | 2676 | 37 | 0.789 | 0.833 |
| think_cot | 0.829 | 4181 | 29 | 0.797 | 0.885 |
| t3_think_cot | 0.791 | 3266 | 41 | 0.752 | 0.859 |
| leanprompt | 0.720 | 1512 | 21 | 0.722 | 0.718 |
| **cot_leanprompt** | **0.806** | **1919** | 33 | 0.797 | 0.821 |
| **t3_leanprompt** | **0.834** | **1487** | 26 | 0.805 | 0.885 |
| cot_chrono_lean6 (drop blocks) | 0.668 | 1961 | 62 | 0.594 | 0.795 |

Raw: [`data/2026-07-04-sweep{1,2,3}.json`](data/).

## Conclusions

1. **Chain-of-Note is the biggest single lever:** +14 pts (0.692→0.829) for ~+460
   tokens. Matches the literature (chain-of-note + structured JSON, ~+10 pts).
2. **Lean prompt is free efficiency:** −36% tokens at zero accuracy loss
   (0.692→0.720). Keeps all evidence — the version that *dropped* blocks
   (`lean6`) cratered to 0.668 with 62 abstentions.
3. **Chronological reordering hurts** once reasoning is on (cot 0.829 →
   cot_chrono 0.791). Rejected.
4. **Levers don't stack:** T3 + thinking + CoN (0.791) is *worse* than CoN alone.
   When more reasoning lowers accuracy, the bottleneck is no longer reasoning.
5. **Two 80%+ operating points** (pending model-cost decision):
   - `cot_leanprompt` — 0.806 / 1919 tok on the **fast** flash model
     (−18% tokens AND −18% real $ vs baseline; same model).
   - `t3_leanprompt` — 0.834 / 1487 tok on qwen3.7-max (best accuracy, −37%
     token count, but ~10× $/token so higher real $). NB: the repo's cost model
     is flat `0.14/M`, under which t3_leanprompt is strictly cheapest.

## The 0.90 cap — three walls (follow-up scope)

Taxonomy of the best variant's (`cot`, 0.829) 36 residual failures, tagged by
whether gold-answer evidence was even retrieved (`cov`). All three need
**retrieval-side** work + full re-runs (the replay cache is a frozen retrieval
snapshot and cannot test them):

- **Wall 1 — evidence never retrieved (`cov≈0`).** E.g. *"current highest score in
  Ticket to Ride"* → gold 132 absent from context; model correctly abstains. A
  top-k / ranking problem.
- **Wall 2 — supersession-direction (`cov=1.0`, wrong).** Questions asking for the
  *superseded* value ("where did I **initially** keep…", "**previous** best time")
  while the pipeline (and the CoN prompt) prefers the *current* fact. Needs an
  "initial/previous/original" path that flips the preference — and fights the
  ranking that already down-weighted the old capsule.
- **Wall 3 — ordering & counting (`cov=1.0`, wrong).** All comparanda retrieved but
  mis-ranked or under-counted ("how many X before Y" off by one — the qualifying
  event sits outside top-k). This is the sub-query-union / per-sub-query-slot
  retrieval problem (reverted in H7).

Arithmetic: 0.834 is ~35 questions short of 0.90; ≈⅓ Wall 1 (pure retrieval), ⅓
Walls 2–3 (retrieval + prompt together), ⅓ judge-boundary noise ("7 days; 8 also
acceptable"). Closing to 0.90 is a retrieval-and-ranking project, not a prompt
project.

## Reproduce

```
# 1. build the capsule cache (also a fresh baseline)
python -m scripts.benchmarks.run_longmemeval --limit 0 --k 5 --pack conversation_v1 \
  --workers 6 --db-url-template 'postgresql+asyncpg://nexus:nexus@localhost:5432/nexus_lme_w{n}' \
  --dump-context --out <cache-dir>

# 2. replay answer-path variants over the fixed cache
DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5432/nexus_lme \
python -m scripts.benchmarks.replay_answer --cache <cache-dir>/results.jsonl \
  --variants baseline cot leanprompt cot_leanprompt t3_leanprompt --out <out-dir>
```
