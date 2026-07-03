# TODO

## Hackathon Critical Path — Qwen Cloud MemoryAgent (deadline 2026-07-09 5pm EDT)

> Submission target: Devpost Qwen Cloud Hackathon, Track 1 MemoryAgent. For the hackathon branch, optimize for a working Qwen-powered memory demo, benchmark report, and submission package. Defer broad roadmap items that do not strengthen the MemoryAgent story within one week.

- [X] H0 — Register/verify Qwen Cloud access, API key, voucher credits, and model availability from the deployment environment.
- [x] H1 — Route **T2 and above** through Qwen Cloud / Model Studio models; keep model names configurable by environment and domain pack. (PR #25 D3/G4)
- [x] H2 — Produce a MemoryAgent demo script: ingest AI-tech memory stream → extract capsules → relate/consolidate → supersede stale memory → answer with citations → show benchmark report. (PR #25; `scripts/benchmarks/demo_answer.py` + `nexus eval memory run`)
- [ ] H3 — Add submission docs/assets: ~~README demo walkthrough~~ (done, PR #25), architecture diagram, benchmark screenshot/report, demo video outline, Devpost project narrative.
- [ ] H4 — Treat MCP integrations and repo skills as final-version improvements: document tool contracts now; implement only a thin MCP server/tool wrapper if it does not endanger the core demo.
- [ ] H5 — Implement a Qwen memory query router before the next benchmark pass: classify each incoming question (timeline/factoid vs. multi-doc vs. supersession vs. abstention) and dispatch to a retrieval/answer strategy tuned for that shape, instead of one fixed chat-graph path for every question. Candidate fix for the weak timeline/factoid-recall category — see the Phase F follow-up below.
  Spec: `docs/superpowers/specs/2026-07-03-query-router.md`. Plan: `docs/superpowers/plans/2026-07-03-query-router.md`.
  - [x] T-R1 — `app/intelligence/router.py` (shapes + `RetrievalStrategy` table + `resolve_strategy`) wired through `classify_intent`/`retrieve_capsules`/`generate_answer`; single shared T2 classify call returns intent + shape; unit tests. (Grok implementer; 513 passed / 6 pre-existing failures — the pre-existing set on this Linux env is `test_loader.py::test_absolute_path_raises_file_not_found` + `test_chat_api.py::test_chat_answer_graph_error_state_returns_service_unavailable` + the 4 known extraction/dual-write mock failures, all confirmed failing on clean main.)
  - [x] T-R2 — Live benchmark validation on scratch DB: **all gates pass** — timeline 0.333→1.000 (temporal_correctness 0.25→1.00), overall answer_correctness 0.568→0.678, evidence_recall 0.407→0.491, faithfulness 1.000, forbidden 0.000, abstention 0.864. No strategy tuning needed. authority_conflict 0.333→0.250 (single-question shift on n=3, noted below). Run: `docs/benchmarks/runs/router-t-r2/`.
  - Env note: first T-R2 attempt 401'd on every LLM call — this machine's `.env` had `QWEN_CLOUD_API_KEY` but no `LLM_BASE_URL`, so calls defaulted to OpenRouter. Added `LLM_BASE_URL` to `.env` (matches `.env.example`).
  - [ ] Router follow-up (PR #26 review) — surface `question_shape` per-question in the benchmark `results.jsonl` (the chat graph already returns it in final state; the runner just doesn't record it) so shape-routing accuracy can be audited; revisit the `conflict`/`current_state` routing if `authority_conflict`/`supersession_correctness` stay flat on the next pass.

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
- [ ] **Cross-document relation pass (baseline top follow-up)** — `classify_relations` only pairs capsules within one document; explicit cross-doc `supersedes`/`contradicts` edges are never created (the lifecycle facet heuristic partially compensates for supersession). Add a domain-wide relation pass (batch by object_family/actor across docs). See `docs/benchmarks/baseline-2026-07-02.md`.
- [ ] **Timeline/factoid-recall category is the weakest benchmark score** (0.25–0.5 across runs) — likely an embedding-recall or prompt issue for single-fact date lookups, not a lifecycle bug (the underlying capsule is `active`). Investigate retrieval for short factoid queries. Candidate fix: the query router (H5, above).
- [ ] Stretch after baseline — LoCoMo/LongMemEval download + conversion adapters; BEAM/Memora adapters remain post-hackathon unless the core demo is already complete.

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
