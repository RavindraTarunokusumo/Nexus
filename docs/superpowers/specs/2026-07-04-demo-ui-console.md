# Spec: Demo UI Console (H6)

**Date:** 2026-07-04
**Status:** Accepted (plan agreed in-chat 2026-07-03; hackathon fast-path)
**TODO ref:** H6 — read-only three-tab console over the existing `web/` chat app.

## Problem

The demo currently runs through CLI commands — functional but not presentable. The
submission needs a visual surface showing (a) the state of memory, (b) the chat with
its epistemic metadata, and (c) *how* Nexus works: routing, model tiering, and the
provenance chain, as diagrams.

## Requirements

### Backend (T-U1) — all additive, no breaking changes

1. `GET /stats/overview` →
   ```json
   {
     "counts": {"documents": n, "spans": n, "capsules": n, "relations": n, "theses": n},
     "lifecycle": {"active": n, "confirmed": n, "superseded": n, ...},
     "model_usage": [{"run_type": str, "model": str, "calls": n,
                      "prompt_tokens": n, "completion_tokens": n,
                      "cost_estimate_usd": float}, ...]
   }
   ```
   Single queries (GROUP BYs over `semantic_capsules.lifecycle_state` and `agent_runs`).
2. `GET /capsules/{capsule_id}/provenance` →
   ```json
   {
     "capsule": {id, text, object_family, domain_object_type, core_type,
                 lifecycle_state, salience, confidence, created_at},
     "document": {id, title, url, published_at},
     "spans": [{id, span_index, text_excerpt}],          // via capsule_segments
     "relations": [{id, direction: "in"|"out", relation_type, polarity, strength,
                    other_capsule: {id, text_excerpt, lifecycle_state}}],
     "theses": [{id, statement_excerpt}]                  // theses whose evidence/cluster includes this capsule
   }
   ```
   404 on unknown id. Text excerpts capped (~200 chars).
3. Chat answer responses (`POST /chat/answer` and the session-message route) gain
   additive fields `question_shape: str` and `query_intent: str` (the graph already
   returns both in final state; the routes drop them today). Existing response fields
   unchanged.

### Frontend (T-U2, T-U3)

4. Tab shell in `App.tsx`: `Dashboard | Chat | How it works` — plain state toggle, no
   router lib. Chat tab = the existing `SessionSidebar` + `ChatPanel`, unchanged
   behavior.
5. **Dashboard** (T-U2): count cards (documents/spans/capsules/relations/theses),
   lifecycle distribution as a horizontal stacked bar with state color legend,
   model-usage table (run_type × model, calls/tokens/cost). Data from `/stats/overview`
   on tab mount + a manual refresh button. No polling.
6. **How it works** (T-U3), two views driven by a client-side `buildMermaid()` util over
   API JSON (server stays diagram-format-agnostic):
   - *Pipeline routing*: flowchart of the **last answer asked in the Chat tab this
     session** (lifted state: question, `question_shape`, `query_intent`, citation
     roles, tokens): question → classify (T2 model name, intent+shape) → retrieval
     (shape strategy summary from a static map mirroring `router.py` values) → context
     blocks (primary/counter/supersession counts) → answer (T2, tokens). Empty state
     when no question asked yet.
   - *Provenance chain*: capsule picker (id paste + "from last answer's citations"
     shortcuts) → fetch `/capsules/{id}/provenance` → flowchart document → spans →
     capsule → relation edges to other capsules (labelled supersedes/contradicts/…,
     lifecycle-state color-coded) → thesis nodes.
   - Mermaid rendered via the `mermaid` npm package (only new dependency), init once,
     re-render on data change; wrap in an error boundary (bad diagram text must not
     crash the tab).
7. Chat citation enrichment (T-U3): role badge (primary / counter_evidence /
   supersession) and epistemic-note tooltip on `CitationList` entries; an "explain"
   disclosure per assistant message showing shape/intent/tokens.

## Non-goals (v1)

No auth (localhost demo), no live refresh/websockets, no ingest-from-UI, no pagination,
no mobile layout, no D3. Session-message route metadata persistence: the additive
fields are returned on the wire but NOT added to the `chat_messages` schema (no
migration in this PR); the pipeline view uses in-memory lifted state only.

## Edge cases

- `/stats/overview` on an empty DB → zeros, not errors.
- Provenance for a capsule with no relations/theses → empty lists.
- Mermaid render failure → error boundary shows the raw diagram text.
- Chat tab session flows must be untouched: all 26 existing frontend tests keep passing
  unmodified (except additive-field fixtures where needed).

## Success criteria

1. Full backend suite green (6 pre-existing failures only) + new endpoint tests
   (overview shape on empty + seeded DB; provenance happy path + 404).
2. `npm run lint` + `npm test` green; new component tests for Dashboard rendering
   (mocked fetch), buildMermaid output (pure string assertions), citation badges.
3. Live check: console runs against a populated scratch DB (`nexus eval memory run`
   corpus) — dashboard shows non-zero counts, a chat question renders the pipeline
   diagram with real shape/intent, clicking a citation renders its provenance chain.

## Constraints

- No DB migrations. No changes to `chat.py` graph logic — routes only surface existing
  state. `mermaid` is the only new npm dependency. Vanilla CSS matching the existing
  style.
