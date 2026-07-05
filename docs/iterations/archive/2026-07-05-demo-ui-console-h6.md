# H6 — Demo UI Console

**Branch:** `claude/webui-h6`
**PR:** [#28](https://github.com/RavindraTarunokusumo/Nexus/pull/28)
**Merge commit:** `b9047b0`
**Merged at:** 2026-07-05T13:50:58Z
**Merged by:** RavindraTarunokusumo

## Summary

Read-only three-tab demo console over the existing `web/` chat app: **Dashboard**
(memory-state counts, lifecycle distribution bar, model-usage/cost table), **Chat**
(existing session UI, enriched with citation role badges, epistemic-note tooltips,
and a per-answer "explain" disclosure), and **How it works** (Mermaid diagrams: a
pipeline-routing flowchart of the last answer annotated with the actual question
shape/intent/models/tokens, and a provenance-chain view for any capsule showing
document → spans → capsule → relation edges → theses with lifecycle color coding).

Backend additions (all additive, no migrations): `GET /stats/overview`,
`GET /capsules/{id}/provenance`, and `question_shape`/`query_intent` surfaced on
chat answer responses.

Spec: [`docs/superpowers/specs/2026-07-04-demo-ui-console.md`](../../superpowers/specs/2026-07-04-demo-ui-console.md).
Plan: [`docs/superpowers/plans/2026-07-04-demo-ui-console.md`](../../superpowers/plans/2026-07-04-demo-ui-console.md).

## Tasks Completed

- [x] T-U1 — Backend (no UI dependency; Grok implementer, 545 passed / 6
  pre-existing; wire test proves additive fields arrive): `GET /stats/overview`
  (entity counts, lifecycle histogram, `agent_runs` calls/tokens/cost by
  run_type × model); `GET /capsules/{id}/provenance` (document → spans →
  capsule → relations → thesis chain as structured JSON); additive
  `question_shape` + `query_intent` fields on chat answer responses (the
  chat graph already returned them; the route just didn't surface them).
  Tests: `tests/test_stats_api.py`, `tests/test_provenance_api.py` (8 total).
  (`10cb890`)
- [x] T-U2 — Frontend: tab shell (Dashboard | Chat | How it works, no router
  lib) + Dashboard (count cards, lifecycle distribution bar, model-usage
  table). (`98be6cd`)
- [x] T-U3 — Frontend: "How it works" Mermaid views — pipeline routing
  flowchart of the last answer (classify → strategy → retrieval → context
  blocks → answer, annotated with actual models/shape/values) and provenance
  chain view (click a citation or pick a capsule; lifecycle-state color
  coding, cross-doc supersedes/contradicts edges). Client-side
  `buildMermaid()` over the JSON payloads (server stays diagram-format-
  agnostic); new dep `mermaid`. Plus chat citation enrichment: role badges
  (primary/counter_evidence/supersession) + epistemic-note tooltip, "explain
  this answer" routing disclosure. Frontend tests +20 (46 total). (`aabd393`)
- [x] `/simplify` pass (`d1cbd08`) — 7 of 23 Grok findings applied (−102 LOC):
  parallel provenance type family deleted, mermaid failure handling
  collapsed to one path, serializer reuse. Consistency refactors deferred
  (`e26c94c`); query-merging skipped (sub-10ms at demo scale).
- [x] Bundled PR review response (`298d73d`) — provenance edge direction,
  fetch races, session-switch reset.

## Validation

Backend: 545 passed / 6 pre-existing failures; ruff/mypy at baseline.
Frontend: 46 passed; lint at the 2 pre-existing hook-file errors. Live
end-to-end against a populated DB: stats served real counts/lifecycle
histogram; a real question returned the superseding fact with
`question_shape: factoid` on the wire and role-tagged citations; the cited
capsule's provenance returned the full chain including edges to the
superseded capsules it replaced. Security review (Grok): no high-confidence
findings — mermaid `securityLevel` + label sanitization verified; endpoints
match the repo's existing auth-less demo threat model.

## Deferred / Not Reattempted

- UI display-consistency refactors (role vocabulary, lifecycle palette,
  shared excerpt util) — kept as an active TODO backlog item, not archived.
- Auth before any non-localhost exposure (pre-existing item, tracked
  separately under "Ongoing").
