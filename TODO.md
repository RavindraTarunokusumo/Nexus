# TODO

## Hackathon Critical Path — Qwen Cloud MemoryAgent (deadline 2026-07-09 5pm EDT)

> Submission target: Devpost Qwen Cloud Hackathon, Track 1 MemoryAgent. For the hackathon branch, optimize for a working Qwen-powered memory demo, benchmark report, and submission package. Defer broad roadmap items that do not strengthen the MemoryAgent story within one week.

- [ ] H0 — Register/verify Qwen Cloud access, API key, voucher credits, and model availability from the deployment environment.
- [ ] H1 — Route **T2 and above** through Qwen Cloud / Model Studio models; keep model names configurable by environment and domain pack.
- [ ] H2 — Produce a MemoryAgent demo script: ingest AI-tech memory stream → extract capsules → relate/consolidate → supersede stale memory → answer with citations → show benchmark report.
- [ ] H3 — Add submission docs/assets: README hackathon section, architecture diagram, benchmark screenshot/report, demo video outline, Devpost project narrative.
- [ ] H4 — Treat MCP integrations and repo skills as final-version improvements: document tool contracts now; implement only a thin MCP server/tool wrapper if it does not endanger the core demo.

### Phase C — Reasoning Layer (hackathon required)

> Spec: `docs/superpowers/specs/2026-07-02-phase-c-remainder-design.md`. Plan: `docs/superpowers/plans/2026-07-02-phase-c-remainder.md`. Migration `0005_semantic_capsules.py` records `theses`/`decision_artefacts` as "written first by Phase E" — both writers below ship as standalone functions + CLI commands this PR, with no automatic trigger; Phase E owns triggering.

- [x] C3a — `app/intelligence/theses.py`: `build_thesis_row` + `synthesize_theses_from_relations` (union-find clustering over `semantic_relations`) + unit tests. (`c51ddea`)
- [x] C3b — `app/cli/theses.py`: `nexus theses synthesize` command + CLI smoke test. (`a0ffafe`)
- [x] C4a — `app/intelligence/decision_artefacts.py`: `build_decision_artefact_row` + unit tests. (`a4ff9e4`)
- [x] C4b — `app/cli/artefacts.py`: `nexus artefacts create` command + CLI smoke test. (`a0ffafe`)
- [x] C5 — DB-bound integration tests (`tests/intelligence/test_reasoning_layer_db.py`, `@pytest.mark.slow`, real Postgres) for `judge_capsules`, `classify_relations`, and the C3a→C5 round-trip. (`5199516`)

### Phase D — Retrieval & Qwen Context Assembly (hackathon required)

> Keep only retrieval improvements that visibly improve MemoryAgent quality. Defer schema cutovers and cleanup until after Devpost submission.

- [ ] D1 — Context assembly `include` categories + `ordering: evidence_strength` for supporting evidence, counter-evidence, superseding/superseded memories, and epistemic notes.
- [ ] D2 — Un-stub hackathon-critical hybrid scoring inputs: `source_authority`, `relation_relevance`, and `evidence_quality`; acceptable first version may use deterministic relation/source/lifecycle heuristics.
- [ ] D3 — Ensure chat/synthesis answer generation uses a Qwen T2+ model and reports citations/evidence chain in the demo path.
- [ ] Deferred after hackathon — Drop `claims` + `claim_evidence` tables only after `/chat/answer` cutover is green for 1 week.

### Phase E — Living Knowledge (hackathon MVP)

- [ ] E1 — Minimal lifecycle worker: active → confirmed/qualified/superseded/stale/archived based on relation/lifecycle heuristics sufficient for demo and benchmarks.
- [ ] E2 — Stale/superseded detection for benchmark/demo fixtures using `pack.retention_policy.stale_conditions` + `supersession_rules` where available.
- [ ] E3 — Consolidation worker minimal path: many capsules → thesis / narrative arc / research model using the Phase C thesis writer.

### Phase F — Benchmarking Agentic Memory (hackathon required)

> Build a small but repeatable benchmark first. External benchmark adapters are stretch; Nexus-native synthetic memory probes are required for the one-week submission.

- [ ] F1 — Benchmark survey note mapping LoCoMo, LongMemEval, BEAM, Memora, and RAG/multi-hop baselines to Nexus capabilities; explicitly cite what is implemented now vs stretch.
- [ ] F2 — Add `evals/memory/nexus_synthetic/` fixtures for the demo domain:
  - AI release timeline memory questions.
  - multi-document benchmark/result comparison questions.
  - superseded/stale claim questions.
  - source-authority conflict questions.
  - thesis/consolidation questions.
  - abstention/unanswerable questions.
- [ ] F3 — Add benchmark runner script `scripts/benchmarks/run_memory_benchmark.py` to ingest fixture corpus, run Nexus retrieval/chat answers, score outputs, and emit JSONL/Markdown reports.
- [ ] F4 — Add benchmark CLI surface only if fast to wire: `nexus eval memory run --benchmark nexus_synthetic --k <n>` and `nexus eval memory report --run-id <id>`.
- [ ] F5 — Define and report hackathon metrics: answer correctness, evidence recall@k, citation faithfulness, temporal correctness, supersession correctness, abstention accuracy, latency, token cost.
- [ ] F6 — Add baseline report artifacts under `docs/benchmarks/`: `memory-benchmark-plan.md`, `baseline-template.md`, and first baseline run report.
- [ ] Stretch after baseline — LoCoMo/LongMemEval download + conversion adapters; BEAM/Memora adapters remain post-hackathon unless the core demo is already complete.

### Phase G — Qwen Model Tiering (hackathon required)

> T2 and above must be Qwen-based for submission. Also scout/validate whether Qwen can cover T0/T1 so the whole stack can be presented as Qwen-native.

- [ ] G1 — Add configurable model tier map and document chosen defaults:
  - T0 candidate — `Qwen3-Embedding-0.6B` locally or Model Studio `text-embedding-v4` for embeddings; Qwen3 Embedding supports 0.6B/4B/8B, 32K sequence length, instruction-aware embeddings, MRL dimensions, multilingual/code retrieval.
  - T1 candidate — `Qwen3-Reranker-0.6B` locally or Model Studio `qwen3-rerank` for cheap relevance scoring/reranking; consider `qwen3.6-flash`/turbo-class Qwen model for lightweight classification if available in account.
  - T2 candidate — `qwen3.7-plus` or `qwen3.6-flash` for semantic extraction, judging, relation classification, and routine chat answers.
  - T3 candidate — `qwen3.7-max` or strongest available Qwen reasoning model for synthesis, thesis writing, decision artefacts, and benchmark judge passes.
  - T4 candidate — `qwen3.7-max` / Qwen Max-class model for audit, contradiction, high-confidence adjudication, and final benchmark judge.
- [ ] G2 — Verify exact Qwen Cloud model IDs, pricing/limits, context windows, and OpenAI-compatible base URL in the active account before implementation hard-codes names.
- [ ] G3 — Add environment examples for Qwen Cloud: base URL, API key variable, and tier-to-model overrides.
- [ ] G4 — Update domain pack/model config so T2+ paths no longer default to non-Qwen models for the hackathon submission.

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
- [ ] **Fix `capsule_segments.role="support"` CHECK violation** — `build_capsule_row` (`app/intelligence/capsules.py`) writes `role="support"`, but migration `0005_semantic_capsules.py`'s `ck_capsule_segments_role` CHECK only allows `"supports"` (plural) among `("grounds", "supports", "contradicts", "qualifies", "refines", "exemplifies", "other")`. Breaks `nexus capsules backfill` and the extraction dual-write path against a real Postgres (confirmed on clean `main` @ `91b16c1`, unrelated to the Phase C remainder PR — discovered while running the full test suite against a real DB for that PR's Task 5). 6 tests fail: `tests/intelligence/test_capsule_backfill.py::test_backfill_idempotent`, `::test_backfill_multi_source_ref`, `tests/intelligence/test_capsules_dual_write.py::test_happy_path_single_object`, `::test_multi_source_refs`, `::test_transaction_atomicity`, `::test_embedding_present`. All 4 are unit tests with a mocked DB session, so they never caught this — only a real-DB run surfaces it.
  Reference: `app/intelligence/capsules.py::build_capsule_row`, `app/db/migrations/versions/0005_semantic_capsules.py::_SEGMENT_ROLES`.
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
