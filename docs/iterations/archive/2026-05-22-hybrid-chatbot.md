# Phase 3 — Hybrid Chatbot

**Branch:** `codex/chatbot-workflow-session`
**PR:** #9
**Merge commit:** `7267e33`
**Merged at:** 2026-05-24T12:53:52Z
**Merged by:** RavindraTarunokusumo

## Summary

Implemented a single-turn grounded chatbot that answers questions from embedded spans plus linked active claims. The feature uses a LangGraph chat answer flow, the existing T2 OpenRouter model path, validated citation labels, and exposes both `POST /chat/answer` and `nexus chat`.

## Tasks Completed

- [x] Design spec and implementation plan (commits: `1f581cc`, `94b6ddc`)
- [x] TODO workflow ledger for the chatbot session (commit: `454038b`)
- [x] LLM client run type support for `chat_answer` audit rows (commit: `d8a7503`)
- [x] Hybrid chat graph, prompt, `chat_run()` context, citation validation, and graph tests (commit: `e4c40e0`)
- [x] Chat API route and app/test wiring (commit: `e2936d2`)
- [x] CLI `nexus chat` command and renderer (commit: `8f0ac23`)
- [x] Architecture, command, CLI, and testing documentation (commits: `150a5eb`, `5920724`)
- [x] Validation ledger tag for docs task (commit: `5ef1705`)
- [x] Extraction graph run ID stability fix found during final validation (commit: `d4a6a03`)
- [x] Review fix: schema-invalid LLM responses audited as `schema_error` instead of `success` (commit: `d3737d5`)
- [x] Review-fix TODO hash tag (commit: `facd98e`)

## Key Decisions

- **Hybrid context over claims-only answers** — The graph retrieves embedded spans first, then hydrates linked active claims through `claim_evidence` so answers can cite source text even when extracted claims are sparse.
- **Citation labels are API-validated** — Model-returned labels are normalized, deduplicated, and matched only against retrieved context labels. Unknown or citation-free answers fall back to insufficient evidence.
- **No evidence skips the model** — Empty embedded context returns the insufficient-evidence answer with zero token usage and no OpenRouter call.
- **Chat uses the existing T2 model path** — `LLMClient.complete_json()` now accepts `run_type`, defaulting to `claim_extraction` to preserve extraction behavior while recording chat runs as `chat_answer`.
- **Context isolation for chat runs** — `chat_run()` mints a run ID and clears document/span context during chat answers, then restores any prior extraction context on exit.

## Test Results

Final merged validation on `7267e33`:

- `pre-commit run --all-files` passed.
- `python -m pytest tests/ -v` passed: 155 tests, 6 existing FastAPI 422 deprecation warnings.
- Subagent targeted review checks passed before merge: targeted chat/LLM/CLI/API tests passed, and GitNexus detect-changes reported low risk after the review fix.

## Lessons

- Schema validation must happen inside the audited LLM call status window; otherwise invalid JSON/schema outputs can be recorded as successful `agent_runs`.
- Fresh review agents can find useful audit/data-integrity issues, but must be constrained carefully because delegated agents may exceed read-only instructions.
- Citation safety needs both prompt rules and server-side validation; prompt-only citation discipline is not enough for a merge-ready chatbot endpoint.
