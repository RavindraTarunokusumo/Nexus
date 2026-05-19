# TODO

## Active

### Phase 2 validation harness

- [ ] Create and run a destructive CLI validation script that resets local data and exercises text, RSS, status, document inspection, and semantic search paths.

*(Phase 3 — Claim Extraction merged: PR #5, merge commit: 8ab514e — archived to docs/iterations/archive/)*
*(Phase 3 CLI + Model Tier Config merged: PR #6, merge commit: 87a869f — archived to docs/iterations/archive/)*

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
