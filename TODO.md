# TODO

## Active

### Phase B — Semantic Capsule Schema (follow-up to Phase A)

Phase A landed the telos-aware extraction + projection bridge (see [archive](docs/iterations/archive/2026-05-30-phase-a-telos-semantic-bridge.md)). Phase B promotes the in-memory `SemanticObject` layer to durable tables and retires the legacy dual-path eval contract.

- [ ] **B1** — Alembic migration 0005: `semantic_capsules`, `capsule_segments`, `semantic_relations`, `theses`, `decision_artefacts` tables per `nexus_poc_v07_telos_semantic.md` §7.1.
- [ ] **B2** — Dual-write from `projection.project()`: write a capsule (+ `capsule_segments`) alongside the projected `Claim` row.
- [ ] **B3** — Backfill capsules from existing rows via the `entities_json["_v0_7"]` payload stash.
- [ ] **B4** — Port `app/evaluation/runner.py` to `SemanticExtractionOutput` + an object-level eval gold set. Retire `ExtractedClaim` / `ExtractionOutput`.
- [ ] **B5** — Wire the A7 T2 judge prompt into the graph behind a feature flag, writing escalations to `semantic_relations` (or a new audit table).
- [ ] **B6** — Capsule retrieval + telos-aware hybrid scoring driven by `pack.retrieval_policy.hybrid_score_weights` + query-intent classification.
- [ ] **B7** — Lifecycle / consolidation workers: capsule states (candidate → active → confirmed/qualified/superseded/stale/archived); thesis / narrative-arc / research-model synthesis.
- [ ] **B8** — Ingestion-side detection of v3 source-type profile (replace `pack.metadata.supported_source_types[0]` fallback in `_resolve_pack_and_source_type`).

### Phase A — follow-up unit-test gap

- [ ] Isolated unit test for `_resolve_pack_and_source_type` (currently covered only end-to-end). Test plan flagged in `docs/test-plan-phase-a-telos-semantic.md`.

### Phase 2 validation harness

- [ ] Create and run a destructive CLI validation script that resets local data and exercises text, RSS, status, document inspection, and semantic search paths.

## Future

### Phase 4 — Brief Synthesis + Query Answering

- [ ] T3 model wiring — synthesis uses the strong OpenRouter model from domain pack
- [ ] POST /briefs/generate — daily/weekly/query briefs from extracted claims
- [ ] POST /query — grounded answer over claims + spans, with confidence and citations
- [ ] Re-extraction sweep — background job to retry documents in `extraction_partial`/`extraction_failed`

### Ongoing

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
