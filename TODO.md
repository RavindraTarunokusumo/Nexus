# TODO

## Active

### System-tuning follow-on (deferred from `feature/system-tuning`)

- [ ] **S3 multi-span provenance in real ingestion** — `ClaimEvidence` already
  supports many-to-one but `extraction.store_claims` writes only one row per
  claim. Extend the extractor to identify all supporting sentences and emit
  one `ClaimEvidence` row per supporting span.
- [ ] **S4 canonicalization on real claims** — wire `canonicalization.canonicalize()`
  and `supersede_check()` as a post-ingest hook or a periodic batch job. Depends
  on S3 to have meaningful multi-document data.
- [ ] **S9 temporal supersede on real claims** — verify `supersede_check()`
  selects the most-recent unsuperseded claim per canonical cluster. Needs
  real data with overlapping facts across timestamps.
- [ ] **Fine-tune GLiNER on v4 corpus** — train a head specifically for the
  24-way dotted taxonomy. Target: type accuracy 0.64 → 0.85+. Requires labeled
  training set (v4 + future v5), training infra, GPU.
- [ ] **Cross-family Claude human-labels for judge calibration** — script
  already exists at `scripts/opus_label_pairs.py` but Anthropic is blocked at
  OpenRouter's routing layer on this account. Unblock by either (a) routing
  config change, (b) direct Anthropic API integration, or (c) external Claude
  Code labeling session.
- [ ] **Wire S5 chat retrieval into a live test** — extraction now writes
  `claim_embedding`; `chat.retrieve_spans` reads it; add an integration test
  that ingests a doc, extracts claims, and confirms the hybrid score outranks
  span-only on a question that matches a claim better than its containing span.

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
- [ ] Shared httpx.AsyncClient via lifespan (currently created per-request in ingestion)
- [ ] Populate `docs/iterations/active/` with execution logs
- [ ] Record durable workflow lessons in `docs/insights.md` as they appear.
- [ ] `nexus document <id>` CLI command — show extracted claims inline (deferred from Phase 2.5)
- [ ] `nexus extract <doc_id>` CLI command — trigger extraction from the CLI

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
