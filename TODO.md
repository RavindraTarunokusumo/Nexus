# TODO

## Active

### Phase 3 — Claim Extraction (branch: feat/phase3-claim-extraction)

- [x] T1: langgraph>=0.2.0 dependency (commit: 48c456c)
- [x] T2: Prompts module — `app/intelligence/prompts/extract_claims.py` (commit: 31a6540)
- [x] T3: LLMClient with OpenRouter + AgentRun logging (commit: 618bc4d, fix: f602e14)
- [x] T4: LangGraph extraction graph — 4 nodes, Semaphore(5), correction-prompt retry (commit: ce76aee)
- [x] T5: Claims routes + main.py + conftest.py wiring (commit: 02ce267, spec-fix: d526093)

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
