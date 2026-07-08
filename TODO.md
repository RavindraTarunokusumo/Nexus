# TODO

## Hackathon Critical Path — Qwen Cloud MemoryAgent (deadline 2026-07-09 5pm EDT)

> Submission target: Devpost Qwen Cloud Hackathon, Track 1 MemoryAgent. For the hackathon branch, optimize for a working Qwen-powered memory demo, benchmark report, and submission package. Defer broad roadmap items that do not strengthen the MemoryAgent story within one week.

- [x] H7 — LongMemEval external benchmark + retrieval/answer-path fixes for temporal reasoning (+ H8-W speed-up, H8 Q0). Overall accuracy 0.355→0.709 (matched pairs, n=203). Shipped in PR #29 (merge `b8536b9`). Archived: `docs/iterations/archive/2026-07-04-longmemeval-h7.md`. Report: `docs/benchmarks/longmemeval-2026-07-04.md`.

- [X] H0 — Register/verify Qwen Cloud access, API key, voucher credits, and model availability from the deployment environment.
- [x] H1 — Route **T2 and above** through Qwen Cloud / Model Studio models; keep model names configurable by environment and domain pack. (PR #25 D3/G4)
- [x] H2 — Produce a MemoryAgent demo script: ingest AI-tech memory stream → extract capsules → relate/consolidate → supersede stale memory → answer with citations → show benchmark report. (PR #25; `scripts/benchmarks/demo_answer.py` + `nexus eval memory run`)
- [x] H9 — LongMemEval answer-path optimization (experiment). Chain-of-Note + lean prompt lift replay accuracy 0.692→0.834 at −37% tokens; ≥0.80-with-efficiency target met, answer-path ceiling ~0.83 established. Shipped in PR #30 (merge `a44368b`). Archived: `docs/iterations/archive/2026-07-05-longmemeval-answer-path-h9.md`. Log: `docs/experiments/2026-07-04-longmemeval-answer-path.md`.
  - [x] H9a — Productionized **`cot_leanprompt`** (CoN + lean prompt, T2 model) into `chat_answer.py` + `chat.py`. Shipped in PR #31 (merge `3f282d6`). Full-211 validation: matched frozen-context replay **0.702→0.817** (McNemar p=7e-5), fresh full run 0.812, −26% tokens — reproduces PR #30's 0.806. Archived: `docs/iterations/archive/2026-07-05-h9a-chain-of-note.md`.
  - [ ] H9b — 0.90 push (session `claude/h9b-walls`): wall re-sizing done — E2 full-211 baseline 0.821 with dumped contexts, taxonomy of the 37 failures (wall1 15 scripted / ~8–10 true, wall2 only 3 → demoted, wall3 6, abstention-with-evidence ~7, judge noise ≥3, truncation errors 4). Log: `docs/experiments/2026-07-06-h9b-wall-taxonomy-truncation.md`.
    - [x] E2 baseline + failure taxonomy + frozen-context replay A/B: **max_tokens 2000→4000 is the single significant answer-path lever** (replay 0.802→0.850, McNemar p=0.013); nostep5/confident prompt dials not significant. Productionized in `ff77d19`.
    - [x] Fresh n=50 validation of the 4k fix — **CONFIRMED on third attempt**: `b3-gate-4k` 0.820 vs 0.760/0.760 same-code noise pair (+3 questions, 0 schema errors on the gate). First two attempts invalid. (a) Full-211 attempt launched without `--pack conversation_v1` → `personal_ai_tech` default pack produced near-zero extractions, killed at 152/211. (b) n=50 attempt (`docs/benchmarks/runs/h9b-4k-validation/`, all-temporal slice) hit the **editable-install footgun**: `scripts/benchmarks/*.py` run as files left the tree root off `sys.path`, so `import app` resolved to the main checkout — the run executed 2000-token main code, and its "flat vs E2" result (0.804→0.739 matched, p≈0.45) is a same-code noise measurement, not a test of 4k. Fixed by the sys.path guard commit; proper arm re-running as `b3-gate-4k`. Replay evidence for 4k (p=0.013) still stands; `ff77d19` kept. **Iteration gate = n=50 mixed (25/category)** (user call, 2026-07-06); full-211 for pre-PR confirmation. Runner should hard-require `--pack` or warn on zero-capsule spikes (see Phase F zero-capsule item).
    - [x] Free noise-floor measurement from the footgun: two same-code n=50 gate runs (`b3-gate-baseline` vs `b3-gate-slots`, both main code) scored 0.760/0.760 overall with ±3 per-category swing and 1/6 vs 0/6 on the wall-3 subset — per-category deltas ≲3 and small-subset flips are within re-ingestion noise.
    - [ ] **FINAL experimentation batch** (user call, 2026-07-06 — after this: finalize + full evaluation runs of both benchmarks):
      - [ ] Schema-failure retry: on `LLMSchemaError` in `chat_answer`, retry once with an instruction to emit `answer`+`citations` immediately — kills the stochastic ~2–4% notes-overrun error tax that 4k did not eliminate (hits the wall-3 enumeration questions hardest).
      - [ ] Pin claim extraction to `qwen3.6-flash-2026-04-16` (live-verified on DashScope-intl; `enable_thinking=false` honored) via `settings.extraction_model`, consumed only at the span-extraction call — relation-classify and chat answer stay on the `qwen3.6-flash` alias so the tuned answer path is untouched.
      - [ ] B1 as k-bump: gate arm at `--k 10` (no code change) vs k=5 — adopt for finals if it wins.
      - [ ] Gate A/B vs `b3-gate-4k` (0.820 reference), then finalize + final runs: LongMemEval full-500 (all 6 categories, H3a) + LoCoMo all 1,878 questions.
    - [ ] B3 per-sub-query retrieval slots (6 questions) — next retrieval lever.
    - [ ] B1 fetch-pool bump / ranking (~9 true misses).
    - [ ] Abstention-with-evidence (~7) — revisit after B3/B1; no cheap prompt lever (confident-suffix p=0.34, regresses under 4k).
  - [ ] H9d — **Sentence-window architecture pivot** (session `claude/h9b-walls`). Deterministic sentence-split ingest (zero LLM), hybrid semantic+lexical (RRF) retrieval of local ±window spans, Chain-of-Note thinking reader. Replaces the LLM extraction+relation pipeline (~69k→~4–6k tok/q). **FINAL (all-Qwen stack: Qwen3-Embedding-0.6B@384 + qwen3.7-plus reader + qwen3.7-max judge, hybrid): LongMemEval-500 0.864, LoCoMo-48 0.750.** Report: `docs/benchmarks/sentence-window-qwen-2026-07-08.md`. Sub-query decomposition and entity anchoring built but off (didn't move multi_hop). Commits: inference prompt, three-lever (hybrid/subq/judge), notes coercion, entity-anchoring, Qwen embedder.
    - [x] Inference-permitting reader prompt (flag) — LME +0.02, LoCoMo abstain 9→2.
    - [x] Hybrid retrieval (lexical⊕semantic RRF) + partial-credit open_domain judge — LoCoMo temporal 0.78→0.83, open_domain 0.20→0.80.
    - [x] Sub-query decomposition — **dropped** (regressed multi_hop 0.47→0.39 via RRF dilution).
    - [x] Notes-as-list coercion in `ChatAnswerOutput` (glm-5.2/qwen thinking robustness).
    - [x] **Rung 1 — entity-anchored retrieval** (Grok build, GLiNER): built + gated. Lifted LoCoMo temporal/open_domain recall but **did not move multi_hop** (bar was ≥0.55) → confirmed multi_hop is a reader/embedding problem, not retrieval-structure. **Off** in final config.
    - [x] Qwen embedder — Qwen3-Embedding-0.6B (asymmetric query/document prompts, MRL truncation to 384, no schema migration). All-Qwen retrieval tier.
    - [x] single-session-preference judge — verified already rubric-style (matches official `evaluate_qa.py`); 0.667 is a real score, not an artifact. No change.
    - [ ] Rung 2 (deferred, post-hackathon) — local-LLM relation triples + one-hop traversal; gate on Rung 1 result (negative → likely deprioritize).
    - [ ] (post-hackathon) Reader distillation qwen3.7-plus → small local student via QLoRA — needs a purpose-built corpus (log `notes`+`context_blocks` on a teacher-generation pass; eval-run outputs are not reusable).
    - [ ] (backlog, PR #32 review) Production-readiness of the sentence-window path: **corpus-scoped retrieval** (thread document/pack filter through `retrieve_windows` — currently global, benchmark-only safe); run embed/NER via `asyncio.to_thread` in async ingest; dedupe overlapping neighbor windows in `_build_blocks`; lock NER-backend init; move shared answer constants out of `chat.py`; read recency weight at call time not import. Plus deferred /simplify cleanups (dedupe system prompts, single NER backend, `_fetch_span_hits`/recency helpers).
  - [ ] H9c — real end-to-end token levers (the answer path is only 3.4% of ~69k tok/q; extraction 56.9% + relation classification 38.8% dominate, `classify_relation` at 51.7 calls/q is the main cost). Ranked levers: (1) pre-LLM pair gate (T1 embedding cosine / shared `object_family` before the model, est. −50-70% classify calls); (2) batching + (3) prefix caching (already scoped as H8 M1/M2); (4) deterministic short-circuit for rule-decidable relations. Full mechanism trace and priority notes in the archive above.

- [ ] H3 — Add submission docs/assets: ~~README demo walkthrough~~ (done, PR #25), architecture diagram, benchmark screenshot/report, demo video outline, Devpost project narrative.
  - [ ] H3a — Full-500 LongMemEval run (all 6 categories) for the submission benchmark report. Prereq: verify the adapter's judge handles `single-session-preference` like the official `evaluate_qa.py` (rubric-style, not exact-fact QA) before trusting those 30 scores. Iteration gate is the 2-category set, currently **n=50** (full-211 for pre-PR confirmation) — full-500 is a one-off report asset, ~2.4× corpus (~4–6h, 6 workers). Footnote in the report: we run the **oracle** variant (evidence-only haystacks); published tables are mostly LongMemEval-S with distractor haystacks, so numbers are not directly comparable.
- [ ] H4 — Treat MCP integrations and repo skills as final-version improvements: document tool contracts now; implement only a thin MCP server/tool wrapper if it does not endanger the core demo.
- [x] H5 — Qwen memory query router. Complete: question-shape classification (factoid/multi_doc/current_state/conflict/general) in the shared T2 classify call, per-shape retrieval strategy + answer hints. Shipped in PR #26 (merge `5dff2b4`); timeline benchmark category 0.333→1.000, overall answer_correctness 0.568→0.678. Archived: `docs/iterations/archive/2026-07-03-router-h5.md`.
- [ ] H8 — Inference latency & token optimization (spec: `docs/superpowers/specs/2026-07-03-inference-optimization.md`). Quick wins done (Q0 thinking-mode disable, span/pair/question call concurrency, instance-parallel workers, client retry — archived under H7/`2026-07-04-longmemeval-h7.md`). Remaining — Medium: span batching, DashScope prefix caching, pre-extraction span filter, domain-scoped retrieval. Future: T2 distillation — fine-tune a small Qwen on validated `agent_runs` traces; scope is at most a trace-export tool for now, not the fine-tune.
- [x] H6 — Demo UI console. Read-only three-tab console over the existing `web/` chat app (Dashboard, Chat enrichment, How-it-works Mermaid views): no auth, no live-refresh, no ingest-from-UI in v1. Shipped in PR #28 (merge `b9047b0`). Archived: `docs/iterations/archive/2026-07-05-demo-ui-console-h6.md`. Spec: `docs/superpowers/specs/2026-07-04-demo-ui-console.md`.

- [ ] **UI display-consistency refactors (H6 /simplify, deferred)** — unify the citation-role vocabulary (badge class/label/diagram counts) and the lifecycle-state palette (CitationList dots / dashboard swatches / mermaid classDefs) into single frontend maps; shared `excerpt()` util for `routes_capsules._excerpt` vs `chat.py`'s span-excerpt shaping (cross-module). Query-merging on `/stats/overview`/provenance skipped: sub-10ms on demo-scale data.

### H8 + H9b/H9c — Ingestion & Retrieval Optimization (session `claude/perf-h8h9`)

Spec: `docs/superpowers/specs/2026-07-05-ingestion-retrieval-opt-h8h9.md`. Experiment-first; Track A (ingestion tokens, zero accuracy risk) before Track B (retrieval accuracy, full re-runs). E1 pair-gate characterization + Track-B baseline diagnostic + H9a shipped in PR #31 (merge `3f282d6`); archived under `docs/iterations/archive/2026-07-05-h9a-chain-of-note.md`. Remaining active follow-up below.

- [ ] **A1 — pre-LLM candidate-pair gate** (H9c lever 1, DEMOTED by E1 to optional): E1 (n=933) showed a cosine floor skips only ~14% of classify calls at ≥95% recall, not the projected 50–70%. Conservative floor (t≈0.55, ~10% fewer calls at ≥96% recall) on `pairs` in `extraction.py::_run_classify_relations` + `cross_relations.py`; `settings.relation_pair_cosine_floor` (default 0 = off). Build only if A2/A3 leave call-count worth trimming. Gate: synthetic A/B relation/`superseded` quality holds.
- [ ] **A2 — relation-pair batching** (H8 M1, NOW PRIMARY): N pairs/call, keyed outputs, per-pair fallback on parse failure — cuts the ~87%-of-cost repeated system prompt regardless of pair count. Gate: synthetic quality holds, tokens/q down.
- [ ] **A3 — DashScope prefix caching** (H8 M2): verify API surface live, cache static system-prompt prefix on extraction/relation calls. Gate: billed prompt tokens down, outputs identical.
- [ ] **A4 — pre-extraction span filter** (H8 M3): local greeting/boilerplate/length pre-filter before extraction call; conversation-heavy win. Gate: capsule count/quality holds.
- [ ] **A5 — deterministic short-circuit** (H9c lever 4): rule-decide unambiguous supersession (same family+actor+monotonic date) before the LLM. Gate: precision sample matches LLM verdict.
- [ ] **B1 — Wall 1 top-k/ranking** (H9b): raise fetch pool / improve ranking so un-retrieved gold survives the cut. Gate: LongMemEval `cov` up, no regression.
- [ ] **B2 — Wall 2 supersession-direction** (H9b): detect "initial/previous/original" and flip recency preference (router + `compute_hybrid_score`). Gate: `supersession_correctness` up.
- [x] **B3 — Wall 3 per-sub-query retrieval slots** (H9b, session `claude/h9b-walls`): built (`46d0863`) behind `settings.retrieval_subquery_slots`, **A/B gate FAILED — flag stays off**. Gate 0.820→0.776 (5 up/7 down, ns) and wall-3 0/6 vs 1/6, flipping the same ordering question right→wrong in two independent replicates, with emission verified real in `agent_runs`. Verdict + evidence: `docs/experiments/2026-07-06-h9b-wall-taxonomy-truncation.md` §B3 A/B verdict. Wall-3 residual is answer-path (date arithmetic, notes-overrun schema errors on enumeration questions), not retrieval — code kept for possible reuse, do not flip without a new hypothesis.
  - [x] Task 1: classifier emits `sub_queries` (`46d0863`).
  - [x] Task 2: slotted retrieval merge + config flag + unit tests (`46d0863`).
  - [x] A/B gate run (correct code post-footgun): 4k-only arm doubles as the **4k production confirmation** — 0.820 vs 0.760/0.760 same-code noise pair, 0 schema errors on the gate.

### Phase C — Reasoning Layer

Complete. Thesis writer, decision artefact writer, and DB integration tests shipped in
PR #24 (merge `f660b8d`). Archived: `docs/iterations/archive/2026-07-02-phase-c-remainder.md`.

### Phases D/E/F — Retrieval, Living Knowledge, Memory Benchmark

Complete. Context-assembly + un-stubbed hybrid scoring (D), lifecycle + consolidation
workers (E), and the Nexus-native memory benchmark (F) shipped in PR #25
(merge `b57d21c`), along with three bring-up fixes found during live Qwen validation
(capsule-role CHECK violation, supersession heuristic over-firing on historical events,
relation classifier routed to a dead model) and the README demo guide. First live
baseline: `docs/benchmarks/baseline-2026-07-02.md`. Archived:
`docs/iterations/archive/2026-07-02-def-hackathon.md`.

### Phase F — Benchmarking Agentic Memory — open follow-ups

- [ ] **Chat retrieval: collapse double aux-block discovery** (PR #25 review, LOW) — `_discover_counter_evidence_ids`/`_discover_supersession_links` run once in `_run_retrieve_capsules` (for the DB fetch) and again in `_assemble_context_blocks`; deterministic, so a perf nit not a bug. Compute once and pass through. Ref `app/intelligence/chat.py`.
- [ ] **`nexus lifecycle run --json` prints nothing (demo finding, LOW)** — the CLI runs but emits no output in `--json` mode against an already-lifecycled corpus (0 new transitions). Should always print the report object. Ref `app/cli/lifecycle.py`.
- [x] ~~Cross-document relation pass~~ — Complete. Domain-wide `(object_family, actor)` pairing across documents, `published_at`-based direction, `nexus relations run` + benchmark stage. Shipped in PR #27 (merge `259df9b`). Archived: `docs/iterations/archive/2026-07-03-crossdoc-relations.md`.
- [ ] **Benchmark needs multi-run averaging** (T-X3 finding) — single-run categories of n=3–4 sit below the stochastic pipeline's noise floor (extraction capsule counts varied 58–65 across three same-code runs; category scores swung ±0.25). Add `--runs N` aggregation with per-category mean/stddev to `run_memory_benchmark`, and set gates on means. Ref `scripts/benchmarks/run_memory_benchmark.py`.
- [x] ~~Recency score input is ingestion order, not publication date~~ (T-X3 finding) — resolved by H7 T-L6 R3: `compute_hybrid_score` and its `recency_min`/`recency_max` normalization now use `published_at` when set, falling back to `created_at`. Ref `app/intelligence/chat.py::compute_hybrid_score`.
- [ ] **Cross-doc pair-attempt ledger/cursor** (PR #27 review, deferred) — pairs classified `none` are never recorded, so reruns re-send the same top-`max_pairs` LLM calls and tail pairs beyond the cap may never be reached. Persist negative attempts or rotate a cursor. Ref `app/intelligence/cross_relations.py`.
- [ ] **Extract a shared relation-persist helper** (crossdoc /simplify finding, deferred) — `cross_relations.py` duplicates ~25 lines of classify-and-persist (canonical/domain type split, row construction) from `extraction.py::_run_classify_relations`; the crossdoc spec constrained `extraction.py` to import-only, so dedup means a small shared module both import. Do it when `extraction.py` is next open for changes.
- [ ] **Transient extraction failure leaves a doc at `claims_extracted` with zero capsules** (T-X3 run-2 finding) — a `network_error` on one doc's `claim_extraction` silently produced an empty memory footprint while the status advanced, so the planned re-extraction sweep (which watches `extraction_partial`/`extraction_failed`) would never catch it. Needs a retry or a zero-capsule status check in the extraction graph. The benchmark runner now warns on zero-capsule docs. Ref `app/intelligence/extraction.py`.
- [x] ~~Timeline/factoid-recall category is the weakest benchmark score~~ — resolved by the H5 query router (PR #26): timeline answer_correctness 0.333→1.000, temporal_correctness 0.25→1.00.
- [ ] **Router follow-up (PR #26 review)** — surface `question_shape` per-question in the benchmark `results.jsonl` (the chat graph already returns it in final state; the runner just doesn't record it) so shape-routing accuracy can be audited; revisit the `conflict`/`current_state` routing if `authority_conflict`/`supersession_correctness` stay flat on the next pass (authority_conflict 0.333→0.250 on n=3 in the T-R2 run — single-question shift, watched).
- [ ] ~~Stretch after baseline — LoCoMo/LongMemEval adapters~~ — promoted to **H7** at the top of the hackathon critical path (user-directed 2026-07-03); BEAM/Memora remain post-hackathon.
- [ ] **R2 sub-query union retrieval — corrected design** (H7 T-L6 follow-up, deferred) — the reverted attempt (`bc8fe83`→`ec1962a`) pooled per-entity sub-query candidates then reranked globally, letting one entity's sub-query dominate the shared top-k. Corrected design: allocate a floor per sub-query (e.g. `ceil(effective_top_k / (1 + len(sub_queries)))` guaranteed slots) before any shared rerank. Ref `docs/superpowers/specs/2026-07-03-longmemeval-adapter.md` Amendment 2.
- [ ] **`as_of` as a first-class chat API field** (H7 bundled-review altitude finding, deferred) — `run_chat_with_context`'s `as_of` is only reachable from the benchmark; `/chat/answer` always defaults to `now()`. Add it to `ChatAnswerRequest` (or derive from session metadata) so temporal grounding covers real usage, not just the benchmark. Ref `app/api/routes_chat.py`, `app/intelligence/chat.py`.
- [ ] **Capsule-level event-date recency** (H7 bundled-review altitude finding, deferred) — recency now scores on `Document.published_at`, so every capsule from one document shares one timestamp; a multi-event document (e.g. one session mentioning several dated events) can't rank them apart. Needs per-capsule event dates (parsed `facets.dates`?) with document date as fallback. Ref `app/intelligence/chat.py::compute_hybrid_score`.
- [ ] **Shared non-UUID span-ref validation helper** (H7 /simplify finding, deferred) — `app/intelligence/capsules.py` and `app/intelligence/extraction.py` each guard non-UUID span refs with an identical try/except/skip; validate/normalize once at the LLM output boundary instead. Ref both files' non-UUID guards.

### Phase G — Qwen Model Tiering (hackathon required)

> T2 and above must be Qwen-based for submission. Also scout/validate whether Qwen can cover T0/T1 so the whole stack can be presented as Qwen-native.

- [x] G1 (T2/T3) — `qwen3.6-flash` (T2: extraction, judging, relation classification, chat) and `qwen3.7-max` (T3: synthesis, thesis writing, decision artefacts) wired as config defaults + domain-pack overrides. (PR #25 H1/D3/G4)
- [ ] G1 (T0/T1/T4 stretch) — T0 embeddings via `Qwen3-Embedding-0.6B`/`text-embedding-v4` (T1 currently runs locally via `BAAI/bge-small-en-v1.5`); T1 reranking via `Qwen3-Reranker-0.6B`/`qwen3-rerank`; T4 high-confidence audit/adjudication pass.
- [x] G2 — Verify exact Qwen Cloud model IDs, base URL (`https://dashscope-intl.aliyuncs.com/compatible-mode/v1`), and live availability. (PR #25 D3, confirmed via the F6 baseline run)
- [x] G3 — Environment examples for Qwen Cloud: base URL, API key variable, tier-to-model overrides. (`.env.example`, PR #25)

### Phase H — MCP / Skills Integration Story (hackathon stretch)

- [ ] H-MCP1 — Document MCP tool contracts for final version: `nexus.memory.search`, `nexus.memory.remember`, `nexus.memory.answer`, `nexus.memory.benchmark.run`.
- [ ] H-MCP2 — Implement a thin local MCP wrapper only if core Qwen demo and benchmark report are already green.
- [ ] H-SKILL1 — Document reusable agent skills/workflows for ingesting memory, answering with evidence, detecting supersession, and running benchmarks.

### Post-Hackathon / Deferred Roadmap

- [ ] Integrity & Multi-Domain — T4 audit pass, standing reports, `sec_filing_v1`, `scientific_paper_v1`, `literary_narrative_v1`, pack inheritance, cross-domain capsule linking, optional `spans` → `segments` rename.
- [ ] Cost & Multimodal — T1 local stack beyond Qwen candidates, cost dashboard, multimodal T1, numeric chart extraction guard.
- [ ] Eval & Observability Hardening — per-pack gold sets, 20-source test sets, T2 judge calibration sets, object-level eval dashboard.

### Post-Hackathon / Legacy Phase 4 — Brief Synthesis + Query Answering

- [ ] T3 model wiring — synthesis uses the configured Qwen Cloud T3 model from the domain pack/model tier map.
- [ ] POST /briefs/generate — daily/weekly/query briefs from semantic capsules/theses with evidence citations.
- [ ] POST /query — grounded answer endpoint over capsule evidence chains, with confidence and citations.
- [ ] Re-extraction sweep — background job to retry documents in `extraction_partial`/`extraction_failed`.

### Ongoing

- [ ] **CLI `asyncio.run()` event-loop footgun** (from PR #24 review) — `app/cli/capsules.py::backfill`, `app/cli/theses.py::synthesize`, and `app/cli/artefacts.py::create` all use bare `asyncio.run()` instead of `app/cli/main.py::_run()` (which exists specifically because `asyncio.run()` raises `RuntimeError` when a framework like pytest-asyncio already owns the event loop). Any future `@pytest.mark.asyncio` e2e test invoking one of these commands against a real DB will fail. Fix all three uniformly (extract `_run()` to a shared helper if `app/cli/main.py` importing from the subcommand modules creates a circular import) — not scoped to the two Phase C remainder commands alone, since `capsules.py` has the identical pattern already.
  Reference: `app/cli/capsules.py:62`, `app/cli/theses.py:50`, `app/cli/artefacts.py:72`, `app/cli/main.py::_run`.
- [ ] **Phase C remainder P2 test gaps** (from `docs/test-plan-phase-c-remainder.md`, deferred non-blocking):
  - GAP-5 — 3-capsule real-DB round-trip for `synthesize_theses_from_relations` (only the 2-capsule minimum is covered in `tests/intelligence/test_reasoning_layer_db.py`; the 3-capsule chain is covered by a mocked-session test only).
  - GAP-7 — `nexus artefacts create` has no DB integration test (only the pure `build_decision_artefact_row` unit tests and a CLI `--help`/bad-UUID smoke test).
  - GAP-8 — `classify_relations` "none"-classification-writes-no-row has unit coverage (`test_relation_classification.py`) but no real-DB integration test.
  - `--min-strength` on `nexus theses synthesize` and `--capsule-id`/`--thesis-id` count limits on `nexus artefacts create` have no range/sanity validation (e.g. `--min-strength 1.5` is silently accepted, just matches nothing).
- [ ] HTTP Basic Auth / API key middleware (security gap, open since Phase 1)
- [ ] Chat security F1 — multi-turn prompt injection: wrap user messages with untrusted-input marker in agent prompt; plan Llama Guard guardrail pass post-auth (see `docs/security-review-chat-sessions.md`)
- [ ] Chat security F4 — rate limiting + session/message caps + move `checkpointer.setup()` to lifespan (`slowapi`, `MAX_SESSIONS`, `MAX_MESSAGES_PER_SESSION`)
- [ ] Chat security F5 — pre-shared `X-API-Key` guard on all session endpoints before public exposure
- [ ] Chat security F6 — strip non-printable chars from `_derive_title`; frontend must HTML-escape title field
- [ ] Chat security F8 — move `checkpointer.setup()` to application lifespan handler (DDL on every request)
- [ ] Chat security F10 — add `CHECK (role IN ('user', 'assistant'))` constraint in a future migration
- [ ] Shared httpx.AsyncClient via lifespan (currently created per-request in ingestion)
- [ ] Populate `docs/iterations/active/` with execution logs
- [ ] Record durable workflow lessons in `docs/insights.md` as they appear.
- [ ] `nexus document <id>` CLI command — show extracted claims inline (deferred from Phase 2.5)
- [ ] `nexus extract <doc_id>` CLI command — trigger extraction from the CLI
- [ ] **Fix mypy pre-commit hook** — add `types-PyYAML` to `additional_dependencies` in `.pre-commit-config.yaml` so the hook's isolated env resolves the `yaml` stubs; eliminates the false failure on `app/evaluation/*.py` every session.
  Reference: `.pre-commit-config.yaml`, mypy hook, `language: system` → `language: python` or add `additional_dependencies: [types-PyYAML]`
- [ ] **Session-start hook for PostgreSQL** — add a Claude Code `SessionStart` hook that runs `service postgresql start` so integration tests work immediately without manual intervention each session.
  Reference: `.claude/settings.json` hooks, `session-start-hook` skill
- [ ] **CORS origins via env var** — `app/main.py` hardcodes `localhost:5173`; add a `CORS_ORIGINS` setting to `app/config.py` so staging/production origins can be configured without code changes.
- [ ] **Fix `/security-review` skill for remote envs** — skill calls `git log origin/HEAD..HEAD` which fails when `origin/HEAD` is unset. Should fall back to `git merge-base origin/main HEAD` or accept a base ref arg.
- [ ] **doc-updater field-name guard** — after doc-updater runs, grep curl examples in `docs/` against actual Pydantic field names to catch cross-endpoint contamination (e.g. `content` vs `question`) before commit.

## Observability — Deferred

- [ ] **LangSmith tracing** — Integrate LangSmith for LLM-side tracing (env-gated via
  `LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_API_KEY`). Wire `LangSmith` callbacks into
  `LLMClient.complete_json` alongside the existing `tracer.record_agent_run` call.
  Reference: `app/intelligence/llm_client.py::LLMClient.complete_json`.

- [ ] **Full CLI UX** — Rich progress bars during `nexus ingest` and `nexus extract`,
  color-coded log levels, `nexus status --live` auto-refresh dashboard.
  Reference: `app/cli/main.py`, `app/cli/render.py`.

- [ ] **FastAPI request_id middleware** — Assign a per-request UUID via `contextvars`,
  bind to log records, return as `X-Request-ID` response header.
  Reference: `app/main.py`.

- [ ] **`_chunk_and_embed` failure status** — Wrap `_chunk_and_embed` in try/except;
  set `doc.status = "chunk_failed"` or `"embed_failed"` and log the exception.
  Currently documents silently get stuck at `fetched` or `chunked`.
  Reference: `app/api/routes_ingestion.py::_chunk_and_embed`.

- [ ] **RSS entry-fetch drop logging** — Replace `except Exception: return None` in
  `_resolve_entry` with logging + a `dropped` counter surfaced in `IngestResult`.
  Reference: `app/ingestion/rss.py:61`.

- [ ] **File-sink option + `nexus logs tail`** — Add `LOG_FILE` env var support writing
  to `logs/nexus.jsonl`; add `nexus logs tail [--follow] [--run-id X]` CLI command.
  Reference: `app/observability/logger.py`.

- [ ] **Input/output token cost split** — Currently `_COST_PER_TOKEN_USD` applies a
  blended rate to `total_tokens`. OpenRouter bills input/output at different rates.
  Update `record_agent_run` to compute cost from `prompt_tokens` × input_rate +
  `completion_tokens` × output_rate, configurable via `app/config.py`.
  Reference: `app/observability/tracer.py::record_agent_run`.

## Eval Framework — Technical Debt

- [ ] **CLI plumbing consolidation** — `eval.py` re-implements `_require_db_url` (with scheme validation), `_get_session_factory`, and the `CLISettings` boilerplate 5×. Move the scheme-aware `_require_db_url` into `app/cli/main.py` (or `app/cli/_common.py`) and reuse `_with_session` from `app/cli/db.py` so engines are disposed. Also consolidate the `asyncio.run(...)` calls to use the existing `_run()` helper from `main.py`.
  Reference: `app/cli/eval.py:29-51`, `app/cli/main.py:69-115`, `app/cli/db.py:16-24`.

- [ ] **render.py reuse** — eval CLI uses inline `typer.echo(json.dumps(...))` and ad-hoc Rich `Table` construction in 5 commands. Move to `app/cli/render.py` (e.g. `render_eval_run`, `render_eval_diff`, `render_eval_datasets`, `render_eval_calibration`) matching the pattern of `render_runs_list`. Also replace manual `.isoformat()` / `float()` casts with `_to_jsonable()` from `render.py`.
  Reference: `app/cli/eval.py:131-142`, `app/cli/render.py`.

## Eval Framework — Deferred

- [ ] **Activate BriefSynthesisJudge** — remove `NotImplementedError`; wire Phase-4 brief
  synthesis rubric once `POST /briefs/generate` ships.
  Reference: `app/evaluation/judges.py::BriefSynthesisJudge`.

- [ ] **Activate GroundedAnswerJudge** — wire Phase-4 grounded answer rubric once
  `POST /query` ships.
  Reference: `app/evaluation/judges.py::GroundedAnswerJudge`.

- [ ] **SpanRetrievalJudge** — implement the LLM-judged relevance layer (graded 0–3)
  for span retrieval; currently only text-overlap alignment exists.
  Reference: `app/evaluation/judges.py`, `app/evaluation/runner.py`.

- [ ] **Extend human_labels to ≥50 pairs** — current seed has 6; κ estimate unreliable
  below 30 pairs. Run `nexus eval calibrate claim_extraction` after extending.
  Reference: `evals/human_labels/claim_extraction.yaml`.

- [ ] **Baseline run** — after manual corpus ingestion, run `nexus eval run claim_extraction ai_tech_v1`
  and record the run_id in `docs/insights.md` as the v1 baseline reference.

- [ ] **Statistical significance** — add bootstrap CIs on aggregate scores across runs.

- [ ] **Multi-judge ensembling** — run 2+ judge models, majority-vote verdicts.

- [ ] **Dashboard** — web UI over `eval_runs` + `eval_results` for cross-run visualization.
