# H7 — LongMemEval External Benchmark + Retrieval/Answer-Path Fixes (+ H8-W Speed-Up, H8 Q0)

**Branch:** `claude/longmemeval-h7`
**PR:** [#29](https://github.com/RavindraTarunokusumo/Nexus/pull/29)
**Merge commit:** `b8536b9`
**Merged at:** 2026-07-04T20:35:17Z
**Merged by:** RavindraTarunokusumo

## Summary

Built the LongMemEval external-benchmark adapter (H7, user-directed 2026-07-03,
top of the hackathon backlog) and, driven entirely by its matched-pair benchmark
evidence, a set of retrieval and answer-path fixes for temporal reasoning. On the
211-question `knowledge-update` + `temporal-reasoning` slice (oracle retrieval,
`qwen3.7-max` judge): **overall accuracy 0.355 → 0.709** (matched pairs, n=203),
knowledge-update 0.587 → 0.747, temporal-reasoning 0.219 → 0.688, abstentions
101 → 29. Also folded in: a rerun speed-up (H8-W, user-directed 2026-07-04;
5h51m → 34min via instance-parallel workers + concurrent LLM call loops) that
made the empirical iteration loop itself viable, H8 Q0 (disable qwen3 default
thinking mode), and a fully documented failed experiment (sub-query union
retrieval) reverted the same day after it regressed its own validation gate.

Specs:
[`docs/superpowers/specs/2026-07-03-longmemeval-adapter.md`](../../superpowers/specs/2026-07-03-longmemeval-adapter.md)
(adapter + two amendments),
[`docs/superpowers/specs/2026-07-03-inference-optimization.md`](../../superpowers/specs/2026-07-03-inference-optimization.md)
(H8-W amendment).
Plan: [`docs/superpowers/plans/2026-07-03-longmemeval-adapter.md`](../../superpowers/plans/2026-07-03-longmemeval-adapter.md).
Report: [`docs/benchmarks/longmemeval-2026-07-04.md`](../../benchmarks/longmemeval-2026-07-04.md).

## Tasks Completed

- [x] T-L1 — `scripts/benchmarks/run_longmemeval.py` adapter (session→document
  mapping, per-instance DB truncation, full pipeline, T3 QA judge per the
  official protocol, `hypotheses.jsonl` for the official scorer) + 13
  pure-helper unit tests + dataset README/.gitignore. (Grok implementer; 550
  passed / 6 pre-existing.)
- [x] T-L2 — Run 1: 0/20 (all abstentions) — pack-mismatch confirmed (9/20
  instances zero capsules; the `personal_ai_tech` pack's telos didn't extract
  personal facts). Also found: dataset order not category-interleaved.
- [x] T-L3 — `conversation_v1` domain pack (7 families, user-as-protagonist
  facet guidance, personal-state supersession, Qwen ids + no-deepseek
  regression test) + adapter `--pack` flag.
- [x] T-L4/T-L5d — Full-211 before/after: 0.355→0.709, KU 0.587→0.747, TR
  0.219→0.688, abstentions 101→29 (matched pairs, n=203); final run 34 min at
  6 workers.
- [x] T-L5 — Answer-path temporal grounding: `as_of` question-time anchor
  through `run_chat_with_context` → chat state → `build_user_prompt`
  (`8d91038`); `SYSTEM_PROMPT` conflict-resolution instruction + `multi_doc`
  top_k_delta 3→5 (`d0a314f`); `_judge_answer` LLM-error retry (`4056ef9`).
  Diagnosis: 74/133 temporal questions abstained with evidence fully
  retrieved — the answer path was time-blind.
- [x] T-L6 — Retrieval routing + ranking: `temporal` question shape (an
  `agent_runs` audit showed ~90% of temporal questions routing to `factoid`,
  tuned for single-fact lookup) + event-time recency scoring on `published_at`
  (`881cd67`); span evidence excerpts rendered in the answer prompt (R4,
  targets relative-date anchoring — spans were retrieved but never shown to
  the model). Extraction-model matrix (51 common ids): qwen-flash 0.333 /
  qwen3.5-flash 0.353 / **qwen3.6-flash 0.431** (vs pre-fix baseline 0.373) →
  extraction stays on qwen3.6-flash.
  - **R2 — sub-query union retrieval: implemented, benchmark-validated,
    reverted (`bc8fe83` → `ec1962a`).** Regressed the 55-subset validation
    gate (0.611→0.574 acc, abstain 5→8, 9 regressed/7 fixed). Root cause:
    pooling per-entity sub-query candidates then reranking globally lets
    whichever entity's sub-query matches more capsules dominate the shared
    top-k and starve the other comparandum — a design flaw, not a bug.
    Corrected design (per-sub-query floor before the shared rerank) logged in
    the spec as a follow-up, not reattempted.
- [x] H8-W — Rerun speed-up: `--workers`/`--db-url-template` instance sharding
  (`a197466`); `asyncio.gather`+semaphore for the three remaining serial LLM
  call loops (`81ddfe5`, shared with W4); bounded retry with backoff in
  `LLMClient.complete_json` on 429/5xx/network (`0f56d2e`); `T2_MODEL_FORCE`
  env override for benchmark-time extraction routing (`81ddfe5`). 5h51m →
  34min for the full 211-question run.
- [x] H8 Q0 — Disable default qwen3 thinking mode in `complete_json`
  (`thinking: bool = False`, `79d3433`): live A/B showed identical outputs at
  3.6× faster extraction and 12× faster relation classification. Diagnosed
  via `agent_runs` prompt/completion split.
- [x] `/simplify` pass (`be034c4`) — 4 parallel Grok reviews (reuse,
  simplification, efficiency, altitude): hoisted a per-retry-attempt
  `httpx.AsyncClient` construction introduced by the retry work, narrowed a
  since-redundant judge-level retry to the one case the client doesn't cover,
  removed a duplicate `mkdir`, fixed a stale comment.
- [x] Bundled PR review response (`ad3e623`) — per-worker `Embedder` (a shared
  instance serialized every worker's I/O behind synchronous encode calls),
  `rows` UnboundLocalError guard, `zip(strict=True)` session alignment,
  `question_date`-missing warning, DashScope-gated `enable_thinking`,
  `T2_MODEL_FORCE` warning, shared `t2_concurrency` setting.

## Deferred / Not Reattempted

- R2 corrected design (per-sub-query retrieval floor before global rerank) —
  logged in the spec, not reattempted.
- `/simplify` altitude findings not applied (each needs its own scope/spec):
  `as_of` as a first-class chat API field (currently benchmark-only, defaults
  to `now()` in production), capsule-level (not document-level) event-date
  recency, shared non-UUID span-ref validation helper, provider-model config
  profiles for `enable_thinking`.
- H8's broader scope (M1 span batching, M2 prefix caching, M3 pre-extraction
  filter, M4 domain-scoped retrieval, T2 distillation) remains open —
  `docs/superpowers/specs/2026-07-03-inference-optimization.md`.

## Validation

Full suite (`ruff check`, `ruff format --check`, `mypy app/`, `pytest`) green
at every commit: 576 passed, 6 pre-existing failures unchanged throughout
(verified identical against `main` via stash comparison and a fresh `mypy`
baseline run). Security review (network-call/retry-path change): no
HIGH-confidence findings. Bundled PR review: 7 findings, all addressed via the
`receiving-code-review` reception protocol (one pushed back on — the shared
`Embedder` finding was labeled a "race condition," corrected to the actual
mechanism: asyncio's single-threaded event loop serializes synchronous calls,
so the defect is throughput, not a race).
