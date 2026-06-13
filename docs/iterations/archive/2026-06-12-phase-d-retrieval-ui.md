# Phase D — Retrieval & UI Over Meaning

**Branch:** `claude/phase-d-retrieval-ui`
**PR:** [#21](https://github.com/RavindraTarunokusumo/Nexus/pull/21)
**Merge commit:** _pending merge_
**Merged at:** _pending merge_
**Merged by:** _pending merge_

## Summary

Cut `/chat/answer` over from span-based retrieval to semantic-capsule retrieval. Capsules are
retrieved via an HNSW cosine index over `semantic_capsules`, re-ranked with a telos-aware hybrid
score (5 active components, 2 stubbed), and gated by an LLM query-intent classifier that selects
the active pack's retrieval priorities. Citations now carry full capsule metadata and the web UI
renders enriched citation cards.

Plan: [`docs/superpowers/plans/2026-06-12-phase-d-retrieval-ui.md`](../../superpowers/plans/2026-06-12-phase-d-retrieval-ui.md)
Spec: [`docs/superpowers/specs/2026-06-12-phase-d-retrieval-ui-design.md`](../../superpowers/specs/2026-06-12-phase-d-retrieval-ui-design.md)

## Tasks Completed

**Capsule retrieval (pgvector HNSW on `semantic_capsules.embedding`)**

- [x] Migration 0006 — `ix_semantic_capsules_embedding_hnsw` (`vector_cosine_ops`, `m=16`, `ef_construction=64`); symmetric upgrade/downgrade (commit: `d3183bc`)
- [x] `_run_retrieve_capsules` — HNSW cosine search, `fetch_k = top_k * 3` over-fetch, `lifecycle_state="active"` filter, sentinel embedding pre-check (commits: `8c50285`, `fc767b4`)

**Query-intent classification (drives `retrieval_policy.query_intents`)**

- [x] `app/intelligence/prompts/classify_intent.py` — `IntentClassification` schema, `SYSTEM_PROMPT`, `build_classify_prompt` (commit: `9921abf`)
- [x] `_run_classify_intent` node helper — matches against pack intents, falls back to `general` (commits: `9921abf`, `8c50285`)

**Telos-aware hybrid scoring from `pack.retrieval_policy.hybrid_score_weights`**

- [x] `compute_hybrid_score` — 5 active components (semantic_similarity, domain_object_type_match, source_authority[stub 0.5], recency[min-max normalized], salience); `relation_relevance`/`evidence_quality` stubbed at 0.0; rank decay `_PRIORITY_SCORES = [1.0, 0.5, 0.25, 0.1]` (commit: `bf833b1`)
- [x] `default_pack_id = "personal_ai_tech"` config so `run_chat_with_context` loads a pack when none is passed (commit: `6e6223b`)

**Chat-over-capsules — `/chat/answer` cutover from `claims` to `semantic_capsules`**

- [x] Chat graph rewrite — 4-node `StateGraph` (`classify_intent → retrieve_capsules → [conditional] → generate_answer → format_result`); `ChatCitation` schema with capsule fields; capsule-block user prompt in `chat_answer.py` (commit: `8c50285`)
- [x] CLI citations column renamed Span → Capsule (`capsule_id`) (commit: `5b80d99`)
- [x] Obsolete span-based graph integration tests removed; observability test retained (commit: `1263e5c`)

**Web UI updates — capsule cards, lifecycle indicators**

- [x] `ChatCitation` TS type updated; `CitationList` rewritten with lifecycle dot (green/amber/gray), object-type pill badge, inline truncated summary, expandable panel (commit: `3cad14f`)

**Pre-PR gates**

- [x] `/simplify` — list comprehension in scoring sort (commit: `92930a8`) (the paired import-merge was reverted by ruff, which keeps aliased imports in a separate block — see insights)
- [x] `doc-updater` — `architecture.md`, `database.md`, `index.md`, `testing.md`, `changelog.md` updated (commit: `02d6273`)

**Code-review fixes (Opus review)**

- [x] `_run_classify_intent` catches the `LLMError` base class (not just `LLMNetworkError`), so classifier schema/4xx errors degrade to `general` intent instead of 503-ing the whole answer; regression test added (commit: `c78e408`)

**Reflection**

- [x] Four workflow lessons recorded in `docs/insights.md` (commit: `680ee29`)

## Test Results

16/16 unit tests passing across `tests/intelligence/test_chat_intent.py` (5, incl. the schema-error fallback), `test_chat_scoring.py` (5), `test_chat_graph.py` (6) — DB and LLM mocked.
13 pre-existing DB-dependent failures are unrelated (verified identical on `main`).

## What Phase D Did Not Do (Phase E+ backlog)

- **Context assembly per `pack.context_assembly`** — context is assembled (top-k capsule blocks `C1..Cn`) but not yet driven by the pack's declarative `context_assembly` policy (token budgets, ordering rules). Deferred.
- **Drop `claims` + `claim_evidence` tables** — held until `/chat/answer` cutover is green in production for 1 week (per original TODO).
- **Stubbed scoring inputs** — `source_authority` (uniform 0.5), `relation_relevance` (0.0), `evidence_quality` (0.0) await Phase E relation-graph and source-authority signals.
- **Declarative `lifecycle_state` filter and intent selection in pack YAML** — currently hardcoded; deferred to Phase E.
