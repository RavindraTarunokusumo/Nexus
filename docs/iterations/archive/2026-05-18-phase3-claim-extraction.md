# Phase 3 — Claim Extraction

**Branch:** `feat/phase3-claim-extraction`
**PR:** #5
**Merge commit:** `8ab514e`
**Merged at:** 2026-05-18T23:34:00Z
**Merged by:** RavindraTarunokusumo

## Summary

Implemented structured claim extraction from document spans using LangGraph orchestration, an OpenRouter LLM gateway, and a REST claims API. Documents transition from `embedded` → `claims_extracted | extraction_partial | extraction_failed`.

## Tasks Completed

- [x] T1: `langgraph>=0.2.0` dependency (commit: `48c456c`)
- [x] T2: Prompts module — `app/intelligence/prompts/extract_claims.py` (commit: `31a6540`)
- [x] T3: LLMClient with OpenRouter + AgentRun logging (commit: `618bc4d`, fix: `f602e14`)
- [x] T4: LangGraph extraction graph — 4 nodes, `Semaphore(5)`, correction-prompt retry (commit: `ce76aee`)
- [x] T5: Claims routes + `main.py` + `conftest.py` wiring (commit: `02ce267`, spec-fix: `d526093`)
- [x] Reviewer fixes: raw_output on LLMSchemaError, KeyError/IndexError as LLMError, partial status test (commit: `6c31f9c`)
- [x] Simplify: batch claim inserts, centralize status constants, state-driven claim_ids (commit: `2a357b2`)
- [x] Doc-updater: architecture, changelog, commands, database, pipeline spec (commit: `d901244`)
- [x] GitNexus stat update: 2079 symbols, 2900 relationships, 46 flows (commit: `7e7dfa9`)

## Key Decisions

- **LangGraph StateGraph** over manual async orchestration — cleaner conditional routing (error path skips store_claims).
- **`async_sessionmaker` as sync callable** — mirrors production interface; test fixture uses `MagicMock(return_value=session)` not `AsyncMock`.
- **Pre-assigned UUIDs + `add_all`** — avoids N+1 per-claim flush; `stored_claim_ids` returned in graph state so route skips redundant SELECT.
- **`LLMNetworkError` aborts graph; `LLMSchemaError` retries span; `LLMError` fails span** — three-tier failure policy.
- **`POST_EXTRACTION_STATUSES` tuple** — 422 guard accepts `embedded` + all post-extraction statuses to allow `?force=true` re-runs.

## Test Results

94 tests passing (21 new: 4 prompts, 5 LLM client, 5 graph, 7 routes). Pre-commit hooks green. Security review: no HIGH/MEDIUM findings.

## Lessons

- Subagent implementers may deviate from spec to make their own tests pass (Task 5 weakened the 409 check). Spec reviewer + explicit test-adjustment guidance prevents this.
- `async_sessionmaker` pattern must be mirrored exactly in test fixtures — `MagicMock` not `AsyncMock`.
- Pre-PR gates (simplify, doc-updater, security-review) must be scheduled explicitly in the plan; they were skipped in the first pass.
