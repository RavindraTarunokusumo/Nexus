# TODO

## Active

*(No active work items — all Phase 2.5 tasks complete and merged.)*

## Future

### Phase 3 — Claim Extraction + LLM Gateway

- [ ] POST /documents/{id}/extract-claims — LLM-driven claim extraction from document spans
- [ ] OpenRouter LLM client — configurable model gateway, cost tracking via AgentRun
- [ ] Evidence linking — ClaimEvidence rows joining claims to supporting spans
- [ ] Re-embedding sweep — background job to embed documents left in "chunked" state when embedder was unavailable

### Ongoing

- [ ] HTTP Basic Auth / API key middleware (security gap, open since Phase 1)
- [ ] Shared httpx.AsyncClient via lifespan (currently created per-request in ingestion)
- [ ] Populate `docs/iterations/active/` with execution logs
- [ ] Record durable workflow lessons in `docs/insights.md` as they appear.
