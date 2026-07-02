# Phases D/E/F — Retrieval, Living Knowledge, Memory Benchmark (Qwen Hackathon)

**Branch:** `claude/def-hackathon`
**PR:** [#25](https://github.com/RavindraTarunokusumo/Nexus/pull/25)
**Merge commit:** `b57d21c`
**Merged at:** 2026-07-02T22:13:00Z
**Merged by:** RavindraTarunokusumo

## Summary

Implemented the hackathon critical-path Phases D (retrieval & Qwen context assembly), E
(living knowledge — lifecycle + consolidation workers), and F (Nexus-native memory
benchmark), then produced the first live end-to-end MemoryAgent baseline on Qwen Cloud.
Delegation: Wave 1 (6 parallel tasks) via Grok subagents; mid-session the user redirected
Wave 2+ and code review to native Sonnet 5 subagents. Interactive spec-acceptance was
skipped on explicit user instruction (one-week hackathon deadline); the plan doc served
directly as the implementer contract.

Plan: [`docs/superpowers/plans/2026-07-02-def-hackathon.md`](../../superpowers/plans/2026-07-02-def-hackathon.md)

## Tasks Completed

**Phase D — Retrieval & Qwen context assembly**
- [x] D1 — Context-assembly `include` categories (primary / counter-evidence / supersession
  auxiliary blocks, capped 2 each) + `evidence_strength` ordering + per-block epistemic
  notes. (`f809b8c`)
- [x] D2 — Un-stubbed hybrid-score inputs: real `source_authority`, `evidence_quality`,
  `relation_relevance` (deterministic maps + per-capsule relation counts). (`f809b8c`)
- [x] D3 — Configurable `llm_base_url` + `QWEN_CLOUD_API_KEY` routing (`llm_api_key`
  fallback property); all 5 `LLMClient` call sites routed through settings; `.env.example`
  added; verified live against DashScope-intl with `qwen3.6-flash`/`qwen3.7-max`. (`5b464ea`)

**Phase E — Living knowledge**
- [x] E1/E2 — Deterministic lifecycle worker (`app/intelligence/lifecycle.py`):
  precedence superseded > contradicted > qualified > confirmed > stale > archived over
  candidate/active capsules, using relations + pack retention heuristics;
  `nexus lifecycle run` CLI. (`d9a881b`)
- [x] E3 — Consolidation worker (`app/intelligence/consolidation.py`) — thin wrapper over
  the Phase C thesis writer; `nexus consolidation run` CLI. (`ca9b44d`)
- [x] CLI registration for `lifecycle`/`consolidation` in `app/cli/main.py`. (`bcf6102`)

**Phase F — Benchmarking agentic memory**
- [x] F1 — Benchmark survey mapping LoCoMo/LongMemEval/BEAM/Memora/RAG baselines to Nexus
  capabilities (implemented-now vs stretch). (`ae3228a`)
- [x] F2 — `evals/memory/nexus_synthetic/` fixtures: 14-doc fictional AI-tech corpus + 22
  questions across 6 categories (timeline, multi_doc, superseded, authority_conflict,
  thesis, abstention). (`2f9d089`)
- [x] F3/F5 — `scripts/benchmarks/{scoring,run_memory_benchmark}.py` — pure F5 metric
  functions + async ingest→extract→lifecycle→consolidate→answer→score pipeline. (`1d93996`)
- [x] F4 — `nexus eval memory run`/`report` CLI surface. (`f9b75fe`)
- [x] F6 — Baseline artifacts: plan, `baseline-template.md`, `baseline-2026-07-02.md`
  summary + `runs/baseline-2026-07-02/`. (`1a953aa`, refreshed `de5db0b`)

**Bring-up fixes found and fixed during F6 live validation**
- [x] `capsule_segments.role="support"` CHECK violation (pre-existing bug, open since
  Phase B) — fallback role now `"grounds"` (column default) + `claim_evidence`→segment
  vocabulary translation (`support`→`supports`, `refute`→`contradicts`). Was blocking
  every real-DB capsule write; the first benchmark attempt produced zero capsules.
  Fixed 8 of 14 pre-existing real-DB test failures. (`1df68cc`)
- [x] Supersession heuristic over-fired on historical events — a newer same-actor/
  same-type record was marking permanent records (GA dates, funding rounds) `superseded`,
  and retrieval only serves `active/confirmed/qualified`, so correct history was filtered
  out (surfaced by the live `demo_answer` walkthrough). Restricted the heuristic to
  `core_type="state_change"`. Dropped `forbidden_violation` 0.091→0.000, lifted
  `superseded` category 0.444→0.556. (`1f23fad`)
- [x] Relation classifier routed to a dead model — the domain pack's top-level
  `models.t2/t3` hardcoded `deepseek/deepseek-v4-flash`, which `_resolve_t2_model` returns
  ahead of `settings.t2_model`; this 404'd on DashScope and was the **real** root cause of
  0 relations / 0 theses (not a cross-document-architecture limit, as first diagnosed).
  Switched pack + config defaults to `qwen3.6-flash`/`qwen3.7-max`. Result: 22–27
  relations, 7–9 theses, 6–7 `confirmed`-lifecycle capsules per run (were 0/0/0). (`90289fe`)

**Review + demo + docs**
- [x] PR #25 code review (Sonnet 5 subagent) — 4 MEDIUM + 2 LOW findings; 5 fixed same
  session (lifecycle archived/stale precedence dead-branch, fake `skipped_existing`
  metric, dead `openrouter_api_key` parameter, dead `embedding_model` config, trailing
  newline), 1 LOW deferred to `TODO.md` (double aux-block discovery walk — perf nit, not
  a bug). Retrieval correctness, security/key-threading, capsule-role fix, and scoring
  math verified clean by the reviewer. (`279ef46`)
- [x] Live demo driver `scripts/benchmarks/demo_answer.py` + two demo findings logged.
  (`fa6b32f`)
- [x] Root `README.md` demo guide (env setup → one-command benchmark → interactive
  `demo_answer` → per-stage pipeline table); verified reproducible end-to-end via the
  documented `nexus eval memory run`/`report` commands on a fresh DB post-merge. (`d5bd0ea`)

## Test Results

Full suite: 505 passed / 6 pre-existing failures (mock under-provisioning in
`test_extraction_graph.py` / `test_capsules_dual_write.py` — multi-span fixture seeded
with a single mocked LLM response; unrelated to this branch) — down from 14 pre-existing
failures at session start thanks to the capsule-role fix. `ruff check`/`ruff format`/
`mypy app/` identical to the pre-existing baseline throughout (2 pre-existing ASYNC240,
3 pre-existing mypy errors, 6 pre-existing unformatted files, none introduced).

Live end-to-end validation on Qwen Cloud (`qwen3.6-flash`/`qwen3.7-max`, DashScope-intl):
first baseline scored answer_correctness 0.568, citation_faithfulness 1.000, abstention
0.773 with 0 relations/0 theses (bring-up bugs above still present); after the three
fixes, a re-run produced 22–27 relations and 7–9 theses, `forbidden_violation` dropped to
0.000, and `superseded`/`authority_conflict` categories improved. A final README-command
verification run post-merge reproduced the same shape (63 capsules, 27 relations, 9
theses) confirming the documented `nexus eval memory run` path works from a clean clone.

## What This Phase Did Not Do (backlog)

- Cross-document relation classification — `classify_relations` still only pairs
  capsules within a single document's extraction run; explicit `supersedes`/`contradicts`
  edges across documents are not yet created. Logged in `TODO.md`.
- `nexus lifecycle run --json` prints nothing when there are zero new transitions
  (demo finding, LOW). Logged in `TODO.md`.
- Double aux-block discovery walk in `chat.py` retrieval (PR review finding, LOW,
  deterministic — perf nit only). Logged in `TODO.md`.
- G1–G3, H-MCP1/2, H-SKILL1, and the remaining hackathon submission assets (architecture
  diagram, demo video outline, Devpost narrative) — still open in `TODO.md`.
- Timeline/factoid-recall category remains the weakest benchmark score (0.25–0.5 across
  runs) — flagged as the top follow-up in `docs/benchmarks/baseline-2026-07-02.md`.

## Workflow Notes

See `docs/insights.md`, session `def-hackathon (2026-07-02)`, for the full retrospective:
notably the value of live end-to-end validation over trusting a first "0 relations" theory
(the real root cause — a dead model ID in the domain pack — was two layers deeper than the
initial cross-document-architecture diagnosis), and running the exact documented CLI
command as its own verification step before declaring a README accurate.
