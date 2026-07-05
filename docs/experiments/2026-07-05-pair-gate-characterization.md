# E1 — Pre-LLM Pair-Gate Characterization (2026-07-05)

**Goal:** size the H9c "pre-LLM candidate-pair gate" (A1 in the
[optimization spec](../superpowers/specs/2026-07-05-ingestion-retrieval-opt-h8h9.md))
before building it — at what embedding-cosine floor can we skip the ~56% of
relation-classify calls that return "none" without dropping real relations?

**Result:** the cosine gate is **much weaker than the H9c estimate.** At ≥95%
relation recall the floor skips only **~14%** of calls (not the projected
50–70%). Cheap cosine similarity does **not** cleanly separate real relations
from non-relations. **Plan change:** demote A1 to an optional low-value gate;
promote **A2 (batching)** and **A3 (prefix caching)** — which cut tokens
regardless of the pair distribution — to the primary token levers.

## Method

Env-gated trace hook (`NEXUS_PAIR_TRACE`, throwaway, reverted after this run)
recorded every candidate capsule pair reaching the relation classifier during a
15-instance LongMemEval run (`conversation_v1`, knowledge-update +
temporal-reasoning, fresh `nexus_e1` DB): `{cap_a, cap_b, object_family match,
embedding cosine, verdict, strength, source}`. Positive = classifier returned a
real relation; negative = "none". Small per-instance corpora stay under
`max_pairs`, so "none" is a genuine classifier verdict, not a budget cutoff. Run
accuracy 0.867 (sanity — pipeline healthy). Raw:
[`data/2026-07-05-pair-gate-trace.jsonl`](data/2026-07-05-pair-gate-trace.jsonl).

## Data (n=933 pairs; 412 relations, 521 none — 55.8% none-rate)

Matches the 56% none-rate from the [token-levers note](2026-07-05-ingestion-token-levers.md),
so the sample is representative. Split: crossdoc 479 pairs / 162 relations,
indoc 454 / 250.

| cosine | min | p10 | median | mean | p90 | max |
| --- | --- | --- | --- | --- | --- | --- |
| positive (relation) | 0.430 | 0.625 | 0.784 | 0.783 | 0.952 | 1.000 |
| negative (none) | 0.356 | 0.534 | 0.646 | 0.642 | 0.746 | 0.864 |

Threshold sweep (keep cosine ≥ t, skip the rest):

| t | calls skipped | positive recall | relations lost |
| --- | --- | --- | --- |
| 0.50 | 2.1% | 98.8% | 5 |
| 0.55 | 9.5% | 96.1% | 16 |
| 0.57 | 13.6% | 95.1% | ~20 |
| 0.60 | 20.4% | 93.0% | 29 |
| 0.65 | 35.9% | 85.0% | 62 |
| 0.70 | 52.5% | 75.0% | 103 |

## Conclusions

1. **The cosine gate barely earns its complexity.** ~14% call reduction at 95%
   recall, ~20% at 93%. The medians differ (0.78 vs 0.65) but the distributions
   overlap heavily — many real relations (supersession/contradiction of the same
   object with *different* values) sit at moderate cosine, and many "none" pairs
   are same-family/same-topic and score high. Semantic similarity is not the
   signal that decides a relation; the classifier is doing real work a cheap
   floor can't replicate.
2. **The projected 50–70% call cut is not achievable safely** — reaching it costs
   25%+ of real relations (missed supersession → wrong current-state answers).
3. **A1 is demoted, not deleted.** A conservative floor (t≈0.55, ≥96% recall,
   ~10% fewer calls) is a small free win *if* gated on the synthetic A/B — but it
   is not the token lever it was scoped as.
4. **The real token levers are distribution-independent:** A2 batching (collapses
   ~52 calls → a handful and stops re-sending the ~87%-of-cost system prompt) and
   A3 prefix caching. These cut tokens whether or not any pair is gated. Build
   these first.
5. **A5 (deterministic short-circuit) needs its own measurement** — how many
   positives are rule-decidable supersessions (same family+actor+monotonic date)?
   That is a different characterization, not answered here.

## Next

Reprioritized build order: **A2 → A3 first** (primary token wins), then A5 (after
its own characterization), then A1 only as an optional conservative gate. Track B
(retrieval accuracy) unchanged.
