# LongMemEval — Nexus Benchmark Report (2026-07-04)

External benchmark for the H7 deliverable: [LongMemEval](https://github.com/xiaowu0162/LongMemEval)
(ICLR 2025), oracle split, `knowledge-update` + `temporal-reasoning` categories
(211 questions) — the two categories that map onto Nexus's supersession/lifecycle and
timeline capabilities.

## Headline result

One day of retrieval-and-answer-path work **doubled overall accuracy** on the matched
211-question slice, with the biggest gain on temporal reasoning (3.1×):

| Category (matched pairs, n=203¹) | Baseline 2026-07-04 AM | Final 2026-07-04 PM | Δ |
| --- | --- | --- | --- |
| knowledge-update (75) | 0.587 | **0.747** | +0.160 |
| temporal-reasoning (128) | 0.219 | **0.688** | +0.469 |
| **Overall (203)** | **0.355** | **0.709** | **+0.354** |
| Abstentions | 101 (50%) | 29 (14%) | −71% |

¹ Matched pairs = questions with a non-null judge verdict in both runs (8 of 211
dropped: 7 baseline instance errors, 1 final instance error). Full-run report values
(all 211): final overall 0.710 (`runs/longmemeval-full-211-final/report.md`).

## Framing and caveats (read before comparing to published numbers)

- **Oracle retrieval**: the oracle split contains only evidence sessions (~1–5 per
  question). This measures pipeline quality under oracle session-recall, not
  full-haystack retrieval. Published full-haystack numbers (SOTA memory systems ~90+
  per the mem0 2026 survey) are **not directly comparable**.
- **Judge model**: `qwen3.7-max` (Nexus T3), not the paper's GPT-4o.
  `hypotheses.jsonl` is emitted for re-judging with the official `evaluate_qa.py`.
- **Two of six categories**: chosen for relevance to Nexus's memory-lifecycle thesis;
  no claim is made about the other four.

## What changed between the runs

All changes land on branch `claude/longmemeval-h7`; specs:
`docs/superpowers/specs/2026-07-03-longmemeval-adapter.md` (Amendments 1–2),
`docs/superpowers/specs/2026-07-03-inference-optimization.md` (W amendment).

1. **T-L5 — temporal grounding of the answer path** (`8d91038`, `d0a314f`, `4056ef9`):
   the question's `question_date` is injected as `Current date:`; every context block
   carries its session date as a `Date:` line (weekday included); conflict-resolution
   instruction (supersession/lifecycle/dates → single answer); `multi_doc` recall bump.
   *Diagnosis: 74/133 temporal questions abstained with evidence fully retrieved —
   the answer path was time-blind.*
2. **T-L6 — retrieval routing + ranking** (`881cd67`): new `temporal` question shape
   (`top_k_delta=7`, date-arithmetic hint) — an `agent_runs` audit showed 90% of
   temporal questions routed to `factoid` (k=5, single-fact tuning) while every
   abstention was a two-event comparison; recency scoring now uses `published_at`
   (event time) over `created_at` (ingestion order).
3. **R4 — span evidence in the answer prompt** (`f1b8f76`): span retrieval existed
   end-to-end but excerpts never reached the model; up to 2 excerpts per block now
   render under the capsule text, letting relative-time utterances ("two weeks ago")
   anchor to their session date.

### Extraction model selection (de-confounding)

A cheaper-extraction experiment (`T2_MODEL_FORCE`) initially masked the answer-path
gains. Matrix on 51 matched questions (T-L5 stack constant):

| Extraction model | Accuracy |
| --- | --- |
| qwen-flash | 0.333 |
| qwen3.5-flash | 0.353 |
| **qwen3.6-flash** | **0.431** |
| (baseline, 3.6 pre-fixes) | 0.373 |

Decision: extraction stays on `qwen3.6-flash`. Runs:
`runs/longmemeval-55-qwen3{5,6}flash/`, `runs/longmemeval-full-211-post-t-l5/` (partial).

### Iteration speed (H8-W)

The baseline run took 5h51m serially. Instance sharding across 6 scratch DBs
(`--workers 6`), concurrent relation/judge call loops, and client-side 429/5xx retry
(`a197466`, `81ddfe5`, `0f56d2e`) brought the full 211 to **34 minutes** and a
55-question working subset (`--limit 55`) to ~10 minutes.

## Remaining failure modes (final run, 21 residual failures on the 55-subset probe)

1. Counting/aggregation recall ("how many X before Y") — needs all matching capsules
   in context. **Attempted and reverted same day**: sub-query union retrieval
   (classifier emits per-entity sub-queries, retrieval pools their ANN candidates)
   regressed the 55-subset from 0.611 to 0.574 accuracy (abstentions 5→8). Root cause:
   pooling then reranking globally lets one comparandum's sub-query dominate the
   shared top-k and starve the other side. A corrected design (guaranteed per-sub-query
   slots before the shared rerank) is logged as a follow-up in the spec, not shipped.
2. Date-arithmetic near-misses (off-by-one day/week) — partly judge-boundary noise.
3. Residual relative-date anchoring where the capsule text carries the phrase but the
   span excerpt was not among the first 2 rendered. Held alternative: extraction-time
   date normalization in the `conversation_v1` pack.

## Reproduction

```
DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5432/nexus_lme \
python -m scripts.benchmarks.run_longmemeval \
  --dataset evals/memory/longmemeval/longmemeval_oracle.json \
  --categories knowledge-update,temporal-reasoning --limit 0 --k 5 \
  --pack conversation_v1 --workers 6 \
  --db-url-template 'postgresql+asyncpg://nexus:nexus@localhost:5432/nexus_lme_w{n}' \
  --out docs/benchmarks/runs/longmemeval-full-211-final
```

Worker DBs are provisioned with `CREATE DATABASE nexus_lme_w{1..6}` + `alembic upgrade
head`. Dataset download per `evals/memory/longmemeval/README.md`.
