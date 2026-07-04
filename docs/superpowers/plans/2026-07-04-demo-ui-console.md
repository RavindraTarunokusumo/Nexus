# Plan: Demo UI Console (H6)

**Spec:** `docs/superpowers/specs/2026-07-04-demo-ui-console.md`
**Branch:** `claude/webui-h6` (worktree `.worktree/webui`; `web/node_modules` installed)

Build order: T-U1 → (T-U2 ∥ T-U3) — the frontend tasks touch disjoint files after the
shell lands with T-U2, so T-U3 starts when T-U2's `App.tsx` shell is committed.

## T-U1 — Backend endpoints (delegated)

**Files:** `app/api/routes_stats.py` (NEW), `app/api/routes_capsules.py` (NEW —
provenance), `app/main.py` (two `include_router` lines), `app/api/routes_chat.py` +
`app/api/routes_chat_sessions.py` (additive response fields), `tests/test_stats_api.py`
+ `tests/test_provenance_api.py` (NEW).

**Consumes:** ORM models (`Document`, `Span`, `CapsuleSegment`, `SemanticCapsule`,
`SemanticRelation`, `Thesis`, `AgentRun`); the chat routes' existing `final` state dict
(has `question_shape`/`query_intent` keys since PR #26/#27); existing FastAPI DI
session pattern from `routes_chat.py`.

**Produces:** the spec Requirement 1–3 JSON contracts exactly. Pydantic response
models; excerpts capped server-side; 404 via `HTTPException`. Tests follow the existing
API-test patterns (real scratch DB where the suite already uses one).

## T-U2 — Tab shell + Dashboard (delegated, after T-U1)

**Files:** `web/src/App.tsx` (tab state + shell), `web/src/components/Dashboard.tsx`
(NEW), `web/src/api/client.ts` (add `getStatsOverview`), `web/src/App.css` (tab +
card styles), `web/src/components/__tests__` or existing test location for Dashboard
tests (mocked fetch).

**Consumes:** `GET /stats/overview` contract from T-U1 (treat the spec JSON as the
contract — do not import backend code). Existing `client.ts` fetch conventions.

**Produces:** `<Dashboard />` with count cards, stacked lifecycle bar (pure CSS
percentages), model-usage table; tab shell where Chat remains the default tab and the
existing chat components render exactly as before; all pre-existing tests pass.

## T-U3 — Mermaid views + chat enrichment (delegated, after T-U2's shell commit)

**Files:** `web/src/components/HowItWorks.tsx` (NEW), `web/src/lib/mermaid.ts` (NEW —
`buildPipelineDiagram(answerMeta)`, `buildProvenanceDiagram(provenance)` pure
string-builders + a `MermaidBlock` component with error boundary),
`web/src/components/CitationList.tsx` (badges + tooltip),
`web/src/components/MessageBubble.tsx` or `ChatPanel.tsx` ("explain" disclosure +
lifting last-answer meta to App state), `web/src/api/client.ts` (add
`getCapsuleProvenance`), `package.json` (+`mermaid`), tests for the two diagram
builders (pure) + badge rendering.

**Consumes:** T-U1's provenance contract; chat answer additive fields; a static
`SHAPE_STRATEGIES` map in `mermaid.ts` mirroring `app/intelligence/router.py` values
(comment pointing at the source of truth).

**Produces:** spec Requirements 6–7. Diagram builders are pure (testable without
rendering); mermaid rendered client-side only.

## Boundaries (all tasks)

No git operations; no DB migrations; no edits to `app/intelligence/*`; chat graph
untouched. Backend self-check: full `ruff check` + `ruff format --check` + `mypy app/`
+ `pytest` (scratch DB `nexus_ui_t`; 6 known pre-existing failures). Frontend
self-check: `npm run lint` + `npm test` from `web/` (26 pre-existing tests must pass).
Single trailing newline per file.

## Risks

- **Chat-route response models may be strict** (`response_model=` filtering): additive
  fields must be added to the Pydantic response models, not just the dict — otherwise
  FastAPI silently drops them (test asserts the fields arrive on the wire).
- **Mermaid + jsdom**: mermaid does not render in jsdom — component tests must assert
  the generated diagram *text* (pure builders), not rendered SVG; `MermaidBlock` tests
  mock the mermaid module. jsdom `scrollIntoView` shim already exists in test setup.
- **Lifted answer-meta state**: keep it a single `lastAnswerMeta` object in `App.tsx`
  passed down — no context/store library.
