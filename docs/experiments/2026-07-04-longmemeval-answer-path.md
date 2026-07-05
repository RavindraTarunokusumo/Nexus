# LongMemEval — Answer-Path Optimization (2026-07-04)

**Goal:** push LongMemEval (oracle split, knowledge-update + temporal-reasoning,
n=211) from the H7 baseline (0.709) toward ≥0.90, **or** ≥0.80 with significant
token efficiency.

**Result:** answer-path-only changes reach **0.834 accuracy** (from a 0.72
baseline) at **1487 answer-call tokens** (from 2346) — **+11 pts accuracy AND
−37% answer-call tokens**. Accuracy clears 0.80 decisively. **Caveat on
"efficiency":** the answer call is only **~3.4% of the end-to-end per-question
token budget** (~69k tok/q; extraction + relation-classification are ~96%), so
the −37% is ~1.3% end-to-end — real but small. The genuine token lever is the
ingestion stage (see [Token accounting](#token-accounting--scope-and-the-real-lever-important)).
**≥0.90 is not reachable on the answer path** (it plateaus at ~0.83); the residual
is three retrieval-side walls, documented below for the follow-up.

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

## Token accounting — scope, and the real lever (important)

**Every token figure in this report is the `chat_answer` generation call only** —
the answer LLM given the context blocks. That is what the runner's
`mean_tokens_used` measures, and it is a **mean per question**. It excludes the
eval judge and, crucially, the **ingestion pipeline** (extraction, relation
classification), which is where the tokens actually are.

End-to-end per-question cost, measured from `agent_runs` across the six worker
DBs over the cache-build window (÷211):

| stage | calls/q | tokens/q | % of total |
| --- | --- | --- | --- |
| claim_extraction | 10.6 | 39,469 | 56.9% |
| classify_relation | 51.7 | 26,884 | 38.8% |
| **chat_answer** *(this report's number)* | 1.0 | **2,380** | **3.4%** |
| chat_classify_intent | 1.0 | 249 | 0.4% |
| longmemeval_judge *(eval-only)* | 1.0 | 368 | 0.5% |
| **TOTAL** | 65.3 | **≈69,366** | 100% |

So the −37% answer-path saving (2380→1487) trims ~0.9k off a **~69k** budget —
**~1.3% end-to-end**. The answer-path efficiency win is real but small in
absolute terms; the accuracy win (+11–14 pts) is the headline there. **The real
token lever for this benchmark is the ingestion stage** — extraction (39.5k) +
relation classification (26.9k) are ~96% of tokens, driven by 10.6 extraction
calls and **51.7 relation-classify calls per question** (cross-doc pairing). That
is outside this experiment's answer-path scope but is the obvious next target
(logged as H9c).

**Caveat — the 69k is a benchmark artifact.** Each LongMemEval instance ingests a
*fresh* corpus to ask *one* question, so the whole one-time ingestion cost is
charged to a single query. In real memory usage you ingest once and answer many
queries, so per-query cost amortizes toward the ~2.4k answer call. Whether
ingestion optimization (H9c) or answer-path efficiency matters more therefore
depends on the write-heavy (benchmark-like) vs read-heavy (production) mix — but
since ingestion is 96% of tokens whenever writes happen, it is still the first
place to cut.

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
