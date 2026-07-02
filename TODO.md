# TODO

## Future

### Phase C — Reasoning Layer (remaining)

> Spec: `docs/superpowers/specs/2026-07-02-phase-c-remainder-design.md`. Plan: `docs/superpowers/plans/2026-07-02-phase-c-remainder.md`. Migration `0005_semantic_capsules.py` records `theses`/`decision_artefacts` as "written first by Phase E" — both writers below ship as standalone functions + CLI commands this PR, with no automatic trigger; Phase E owns triggering.

- [x] C3a — `app/intelligence/theses.py`: `build_thesis_row` + `synthesize_theses_from_relations` (union-find clustering over `semantic_relations`) + unit tests. (`c51ddea`)
- [x] C3b — `app/cli/theses.py`: `nexus theses synthesize` command + CLI smoke test. (`a0ffafe`)
- [x] C4a — `app/intelligence/decision_artefacts.py`: `build_decision_artefact_row` + unit tests. (`a4ff9e4`)
- [x] C4b — `app/cli/artefacts.py`: `nexus artefacts create` command + CLI smoke test. (`a0ffafe`)
- [x] C5 — DB-bound integration tests (`tests/intelligence/test_reasoning_layer_db.py`, `@pytest.mark.slow`, real Postgres) for `judge_capsules`, `classify_relations`, and the C3a→C5 round-trip. (`5199516`)

### Phase D — Retrieval & UI Over Meaning (residual)

> Core cutover landed in PR #21; token-budget context assembly + evidence-path UI landed in PR #22 (archived: `docs/iterations/archive/2026-06-12-phase-d-retrieval-ui.md`). Remaining (Phase-E-gated):

- [ ] Context assembly `include` categories + `ordering: evidence_strength` — drive block *selection/ordering* from `pack.context_assembly` (token budget already enforced via `max_tokens_by_tier`; the `include` categories — counter-evidence, superseding/superseded, epistemic notes — and evidence-strength ordering need the relation graph / lifecycle / evidence-quality signals).
- [ ] Drop `claims` + `claim_evidence` tables (only after `/chat/answer` cutover is green for 1 week).
- [ ] Un-stub hybrid scoring inputs — `source_authority` (uniform 0.5), `relation_relevance` (0.0), `evidence_quality` (0.0) once Phase E relation-graph / source-authority signals exist.

### Phase E — Living Knowledge

- [ ] Lifecycle worker — capsule state transitions (candidate → active → confirmed/qualified/superseded/stale/archived/rejected) driven by `pack.retention_policy` + `epistemic_policy`.
- [ ] Consolidation worker — many capsules → thesis / narrative arc / research model / company risk model.
- [ ] Stale / superseded detection — `pack.retention_policy.stale_conditions` + `supersession_rules`.

### Phase F — Benchmarking Agentic Memory

> Nexus is an agentic memory system; Phase F should establish benchmark harnesses and repeatable evaluation scripts before expanding integrity/multi-domain work.

- [ ] Benchmark survey note — document selected external memory/RAG benchmarks and mapping to Nexus capabilities:
  - LoCoMo / LOCOMO — long-term conversational memory; single-hop, multi-hop, temporal, adversarial QA, event summarization, multimodal dialogue.
  - LongMemEval — long-term chat-assistant memory; information extraction, temporal reasoning, multi-session reasoning, abstention/unanswerable behavior.
  - BEAM — long-scale conversational memory stress tests across 128K/500K/1M+ token histories; useful as stretch benchmark after local harness exists.
  - Memora — personalized-agent long-term memory over weeks/months; preference/user-memory and forgetting/supersession behavior.
  - RAG/multi-hop baselines — HotpotQA, MuSiQue, 2WikiMultiHopQA-style retrieval/grounded-answer tests adapted to capsule evidence chains.
- [ ] Add benchmark dataset layout under `evals/memory/`:
  - `evals/memory/locomo/` for downloaded/converted LoCoMo conversations and QA.
  - `evals/memory/longmemeval/` for LongMemEval-style sessions/questions.
  - `evals/memory/nexus_synthetic/` for Nexus-native domain-pack memory probes.
  - `evals/memory/README.md` documenting licensing/source URLs, conversion steps, and dataset checksums.
- [ ] Add benchmark runner scripts under `scripts/benchmarks/`:
  - `download_memory_benchmarks.py` — fetch or verify external benchmark files without committing large raw datasets.
  - `convert_locomo.py` — convert LoCoMo conversations/questions into Nexus source/doc/span ingestion fixtures.
  - `convert_longmemeval.py` — convert LongMemEval sessions/questions into Nexus benchmark fixtures.
  - `run_memory_benchmark.py` — ingest fixture corpus, run Nexus retrieval/chat answers, score outputs, and emit JSONL/Markdown reports.
- [ ] Add benchmark CLI surface, e.g. `nexus eval memory ...`, reusing the existing evaluation framework where practical:
  - `nexus eval memory prepare --benchmark locomo|longmemeval|nexus_synthetic`
  - `nexus eval memory run --benchmark <name> --split <split> --k <n>`
  - `nexus eval memory report --run-id <id>`
- [ ] Define scoring metrics for agentic memory:
  - answer exact/semantic correctness via judge + deterministic aliases where available.
  - evidence recall@k / precision@k over cited spans/capsules.
  - multi-hop support coverage: all required supporting memories retrieved and cited.
  - temporal ordering accuracy for time-sensitive questions.
  - abstention accuracy for unanswerable/adversarial questions.
  - freshness/supersession correctness once Phase E lifecycle states exist.
  - latency, token cost, and DB/query cost per benchmark example.
- [ ] Add Nexus-native benchmark fixtures for the actual product domain:
  - AI release timeline memory questions.
  - multi-document benchmark/result comparison questions.
  - superseded/stale claim questions.
  - source-authority conflict questions.
  - thesis/consolidation questions once Phase C/E writers exist.
- [ ] Add baseline report artifacts under `docs/benchmarks/`:
  - `docs/benchmarks/memory-benchmark-plan.md`
  - `docs/benchmarks/baseline-template.md`
  - first baseline run report after harness lands.

### Phase G — Integrity & Multi-Domain

- [ ] T4 audit pass — integrity checks; contradiction-as-mystery-thread for narrative packs.
- [ ] Four standing reports (per v0.7) — coverage, contradiction, freshness, cost.
- [ ] `sec_filing_v1` pack.
- [ ] `scientific_paper_v1` pack.
- [ ] `literary_narrative_v1` pack.
- [ ] Pack inheritance resolution — implement `inherits_from` in the YAML loader; first consumer of the `domain_packs.parent_pack_id` column added in B1.
- [ ] Cross-domain capsule linking — capsules from different domains referenced by the same thesis.
- [ ] Optional `spans` → `segments` table rename (Phase B deferred this).

### Phase H — Cost & Multimodal

- [ ] T1 local stack — GLiNER2 + bge-small + DeBERTa-v3-xsmall + Qwen2.5-0.5B per v0.7 §11.2.
- [ ] T1 candidate-capsule prompt + route-to-T2 gating.
- [ ] Cost dashboard — per-tier / per-pack spend, ratio of T1-only vs T2-escalated.
- [ ] Multimodal at T1 — image / table / chart segments.
- [ ] Numeric chart extraction guard — Phase A guarded against this implicitly; codify as a T0 rule.

### Phase I — Eval & Observability Hardening

- [ ] Per-pack evaluation gold sets — extend `evals/gold/semantic_objects/` with one fixture per pack (matches `ai_tech_v3.yaml` shape).
- [ ] 20-source test sets per domain pack.
- [ ] Calibration sets for the T2 judge.
- [ ] Object-level eval dashboard (HTML or web UI over `eval_runs` + `eval_results`).

### Phase 4 — Brief Synthesis + Query Answering

- [ ] T3 model wiring — synthesis uses the strong OpenRouter model from domain pack
- [ ] POST /briefs/generate — daily/weekly/query briefs from extracted claims
- [ ] POST /query — grounded answer over claims + spans, with confidence and citations
- [ ] Re-extraction sweep — background job to retry documents in `extraction_partial`/`extraction_failed`

### Ongoing

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
