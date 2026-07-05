# H9 — LongMemEval Answer-Path Optimization (Experiment)

**Branch:** `claude/bench-push`
**PR:** [#30](https://github.com/RavindraTarunokusumo/Nexus/pull/30)
**Merge commit:** `a44368b`
**Merged at:** 2026-07-05T13:49:06Z
**Merged by:** RavindraTarunokusumo

## Summary

Experiment tooling + docs only — no `app/` runtime change. Built an
answer-path replay harness for LongMemEval and used it to find that
answer-path-only changes lift replay accuracy **0.692 → 0.834 at −37%
tokens** (baseline 0.72 / 2346 tok). The ≥0.80-with-token-efficiency target
is met decisively; ≥0.90 is not reachable on the answer path alone (~0.83
ceiling), blocked by three retrieval-side walls documented as H9b follow-up.

Key levers found: **Chain-of-Note** (in-band `notes` reasoning field, +14
pts) and **lean prompt** (strip per-block metadata, −36% tokens, zero
accuracy loss). Rejected by data: chronological reordering (hurts once
reasoning is on) and dropping evidence blocks (starvation, 62 abstentions).

Log: [`docs/experiments/2026-07-04-longmemeval-answer-path.md`](../../experiments/2026-07-04-longmemeval-answer-path.md).
Ingestion-side follow-on analysis: [`docs/experiments/2026-07-05-ingestion-token-levers.md`](../../experiments/2026-07-05-ingestion-token-levers.md).

## Tasks Completed

- [x] Harness — `scripts/benchmarks/run_longmemeval.py --dump-context`
  (gated, default off) serializes retrieved `context_blocks` into
  `results.jsonl` so one full run doubles as a replay cache; new
  `scripts/benchmarks/replay_answer.py` re-runs only the answer LLM + judge
  over the fixed cache under variant configs (model, thinking, block order,
  Chain-of-Note, lean prompt, context trim). (`c8b68fe`)
- [x] Results — full variant sweep + `docs/experiments/` lab-notebook folder
  (README + writeup + raw `data/*.json`). (`c1fc282`)
- [x] Bundled PR review response (`3575654`) — replay robustness, cache
  validation, helper tests.
- [x] Reframing — corrected token-efficiency framing: the answer path is
  only 3.4% of end-to-end tokens; extraction (56.9%) + relation
  classification (38.8%) dominate. (`6e8669d`)
- [x] H9c — real end-to-end token-lever mechanism analysis (code-traced,
  n=211: 2.1 docs, 21 capsules, 22.6 relations/instance): `classify_relation`
  is 51.7 calls/q (pairwise capsule classification, one LLM call per
  candidate pair, O(n²) bounded by `max_pairs` — within-doc
  `extraction.py:464` + cross-doc `cross_relations.py:102`; only ~23 of ~52
  pairs persist, the rest cost a call for "no relation"). `claim_extraction`
  is 10.6 calls/q (one `complete_json` per chunk, `extraction.py:315`).
  Ranked levers (all zero-accuracy-risk, structural): (1) pre-LLM pair gate
  (cheapest & highest ROI, ~56% of pair calls return "no relation" — filter
  by T1 embedding cosine / shared `object_family` before the model, est.
  −50–70% classify calls); (2) batching + (3) prefix caching (already
  scoped as H8 M1/M2); (4) deterministic short-circuit (rule-decidable
  relations, e.g. supersession = same `object_family` + monotonic date, via
  heuristic — LLM only for ambiguous pairs). Est. relation-classify 27k →
  <10k tok/q. (`4db3c51`, `8e42241`, `cbd31fc`)

## Test Plan

`ruff check` + `ruff format --check` clean. `mypy app/` — 3 pre-existing
errors only, no regressions. `pytest tests/benchmarks/` — 32 passed. Harness
validated end-to-end: 211-instance cache build + 3 replay sweeps (16
variants). Security review not warranted (experiment tooling only, no
auth/secrets/network-boundary/privileged changes).

## Deferred / Follow-Up (kept active in TODO.md)

- **H9a** — productionize the chosen operating point (`cot_leanprompt` fast
  vs `t3_leanprompt` max — pending model-cost decision) into
  `app/intelligence/chat.py` + `prompts/chat_answer.py`, validated by a full
  end-to-end run, not just replay.
- **H9b** — 0.90 push (3 walls, retrieval-side, full re-runs): Wall 1
  top-k/ranking for un-retrieved evidence; Wall 2 supersession-direction
  ("initial/previous/original" → prefer superseded fact); Wall 3
  ordering/counting (per-sub-query retrieval slots).
- **H9c levers** — pre-LLM pair gate, batching/prefix-caching (H8 M1/M2),
  deterministic short-circuit for rule-decidable relations. Not yet
  implemented; priority note: the ~69k tok/q figure is a benchmark artifact
  (fresh corpus per question) — real read-heavy usage amortizes ingestion
  across many queries, so weigh this against answer-path work by the actual
  write/read mix. Fine-tuning is a distant last resort, scoped to
  relation-classify/extraction only, never the answer path (overfit risk).
