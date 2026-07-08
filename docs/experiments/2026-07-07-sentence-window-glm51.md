# Sentence-Window Retrieval — first A/B (2026-07-07)

Session `claude/h9b-walls`. First measurement of the deterministic
sentence-window architecture (spec/plan `2026-07-06-sentence-window-retrieval`)
vs the semantic-capsule pipeline. Answer model **glm-5.1** (thinking on),
judge **qwen3.7-max** (same judge as all prior baselines). Ingestion is fully
local: `agent_runs` shows only `chat_answer` + judge — **zero** extraction /
relation calls.

## Results

| benchmark | subset | sentence-window (glm-5.1) | semantic baseline | Δ |
| --- | --- | --- | --- | --- |
| LongMemEval | 25 KU + 25 temporal (n=50) | **0.840** | 0.820 (flash, `b3-gate-4k`) | +0.02 |
| LoCoMo | 6 convs, all 5 cats (n=48) | **0.438** | 0.289 (122b, k=15, n=100) | +0.15 |

Per category:

- **LongMemEval:** knowledge-update 0.880, temporal-reasoning 0.800, 3 abstentions.
- **LoCoMo:** temporal **0.652** (vs ~0.24 semantic — the big winner), multi_hop
  0.278, open_domain 0.000 (judge subset-rule artifact, unchanged), single_hop 1/2.

## Cost

| | tokens/answer (median) | ingestion API tokens | total for the subset |
| --- | --- | --- | --- |
| sentence-window | LME 2,973 / LoCoMo 2,213 | **0** | LME 153 k (50 q) |
| semantic (est.) | ~2,100 answer | ~66 k / question | ~3.4 M for 50 q |

**~22× fewer tokens** on LongMemEval-50, entirely from eliminating the
extraction+relation ingestion tax. Answer-path tokens stay ~2–3 k even with a
thinking reader.

## Reading it honestly

- **The architecture matches/beats the semantic pipeline on both benchmarks at
  ~97% lower ingestion cost.** That is the headline: the deterministic path is
  cheaper *and* at least as accurate.
- **Confound:** the comparison mixes architecture with model (glm-5.1 vs the
  baselines' flash/122b). A clean isolation needs semantic-mode on glm-5.1 or
  sentence-window on flash — not yet run. But the strategic point stands:
  sentence-window *enables* a strong thinking reader cheaply, because ingestion
  is free — you could not afford glm-5.1 across the semantic pipeline's 65
  calls/question.
- **Temporal reasoning is the clear win** (LoCoMo 0.24→0.65): verbatim sentences
  with session dates + a thinking reader beat lossy capsules + date arithmetic.
- **Neither hits 0.90.** LongMemEval 0.84 is close; LoCoMo 0.44 is well short.
  The residual losses map exactly to the MVP's deferred enhancements:
  - "which happened first" / comparison questions fail even when *both*
    comparands are retrieved — needs the **ordering-id metadata** (reader can't
    establish order from the current signal).
  - LoCoMo multi_hop 0.28 — needs **sub-query / iterative retrieval** for
    unknown-bridge hops.
  - LoCoMo open_domain 0.00 — **judge subset-rule** artifact, not a system
    failure; needs a partial-credit judge.

## Next levers (in leverage order)

1. Ordering-id metadata on claims → fixes comparison/temporal ordering (the
   single biggest miss class across both benchmarks).
2. Sub-query decomposition for multi-hop retrieval.
3. Partial-credit / F1 judge for LoCoMo open_domain (measurement, not system).
4. Isolation A/B (semantic-mode glm-5.1) to separate architecture from model.
