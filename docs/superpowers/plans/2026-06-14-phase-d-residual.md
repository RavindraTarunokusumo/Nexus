# Phase D Residual Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make chat retrieval honor the pack's declarative token budget (A) and surface each citation's capsule→span evidence chain in the web UI (B).

**Architecture:** Two pure helpers (`estimate_tokens`, `_assemble_within_budget`) replace the flat `top_k` slice in `_run_retrieve_capsules`. A second pure helper (`_build_evidence_map`) shapes a `CapsuleSegment⨝Span` query into per-capsule excerpts attached to each context block and carried into `ChatCitation.evidence`, then rendered by `CitationList`.

**Tech Stack:** Python 3.11, SQLAlchemy 2 async, Pydantic v2, LangGraph; React + TypeScript + Vitest.

**Conventions:** Worktree `C:\Users\rvind\OneDrive\Desktop\Projects\Nexus\.claude\worktrees\phase-d-residual`, branch `claude/phase-d-residual`. Activate `.venv` before pytest. Run `pre-commit run --all-files` before each commit; code commits use `$env:SKIP = "mypy,pytest-fast"` (PowerShell) due to pre-existing mypy/pytest-fast failures. Stage specific files only. Postgres must be up (`docker compose up -d`) for the autouse migration fixture.

---

## Task 1 (A1): Pure token-budget helpers

**Files:**
- Modify: `app/intelligence/chat.py` (add helpers after `_PRIORITY_SCORES`)
- Test: `tests/intelligence/test_chat_assembly.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
# tests/intelligence/test_chat_assembly.py
from __future__ import annotations

from app.intelligence.chat import _assemble_within_budget, estimate_tokens


def _c(text: str) -> dict:
    return {"text": text}


def test_estimate_tokens_ceil_div_4() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2


def test_assemble_none_budget_is_flat_top_k() -> None:
    scored = [(_c("x" * 400), 0.9), (_c("y" * 400), 0.8), (_c("z" * 400), 0.7)]
    assert _assemble_within_budget(scored, top_k=2, token_budget=None) == scored[:2]


def test_assemble_stops_when_budget_exceeded() -> None:
    # each block 400 chars -> 100 tokens; budget 250 fits two (200), not three (300)
    scored = [(_c("a" * 400), 0.9), (_c("b" * 400), 0.8), (_c("c" * 400), 0.7)]
    out = _assemble_within_budget(scored, top_k=10, token_budget=250)
    assert [s for _, s in out] == [0.9, 0.8]


def test_assemble_respects_top_k_cap_under_budget() -> None:
    scored = [(_c("a" * 4), 0.9), (_c("b" * 4), 0.8), (_c("c" * 4), 0.7)]
    out = _assemble_within_budget(scored, top_k=2, token_budget=100000)
    assert len(out) == 2


def test_assemble_always_includes_first_even_if_over_budget() -> None:
    scored = [(_c("a" * 4000), 0.9), (_c("b" * 4), 0.8)]  # first ~1000 tokens
    out = _assemble_within_budget(scored, top_k=10, token_budget=10)
    assert [s for _, s in out] == [0.9]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/intelligence/test_chat_assembly.py -q`
Expected: FAIL — `ImportError: cannot import name '_assemble_within_budget'`.

- [ ] **Step 3: Implement the helpers**

In `app/intelligence/chat.py`, after the `_PRIORITY_SCORES = [...]` line:

```python
def estimate_tokens(text: str) -> int:
    """Cheap char-based token estimate (~4 chars/token). Sufficient for a soft budget gate."""
    return (len(text) + 3) // 4


def _assemble_within_budget(
    scored: list[tuple[dict, float]],
    top_k: int,
    token_budget: int | None,
) -> list[tuple[dict, float]]:
    """Pick score-ordered blocks under a token budget; top_k caps the count.

    Always includes the highest-scored block even if it alone exceeds the budget.
    token_budget=None falls back to the flat top_k slice.
    """
    if token_budget is None:
        return scored[:top_k]
    selected: list[tuple[dict, float]] = []
    running = 0
    for cand, score in scored:
        if len(selected) >= top_k:
            break
        est = estimate_tokens(cand["text"])
        if selected and running + est > token_budget:
            break
        selected.append((cand, score))
        running += est
    return selected
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/intelligence/test_chat_assembly.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```powershell
git add app/intelligence/chat.py tests/intelligence/test_chat_assembly.py
$env:SKIP = "mypy,pytest-fast"; git commit -m "feat(chat): token-budget assembly helpers (estimate_tokens, _assemble_within_budget)"
```

---

## Task 2 (A2): Wire the budget into `_run_retrieve_capsules`

**Files:**
- Modify: `app/intelligence/chat.py` (`_run_retrieve_capsules`, the `top =` selection)
- Test: `tests/intelligence/test_chat_graph.py` (`_make_pack` helper)

- [ ] **Step 1: Run impact analysis**

Run: `gitnexus_impact({target: "_run_retrieve_capsules", direction: "upstream", repo: "Nexus"})`
Expected: only the `retrieve_capsules` node calls it (LOW). Report it.

- [ ] **Step 2: Update `_make_pack` so `context_assembly.max_tokens_by_tier` is a real dict**

In `tests/intelligence/test_chat_graph.py`, in `_make_pack`, add (so the MagicMock does not return a truthy mock for `.get("T2")`):

```python
    pack.context_assembly.max_tokens_by_tier = {}
```

This keeps existing graph tests on the flat-`top_k` path (budget `None`).

- [ ] **Step 3: Replace the flat slice with budget assembly**

In `_run_retrieve_capsules`, replace:

```python
    top = scored[: state["top_k"]]
```

with:

```python
    token_budget: int | None = None
    if pack is not None:
        token_budget = pack.context_assembly.max_tokens_by_tier.get("T2")
    top = _assemble_within_budget(scored, state["top_k"], token_budget)
```

- [ ] **Step 4: Run the affected tests**

Run: `pytest tests/intelligence/test_chat_graph.py tests/intelligence/test_chat_assembly.py -q`
Expected: PASS (all existing graph tests + the 5 assembly tests).

- [ ] **Step 5: Commit**

```powershell
git add app/intelligence/chat.py tests/intelligence/test_chat_graph.py
$env:SKIP = "mypy,pytest-fast"; git commit -m "feat(chat): honor pack context_assembly T2 token budget in retrieval"
```

---

## Task 3 (B1): `CitationEvidence`, `ChatCitation.evidence`, `_build_evidence_map`

**Files:**
- Modify: `app/intelligence/chat.py` (model + constants + pure helper)
- Test: `tests/intelligence/test_chat_assembly.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/intelligence/test_chat_assembly.py`:

```python
import uuid

from app.intelligence.chat import (
    _EVIDENCE_EXCERPT_CHARS,
    _MAX_EVIDENCE_SPANS,
    _build_evidence_map,
)


def test_build_evidence_map_groups_and_orders() -> None:
    cap = uuid.uuid4()
    s1, s2 = uuid.uuid4(), uuid.uuid4()
    rows = [(cap, s1, 0, "first"), (cap, s2, 1, "second")]
    out = _build_evidence_map(rows, _MAX_EVIDENCE_SPANS, _EVIDENCE_EXCERPT_CHARS)
    assert [e["span_index"] for e in out[cap]] == [0, 1]
    assert out[cap][0]["span_id"] == s1


def test_build_evidence_map_caps_spans() -> None:
    cap = uuid.uuid4()
    rows = [(cap, uuid.uuid4(), i, f"s{i}") for i in range(_MAX_EVIDENCE_SPANS + 3)]
    out = _build_evidence_map(rows, _MAX_EVIDENCE_SPANS, _EVIDENCE_EXCERPT_CHARS)
    assert len(out[cap]) == _MAX_EVIDENCE_SPANS


def test_build_evidence_map_truncates_text() -> None:
    cap = uuid.uuid4()
    long = "x" * (_EVIDENCE_EXCERPT_CHARS + 50)
    out = _build_evidence_map([(cap, uuid.uuid4(), 0, long)], _MAX_EVIDENCE_SPANS, _EVIDENCE_EXCERPT_CHARS)
    assert len(out[cap][0]["text"]) == _EVIDENCE_EXCERPT_CHARS
    assert out[cap][0]["text"].endswith("…")


def test_build_evidence_map_empty() -> None:
    assert _build_evidence_map([], _MAX_EVIDENCE_SPANS, _EVIDENCE_EXCERPT_CHARS) == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/intelligence/test_chat_assembly.py -q`
Expected: FAIL — `ImportError: cannot import name '_build_evidence_map'`.

- [ ] **Step 3: Add the model, constants, and helper**

In `app/intelligence/chat.py`, add `CitationEvidence` before `ChatCitation` and an `evidence` field on `ChatCitation`:

```python
class CitationEvidence(BaseModel):
    span_id: uuid.UUID
    span_index: int
    text: str
```

Add to `ChatCitation` (after `summary`):

```python
    evidence: list[CitationEvidence] = []
```

Add constants near `_PRIORITY_SCORES`:

```python
_MAX_EVIDENCE_SPANS = 5
_EVIDENCE_EXCERPT_CHARS = 280
```

Add the pure helper (near the other helpers):

```python
def _build_evidence_map(
    rows: list,
    max_spans: int,
    excerpt_chars: int,
) -> dict[uuid.UUID, list[dict[str, Any]]]:
    """Shape (capsule_id, span_id, span_index, text) rows into per-capsule excerpts.

    Rows must arrive ordered by capsule_id then span_index. Keeps up to max_spans per
    capsule and truncates each excerpt to excerpt_chars (trailing ellipsis when cut).
    """
    out: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for capsule_id, span_id, span_index, text in rows:
        bucket = out.setdefault(capsule_id, [])
        if len(bucket) >= max_spans:
            continue
        excerpt = text if len(text) <= excerpt_chars else text[: excerpt_chars - 1] + "…"
        bucket.append({"span_id": span_id, "span_index": span_index, "text": excerpt})
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/intelligence/test_chat_assembly.py -q`
Expected: PASS (9 passed total).

- [ ] **Step 5: Commit**

```powershell
git add app/intelligence/chat.py tests/intelligence/test_chat_assembly.py
$env:SKIP = "mypy,pytest-fast"; git commit -m "feat(chat): CitationEvidence model + _build_evidence_map helper"
```

---

## Task 4 (B2): Evidence query + `format_result` wiring

**Files:**
- Modify: `app/intelligence/chat.py` (imports, `_run_retrieve_capsules`, `format_result`)
- Test: `tests/intelligence/test_chat_graph.py` (`_make_session_factory`, retrieve test)

- [ ] **Step 1: Run impact analysis**

Run: `gitnexus_impact({target: "format_result", direction: "upstream", repo: "Nexus"})`
Expected: internal to the graph (LOW). Report it.

- [ ] **Step 2: Add imports**

In `app/intelligence/chat.py`, change:

```python
from app.db.models import Document, SemanticCapsule
```

to:

```python
from app.db.models import CapsuleSegment, Document, SemanticCapsule, Span
```

- [ ] **Step 3: Fetch evidence for the assembled blocks**

In `_run_retrieve_capsules`, after `top = _assemble_within_budget(...)` and before the `blocks = [...]` list, add:

```python
    capsule_ids = [c["id"] for c, _ in top]
    evidence_map: dict[uuid.UUID, list[dict[str, Any]]] = {}
    if capsule_ids:
        async with session_factory() as session:
            evidence_rows = (
                await session.execute(
                    select(
                        CapsuleSegment.capsule_id,
                        Span.id,
                        Span.span_index,
                        Span.text,
                    )
                    .join(Span, CapsuleSegment.segment_id == Span.id)
                    .where(CapsuleSegment.capsule_id.in_(capsule_ids))
                    .order_by(CapsuleSegment.capsule_id, Span.span_index)
                )
            ).all()
        evidence_map = _build_evidence_map(
            evidence_rows, _MAX_EVIDENCE_SPANS, _EVIDENCE_EXCERPT_CHARS
        )
```

Then add `"evidence"` to each block dict in the `blocks = [...]` comprehension (after `"lifecycle_state": c["lifecycle_state"],`):

```python
            "evidence": evidence_map.get(c["id"], []),
```

- [ ] **Step 4: Carry evidence into the citation**

In `format_result`, add to the `ChatCitation(...)` construction (after `summary=block["text"],`):

```python
                    evidence=block.get("evidence", []),
```

- [ ] **Step 5: Update the graph test session mock for the second query**

In `tests/intelligence/test_chat_graph.py`, `_make_session_factory` must return a session whose `execute` yields the candidate rows on the first call and evidence rows on the second. Update the helper so the mock session's `execute` uses a side-effect list. For the existing `test_retrieve_capsules_returns_labelled_blocks`, supply an empty evidence result for the second call, e.g.:

```python
    capsule_result = MagicMock()
    capsule_result.all.return_value = rows
    evidence_result = MagicMock()
    evidence_result.all.return_value = []
    mock_session.execute = AsyncMock(side_effect=[capsule_result, evidence_result])
```

Add a focused test asserting evidence is attached:

```python
@pytest.mark.asyncio
async def test_retrieve_capsules_attaches_evidence() -> None:
    from app.intelligence.chat import _run_retrieve_capsules

    doc_id, cap_id, span_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    cap_row = _capsule_row(cap_id, doc_id)  # existing helper producing a candidate row
    capsule_result = MagicMock()
    capsule_result.all.return_value = [cap_row]
    evidence_result = MagicMock()
    evidence_result.all.return_value = [(cap_id, span_id, 0, "supporting span text")]
    mock_session = MagicMock()
    mock_session.scalar = AsyncMock(return_value=object())
    mock_session.execute = AsyncMock(side_effect=[capsule_result, evidence_result])
    sf = _make_session_factory(mock_session)
    state = {"question": "q", "top_k": 5, "pack": _make_pack(query_intents={"general": {}})}

    result = await _run_retrieve_capsules(state, sf, _make_embedder())

    assert result["context_blocks"][0]["evidence"][0]["text"] == "supporting span text"
    assert result["context_blocks"][0]["evidence"][0]["span_id"] == span_id
```

> If `_make_session_factory` / `_capsule_row` signatures differ, adapt the test to the actual helpers in the file — the key behavior is: first `execute` → candidate rows, second `execute` → evidence rows, sentinel `scalar` non-None.

- [ ] **Step 6: Run the affected tests**

Run: `pytest tests/intelligence/test_chat_graph.py tests/intelligence/test_chat_assembly.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add app/intelligence/chat.py tests/intelligence/test_chat_graph.py
$env:SKIP = "mypy,pytest-fast"; git commit -m "feat(chat): attach capsule->span evidence to citations"
```

---

## Task 5 (B3): Frontend — type + CitationList evidence subsection

**Files:**
- Modify: `web/src/api/client.ts` (`ChatCitation` type)
- Modify: `web/src/components/CitationList.tsx` (expanded panel)
- Test: `web/src/test/components.test.tsx`

- [ ] **Step 1: Extend the `ChatCitation` type**

In `web/src/api/client.ts`, add to `ChatCitation` (after `summary: string`):

```typescript
  evidence: { span_id: string; span_index: number; text: string }[]
```

- [ ] **Step 2: Write the failing frontend tests**

In `web/src/test/components.test.tsx`, add `evidence` to the existing `CITATION` fixture, e.g.:

```typescript
  evidence: [{ span_id: 's1', span_index: 0, text: 'supporting excerpt' }],
```

Add two tests (expand the citation, then assert):

```typescript
  it('renders evidence excerpts in the expanded panel', async () => {
    render(<CitationList citations={[CITATION]} />)
    await userEvent.click(screen.getByRole('button'))
    expect(screen.getByText(/supporting excerpt/)).toBeInTheDocument()
    expect(screen.getByText('Evidence')).toBeInTheDocument()
  })

  it('omits the Evidence subsection when there is no evidence', async () => {
    render(<CitationList citations={[{ ...CITATION, evidence: [] }]} />)
    await userEvent.click(screen.getByRole('button'))
    expect(screen.queryByText('Evidence')).not.toBeInTheDocument()
  })
```

> If the test file already imports `userEvent`/`render`/`screen`, reuse them; otherwise import from `@testing-library/react` and `@testing-library/user-event` matching the file's existing pattern.

- [ ] **Step 3: Run tests to verify they fail**

Run (from `web/`): `npm run test -- --run components`
Expected: FAIL — "Evidence" / "supporting excerpt" not found.

- [ ] **Step 4: Render the evidence subsection**

In `web/src/components/CitationList.tsx`, inside the expanded panel `<div>` (after the Document line at `<p>Document: ...</p>`), add:

```tsx
              {c.evidence.length > 0 && (
                <div className="pt-1 border-t border-gray-200">
                  <p className="font-medium text-gray-500">Evidence</p>
                  <ul className="space-y-0.5">
                    {c.evidence.map((e) => (
                      <li key={e.span_id} className="text-gray-600">
                        <span className="text-gray-400 font-mono mr-1">#{e.span_index}</span>
                        {e.text}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
```

- [ ] **Step 5: Run tests to verify they pass**

Run (from `web/`): `npm run test -- --run components`
Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add web/src/api/client.ts web/src/components/CitationList.tsx web/src/test/components.test.tsx
$env:SKIP = "mypy,pytest-fast"; git commit -m "feat(web): render capsule->span evidence chain in CitationList"
```

---

## Pre-PR

- [ ] `gitnexus_detect_changes({scope: "compare", base_ref: "main", repo: "Nexus"})` — confirm scope is contained to chat retrieval + CitationList.
- [ ] `/simplify` skill on the branch diff; apply fixes.
- [ ] `doc-updater` subagent — update `docs/architecture.md` (`/chat/answer` detail: token budget + evidence), `docs/changelog.md` (Phase D residual entry), `docs/index.md` if helper inventory is affected.
- [ ] Git note on every commit (template `.github/git_notes_template.md`); push branch + `refs/notes/commits`.
- [ ] Open PR from `.github/pull_request_template.md`.
- [ ] Opus code review; address findings.

## Notes

- Security/architectural subagents (`security-review`, `test-plan-writer`): **skip with justification** — no new trust boundary (evidence excerpts are already-stored span text surfaced read-only; token budget is internal arithmetic), and the change is a focused extension of an existing, reviewed retrieval path.
- `max_tokens_by_tier["T3"]`/`["T4"]` are intentionally unused here — chat answers run on T2.
