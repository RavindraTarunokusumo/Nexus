# TODO

## Hackathon Critical Path — Qwen Cloud MemoryAgent (deadline 2026-07-09 5pm EDT)

> Submission target: Devpost Qwen Cloud Hackathon, Track 1 MemoryAgent. For the hackathon branch, optimize for a working Qwen-powered memory demo, benchmark report, and submission package. Defer broad roadmap items that do not strengthen the MemoryAgent story within one week.

- [ ] **H7 — External benchmark run for empirical demonstration (TOP PRIORITY, user-directed 2026-07-03).** The synthetic benchmark proves the pipeline but carries no external credibility; the submission needs a recognized dataset with published comparison numbers.
  - **Primary: LongMemEval** ([GitHub](https://github.com/xiaowu0162/LongMemEval), ICLR 2025; cleaned JSON on [HuggingFace](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned), `huggingface-cli download xiaowu0162/longmemeval-cleaned`). 500 instances; its `knowledge-update` and `temporal-reasoning` categories map 1:1 onto Nexus supersession/lifecycle and timeline strengths. Published numbers exist for comparison (SOTA memory systems report ~94; see [mem0's 2026 benchmark survey](https://mem0.ai/blog/ai-memory-benchmarks-in-2026)). Adapter: treat each history session as an ingested document (session timestamp → `published_at`, so the cross-doc pass and lifecycle work unmodified), reuse the `run_memory_benchmark` pipeline + `scoring.py`; add the paper's QA-accuracy judge for comparability. Start with a stratified subset (e.g. all knowledge-update + temporal-reasoning questions) if the full 500 is too slow/costly on T2.
  - **Secondary (stretch): LoCoMo** (1,540 questions over 10 long conversations; single-hop/multi-hop/temporal categories) — conversational rather than document memory, so the adapter is less natural; only if LongMemEval lands fast. [LongMemEval-V2](https://arxiv.org/html/2605.12493v1) and [AMB](https://agentmemorybenchmark.ai/) noted as post-hackathon candidates; BEAM (1M–10M tokens) out of scope for the deadline.
  - Deliverable: `evals/memory/longmemeval/` adapter + a baseline report under `docs/benchmarks/` with per-category Nexus scores next to published reference numbers → feeds directly into H3's benchmark asset.
  Spec: `docs/superpowers/specs/2026-07-03-longmemeval-adapter.md`. Plan: `docs/superpowers/plans/2026-07-03-longmemeval-adapter.md`.
  - [x] T-L1 — `scripts/benchmarks/run_longmemeval.py` adapter (session→document mapping, per-instance DB truncation, full pipeline, T3 QA judge per the official protocol, `hypotheses.jsonl` for the official scorer) + 13 pure-helper unit tests + dataset README/.gitignore. (Grok implementer; 550 passed / 6 pre-existing; date parser verified against the real `2023/04/10 (Mon) 23:07` format.)
  - [x] T-L2 — Run 1 complete: 0/20 (all abstentions) — pack-mismatch CONFIRMED (9/20 instances zero capsules, 31/43 docs empty; surviving capsules tech-adjacent, not the queried personal facts). Architecture ran end-to-end correctly; the number measures the pack. Run: `docs/benchmarks/runs/longmemeval-t-l2/`. Also found: dataset order not category-interleaved (slice was 100% temporal-reasoning).
  - [x] T-L3 — `conversation_v1` domain pack (7 families, user-as-protagonist `people:['user']` facet guidance, personal-state supersession, Qwen ids + no-deepseek regression test) + adapter `--pack` flag threaded via `Source.domain_pack`. (Grok implementer; 557 passed / 6 pre-existing.)
  - [x] T-L4/T-L5d — Full-211 before/after complete: overall 0.355→0.709, KU 0.587→0.747, TR 0.219→0.688, abstentions 101→29 (matched pairs, n=203). Report: `docs/benchmarks/longmemeval-2026-07-04.md`; final run 34 min at 6 workers.
  - [ ] T-L5 — Answer-path temporal grounding + conflict resolution (spec amendment 2026-07-04; full-211 partial showed TR 0.224 with 74 abstentions despite full retrieval — answer path is time-blind).
    - [x] T-L5a (`8d91038`) — `as_of` question-time anchor through `run_chat_with_context` → chat state → `build_user_prompt` (`Current date:` line); `Document.published_at` selected in both capsule queries, copied onto context blocks, rendered as per-block `Date:` line; adapter passes `question_date`. Unit tests for prompt rendering.
    - [x] T-L5b (`d0a314f`) — `SYSTEM_PROMPT` conflict-resolution instruction (resolve via supersession/lifecycle/dates, single answer — never report "conflicting evidence"); `multi_doc` strategy `top_k_delta` 3→5 + enumerate-and-count hint.
    - [x] T-L5c (`4056ef9`) — `_judge_answer` retries once on LLM error before recording null.
    - [x] T-L5d — done via the full-211 final run (see T-L4 entry). Working 55-subset (`--limit 55`) remains the fast iteration loop (~10 min).
  - [x] T-L6 — Retrieval fixes for temporal reasoning (spec Amendment 2, user-approved 2026-07-04). R1/R3/R4 shipped; R2 attempted and reverted (see sub-item).
    - [x] R1 (`881cd67`) — `temporal` question shape: router strategy (top_k_delta=7, fetch_k 6, date-arithmetic hint) + classifier shape definition, narrowing `factoid`'s "when/what past events" wording.
    - [x] R3 (`881cd67`) — recency scoring uses `published_at` (fallback `created_at`) in `compute_hybrid_score` + min/max at call site.
    - [x] R4 — render span evidence excerpts (≤2/block, existing 280-char cap) in `build_user_prompt` — spans were retrieved but never shown to the answer model; targets failure Mode 1 (relative-date anchoring) via raw utterance + block Date. Held alternative: extraction-time date normalization in the pack.
    - [x] R2 (`bc8fe83`, reverted `ec1962a`) — sub-query union retrieval, implemented + full-suite validated, then 55-subset benchmark-validated: **regressed** 0.611→0.574 acc, abstain 5→8 (9 regressed/7 fixed) vs the T-L6+R4 baseline it targeted. Root cause: global rerank over the pooled candidates lets one comparandum's sub-query dominate the shared top-k and starve the other side — not a bug, a design flaw (pool-then-global-rerank). Reverted; corrected design (per-sub-query floor before shared rerank) logged in spec Amendment 2 as a future attempt, not reattempted now.
    - [x] Extraction-model matrix on 51 common ids (T-L5 fixes constant): baseline-pre-fixes 0.373 / qwen-flash 0.333 / qwen3.5-flash 0.353 / **qwen3.6-flash 0.431** → extraction stays qwen3.6-flash (per user rule, 3.5 does not hold); T-L5 answer fixes = +6pts de-confounded. Runs: `docs/benchmarks/runs/longmemeval-55-qwen3{5,6}flash/`. ~10 min per 55-question run at 6 workers.
- [ ] **H8-W — Rerun speed-up (user-directed 2026-07-04; spec amendment in `2026-07-03-inference-optimization.md`).** ~6h projected → target well under 1h via structure, not model swap (probe: fast tiers all ~1.3s/call).
  - [x] W1 (`a197466`) — Adapter `--workers N` + `--db-url-template`: round-robin instance sharding, per-worker engine/client/graphs on own scratch DB, lock-guarded partial appends, dataset-order results, `run_meta.workers`.
  - [x] W2 (`81ddfe5`, with W4) — Semaphore+gather (pattern of `extract_spans`) for `_run_classify_relations` pairs, `judge_capsules` loop, `classify_cross_document_relations` pairs; DB writes stay sequential post-gather.
  - [x] W3 (`0f56d2e`) — `LLMClient.complete_json` bounded retry (2 attempts, backoff+jitter) on 429/5xx/transient network only.
  - [x] W4 (`81ddfe5`, with W2 — shared extraction.py) — `t2_model_force` setting (env `T2_MODEL_FORCE`) overriding pack t2; rerun uses `qwen-flash` (live-verified); report must flag the extraction-model confound.

- [X] H0 — Register/verify Qwen Cloud access, API key, voucher credits, and model availability from the deployment environment.
- [x] H1 — Route **T2 and above** through Qwen Cloud / Model Studio models; keep model names configurable by environment and domain pack. (PR #25 D3/G4)
- [x] H2 — Produce a MemoryAgent demo script: ingest AI-tech memory stream → extract capsules → relate/consolidate → supersede stale memory → answer with citations → show benchmark report. (PR #25; `scripts/benchmarks/demo_answer.py` + `nexus eval memory run`)
- [ ] H3 — Add submission docs/assets: ~~README demo walkthrough~~ (done, PR #25), architecture diagram, benchmark screenshot/report, demo video outline, Devpost project narrative.
- [ ] H4 — Treat MCP integrations and repo skills as final-version improvements: document tool contracts now; implement only a thin MCP server/tool wrapper if it does not endanger the core demo.
- [x] H5 — Qwen memory query router. Complete: question-shape classification (factoid/multi_doc/current_state/conflict/general) in the shared T2 classify call, per-shape retrieval strategy + answer hints. Shipped in PR #26 (merge `5dff2b4`); timeline benchmark category 0.333→1.000, overall answer_correctness 0.568→0.678. Archived: `docs/iterations/archive/2026-07-03-router-h5.md`.
- [ ] H8 — Inference latency & token optimization (spec draft: `docs/superpowers/specs/2026-07-03-inference-optimization.md`; evidence: extraction = 81% of 2.13M tokens, serial round-trips dominate wall-clock). Quick wins pre-deadline if a session frees up: bounded concurrency for span/pair/question calls (3–5× wall-clock), per-task T2 routing to a turbo-class model for classification calls (G2-verify the id first), output-token caps. Medium: span batching, DashScope prefix caching, pre-extraction span filter, domain-scoped retrieval (also unlocks parallel benchmark instances). Future spec: T2 distillation — fine-tune a small Qwen on validated `agent_runs` traces (input/output already collected with downstream acceptance signals); pre-deadline scope is at most the trace-export tool, not the fine-tune.
  - [x] Q0 — Disable default qwen3 thinking mode in `complete_json` (`thinking: bool = False` param): live A/B showed identical outputs at 3.6× faster extraction (25.9s→7.1s) and 12× faster relation classification (13.0s→1.1s, completion 1,598→67 tokens). Diagnosed via `agent_runs` prompt/completion split (classification calls emitting ~20× their useful output).
- [ ] H6 — Demo UI console (plan agreed in-chat 2026-07-03; formal spec when the branch opens, after the cross-doc PR). Read-only three-tab console over the existing `web/` chat app: no auth, no live-refresh, no ingest-from-UI in v1.
  - [ ] T-U1 — Backend (no UI dependency): `GET /stats/overview` (entity counts, lifecycle histogram, `agent_runs` calls/tokens/cost by run_type × model); `GET /capsules/{id}/provenance` (document → spans → capsule → relations → thesis chain as structured JSON); additive `question_shape` + `query_intent` fields on chat answer responses (graph already returns them; routes don't surface them). Tests.
  - [ ] T-U2 — Frontend: tab shell (Dashboard | Chat | How it works, no router lib) + Dashboard (count cards, lifecycle distribution bar, model-usage table; latest-benchmark-scores card as stretch). Consumes T-U1.
  - [ ] T-U3 — Frontend: "How it works" Mermaid views — pipeline routing flowchart of the last answer (classify → strategy → retrieval → context blocks → answer, annotated with actual models/shape/values) and provenance chain view (click a citation or pick a capsule; lifecycle-state color coding, cross-doc supersedes/contradicts edges). Client-side `buildMermaid()` over the JSON payloads (server stays diagram-format-agnostic); new dep `mermaid`. Plus chat citation enrichment: role badges (primary/counter_evidence/supersession) + epistemic-note tooltip, "explain this answer" routing disclosure. T-U2/T-U3 parallelizable after T-U1.

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
- [ ] **Recency score input is ingestion order, not publication date** (T-X3 finding) — `compute_hybrid_score` recency normalizes capsule `created_at`; on a fresh DB that is corpus file order, noise. Use the document's published/date field where available. Ref `app/intelligence/chat.py::compute_hybrid_score`.
- [ ] **Cross-doc pair-attempt ledger/cursor** (PR #27 review, deferred) — pairs classified `none` are never recorded, so reruns re-send the same top-`max_pairs` LLM calls and tail pairs beyond the cap may never be reached. Persist negative attempts or rotate a cursor. Ref `app/intelligence/cross_relations.py`.
- [ ] **Extract a shared relation-persist helper** (crossdoc /simplify finding, deferred) — `cross_relations.py` duplicates ~25 lines of classify-and-persist (canonical/domain type split, row construction) from `extraction.py::_run_classify_relations`; the crossdoc spec constrained `extraction.py` to import-only, so dedup means a small shared module both import. Do it when `extraction.py` is next open for changes.
- [ ] **Transient extraction failure leaves a doc at `claims_extracted` with zero capsules** (T-X3 run-2 finding) — a `network_error` on one doc's `claim_extraction` silently produced an empty memory footprint while the status advanced, so the planned re-extraction sweep (which watches `extraction_partial`/`extraction_failed`) would never catch it. Needs a retry or a zero-capsule status check in the extraction graph. The benchmark runner now warns on zero-capsule docs. Ref `app/intelligence/extraction.py`.
- [x] ~~Timeline/factoid-recall category is the weakest benchmark score~~ — resolved by the H5 query router (PR #26): timeline answer_correctness 0.333→1.000, temporal_correctness 0.25→1.00.
- [ ] **Router follow-up (PR #26 review)** — surface `question_shape` per-question in the benchmark `results.jsonl` (the chat graph already returns it in final state; the runner just doesn't record it) so shape-routing accuracy can be audited; revisit the `conflict`/`current_state` routing if `authority_conflict`/`supersession_correctness` stay flat on the next pass (authority_conflict 0.333→0.250 on n=3 in the T-R2 run — single-question shift, watched).
- [ ] ~~Stretch after baseline — LoCoMo/LongMemEval adapters~~ — promoted to **H7** at the top of the hackathon critical path (user-directed 2026-07-03); BEAM/Memora remain post-hackathon.

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
