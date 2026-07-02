# Phase C Remainder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: delegate each task below to a Grok subagent per AGENTS.md's "Grok Build Implementation/Review Handoff" — one ephemeral session per task, senior dev reviews/commits.

**Goal:** Ship the first `theses` writer (C3), first `decision_artefacts` writer (C4), and DB-bound integration tests for `judge_capsules`/`classify_relations` (C5), all as standalone writer functions + CLI commands with no automatic trigger (Phase E owns triggering — see spec).

**Architecture:** Mirror the existing `app/intelligence/capsules.py` (`build_capsule_row`) + `app/cli/capsules.py` pattern for both new writers. No changes to the extraction graph or `/chat/answer`.

**Tech Stack:** SQLAlchemy async ORM, Typer CLI, pytest (`@pytest.mark.slow` for DB tests via `tests/conftest.py`'s `run_migrations`/`clean_db` fixtures).

## Global Constraints

- `created_by_tier` for `Thesis`/`DecisionArtefact` rows must be one of `t2`/`t3`/`t4` (CHECK constraints `ck_theses_created_by_tier`, `ck_decision_artefacts_created_by_tier` in migration `0005_semantic_capsules.py`) — validate and raise `ValueError` otherwise.
- `Thesis.confidence` must be in `[0, 1]` (`ck_theses_confidence_range`).
- No git operations inside delegated Grok tasks — the senior dev stages, commits, and notes.
- Follow `ruff`/`mypy` conventions already in `app/intelligence/capsules.py` and `app/cli/capsules.py` (module docstring, `__all__`, type hints throughout).

---

### Task 1: Thesis writer (`app/intelligence/theses.py`)

**Files:**
- Create: `app/intelligence/theses.py`
- Test: `tests/intelligence/test_theses.py`

**Interfaces:**
- Consumes: `app.db.models.Thesis`, `app.db.models.SemanticRelation`, `app.db.models.SemanticCapsule` (existing).
- Produces: `build_thesis_row(*, thesis_id: uuid.UUID, domain: str, thesis_type: str, statement: str, supporting_capsule_ids: list[uuid.UUID], contradicting_capsule_ids: list[uuid.UUID], confidence: float, created_by_tier: str, title: str | None = None) -> Thesis` and `async def synthesize_theses_from_relations(session: AsyncSession, *, domain: str, min_strength: float = 0.6, min_cluster_size: int = 2, created_by_tier: str = "t2") -> list[Thesis]`. Task 2 (CLI) imports both.

- [ ] **Step 1: Write failing unit tests for `build_thesis_row`**

```python
# tests/intelligence/test_theses.py
import uuid
import pytest
from app.db.models import Thesis
from app.intelligence.theses import build_thesis_row


def test_build_thesis_row_basic_shape():
    thesis_id = uuid.uuid4()
    cap_a, cap_b = uuid.uuid4(), uuid.uuid4()
    thesis = build_thesis_row(
        thesis_id=thesis_id,
        domain="personal_ai_tech",
        thesis_type="model_release_event",
        statement="GPT-5 outperforms GPT-4 on MMLU.",
        supporting_capsule_ids=[cap_a, cap_b],
        contradicting_capsule_ids=[],
        confidence=0.75,
        created_by_tier="t2",
    )
    assert isinstance(thesis, Thesis)
    assert thesis.id == thesis_id
    assert thesis.domain == "personal_ai_tech"
    assert thesis.thesis_type == "model_release_event"
    assert thesis.supporting_capsule_ids == [cap_a, cap_b]
    assert thesis.contradicting_capsule_ids == []
    assert thesis.confidence == 0.75
    assert thesis.created_by_tier == "t2"
    assert thesis.title is None


def test_build_thesis_row_rejects_invalid_tier():
    with pytest.raises(ValueError, match="created_by_tier"):
        build_thesis_row(
            thesis_id=uuid.uuid4(),
            domain="personal_ai_tech",
            thesis_type="model_release_event",
            statement="x",
            supporting_capsule_ids=[uuid.uuid4()],
            contradicting_capsule_ids=[],
            confidence=0.5,
            created_by_tier="t0",
        )


def test_build_thesis_row_rejects_confidence_out_of_range():
    with pytest.raises(ValueError, match="confidence"):
        build_thesis_row(
            thesis_id=uuid.uuid4(),
            domain="personal_ai_tech",
            thesis_type="model_release_event",
            statement="x",
            supporting_capsule_ids=[uuid.uuid4()],
            contradicting_capsule_ids=[],
            confidence=1.5,
            created_by_tier="t2",
        )
```

- [ ] **Step 2: Run test, verify it fails**

Run: `pytest tests/intelligence/test_theses.py -v --noconftest`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.intelligence.theses'`

- [ ] **Step 3: Implement `build_thesis_row`**

```python
# app/intelligence/theses.py
"""Thesis writer: build_thesis_row (pure) + synthesize_theses_from_relations (DB orchestration).

Mirrors app/intelligence/capsules.py's build_capsule_row pattern. Per
docs/superpowers/specs/2026-07-02-phase-c-remainder-design.md, this is a
standalone writer with no automatic trigger — Phase E's consolidation worker
owns deciding when theses get created; this module only owns constructing
schema-valid rows and clustering existing relations into candidate theses.
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SemanticCapsule, SemanticRelation, Thesis

__all__ = ["build_thesis_row", "synthesize_theses_from_relations"]

_VALID_TIERS = ("t2", "t3", "t4")


def build_thesis_row(
    *,
    thesis_id: uuid.UUID,
    domain: str,
    thesis_type: str,
    statement: str,
    supporting_capsule_ids: list[uuid.UUID],
    contradicting_capsule_ids: list[uuid.UUID],
    confidence: float,
    created_by_tier: str,
    title: str | None = None,
) -> Thesis:
    if created_by_tier not in _VALID_TIERS:
        raise ValueError(f"created_by_tier must be one of {_VALID_TIERS}, got {created_by_tier!r}")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence must be in [0, 1], got {confidence!r}")
    return Thesis(
        id=thesis_id,
        domain=domain,
        thesis_type=thesis_type,
        title=title,
        statement=statement,
        supporting_capsule_ids=supporting_capsule_ids,
        contradicting_capsule_ids=contradicting_capsule_ids,
        confidence=confidence,
        created_by_tier=created_by_tier,
    )
```

- [ ] **Step 4: Run test, verify `build_thesis_row` tests pass**

Run: `pytest tests/intelligence/test_theses.py -v --noconftest -k build_thesis_row`
Expected: PASS (3 tests)

- [ ] **Step 5: Write failing unit test for the union-find clustering helper**

```python
def test_synthesize_theses_from_relations_clusters_connected_capsules(monkeypatch):
    """Uses a fake AsyncSession whose execute() returns canned relation+capsule rows."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from app.intelligence.theses import synthesize_theses_from_relations

    cap_a, cap_b, cap_c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    def _capsule(id_, family="model_release_event", salience=0.5, text="t"):
        c = MagicMock()
        c.id, c.object_family, c.salience, c.text = id_, family, salience, text
        return c

    caps = {cap_a: _capsule(cap_a, salience=0.9, text="anchor"), cap_b: _capsule(cap_b), cap_c: _capsule(cap_c)}

    def _relation(src, tgt, strength=0.8, polarity="positive", relation_type="supports", confidence=0.8):
        r = MagicMock()
        r.source_capsule_id, r.target_capsule_id = src, tgt
        r.strength, r.polarity, r.relation_type, r.confidence = strength, polarity, relation_type, confidence
        return r

    relations = [_relation(cap_a, cap_b)]  # cap_c stays isolated — below min_cluster_size

    session = AsyncMock()
    rel_result, cap_result = MagicMock(), MagicMock()
    rel_result.scalars.return_value.all.return_value = relations
    cap_result.scalars.return_value.all.return_value = list(caps.values())
    session.execute = AsyncMock(side_effect=[rel_result, cap_result])
    session.add_all = MagicMock()
    session.commit = AsyncMock()

    theses = asyncio.run(
        synthesize_theses_from_relations(session, domain="personal_ai_tech", min_strength=0.6)
    )
    assert len(theses) == 1
    assert set(theses[0].supporting_capsule_ids) == {cap_a, cap_b}
    assert theses[0].statement == "anchor"  # highest-salience member
    assert theses[0].thesis_type == "model_release_event"
```

- [ ] **Step 6: Run test, verify it fails**

Run: `pytest tests/intelligence/test_theses.py -v --noconftest -k clusters_connected`
Expected: FAIL — `AttributeError` or `ImportError` (`synthesize_theses_from_relations` not defined)

- [ ] **Step 7: Implement `synthesize_theses_from_relations`**

Append to `app/intelligence/theses.py`:

```python
def _find(parent: dict[uuid.UUID, uuid.UUID], x: uuid.UUID) -> uuid.UUID:
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def _union(parent: dict[uuid.UUID, uuid.UUID], a: uuid.UUID, b: uuid.UUID) -> None:
    ra, rb = _find(parent, a), _find(parent, b)
    if ra != rb:
        parent[ra] = rb


async def synthesize_theses_from_relations(
    session: AsyncSession,
    *,
    domain: str,
    min_strength: float = 0.6,
    min_cluster_size: int = 2,
    created_by_tier: str = "t2",
) -> list[Thesis]:
    """Cluster same-family capsules connected by strong binary relations into Thesis rows.

    Binary relations only (both source and target capsule set — excludes
    judge_capsules' unary self-reference rows). Capsules are only ever
    related within a single object_family (classify_relations only pairs
    same-family capsules), so thesis_type = the shared family is a
    restatement of an existing invariant, not new clustering logic.
    """
    capsule_ids_result = await session.execute(
        select(SemanticCapsule.id).where(SemanticCapsule.domain == domain)
    )
    domain_capsule_ids = set(capsule_ids_result.scalars().all())

    relations_result = await session.execute(
        select(SemanticRelation).where(
            SemanticRelation.target_capsule_id.is_not(None),
            SemanticRelation.strength >= min_strength,
        )
    )
    relations = [
        r
        for r in relations_result.scalars().all()
        if r.source_capsule_id in domain_capsule_ids and r.target_capsule_id in domain_capsule_ids
    ]
    if not relations:
        return []

    parent: dict[uuid.UUID, uuid.UUID] = {}
    for r in relations:
        parent.setdefault(r.source_capsule_id, r.source_capsule_id)
        parent.setdefault(r.target_capsule_id, r.target_capsule_id)
    for r in relations:
        _union(parent, r.source_capsule_id, r.target_capsule_id)

    components: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for cid in parent:
        components[_find(parent, cid)].add(cid)

    caps_result = await session.execute(
        select(SemanticCapsule).where(SemanticCapsule.id.in_(parent.keys()))
    )
    caps_by_id = {c.id: c for c in caps_result.scalars().all()}

    edges_by_pair: dict[frozenset[uuid.UUID], SemanticRelation] = {
        frozenset({r.source_capsule_id, r.target_capsule_id}): r for r in relations
    }

    theses: list[Thesis] = []
    for member_ids in components.values():
        if len(member_ids) < min_cluster_size:
            continue
        members = [caps_by_id[m] for m in member_ids if m in caps_by_id]
        if len(members) < min_cluster_size:
            continue

        contradicting: set[uuid.UUID] = set()
        component_edges = [
            r for r in relations if {r.source_capsule_id, r.target_capsule_id} <= member_ids
        ]
        for r in component_edges:
            if r.polarity == "negative" or r.relation_type == "contradicts":
                contradicting.add(r.source_capsule_id)
                contradicting.add(r.target_capsule_id)
        supporting = member_ids - contradicting

        anchor = max(members, key=lambda c: c.salience)
        confidence = sum(r.confidence for r in component_edges) / len(component_edges)

        thesis = build_thesis_row(
            thesis_id=uuid.uuid4(),
            domain=domain,
            thesis_type=anchor.object_family,
            statement=anchor.text,
            supporting_capsule_ids=sorted(supporting, key=str),
            contradicting_capsule_ids=sorted(contradicting, key=str),
            confidence=min(max(confidence, 0.0), 1.0),
            created_by_tier=created_by_tier,
        )
        theses.append(thesis)

    if theses:
        session.add_all(theses)
        await session.commit()
    return theses
```

Note: the `frozenset`-keyed `edges_by_pair` dict built above is unused after
the switch to `component_edges` filtering — remove it during implementation
(dead code); it was drafted before settling on the simpler per-component
edge filter.

- [ ] **Step 8: Run all Task 1 tests, verify pass**

Run: `pytest tests/intelligence/test_theses.py -v --noconftest`
Expected: PASS (5 tests)

- [ ] **Step 9: Commit**

```bash
git add app/intelligence/theses.py tests/intelligence/test_theses.py
git commit -m "feat(intelligence): thesis writer — build_thesis_row + synthesize_theses_from_relations (C3a)"
```

---

### Task 2: Thesis CLI (`app/cli/theses.py`)

**Files:**
- Create: `app/cli/theses.py`
- Modify: `app/cli/main.py` (register `theses_app`, mirroring line 68/72 for `capsules_app`)
- Test: `tests/test_cli_e2e.py` (append)

**Interfaces:**
- Consumes: `synthesize_theses_from_relations` from Task 1 (`app.intelligence.theses`), `CLISettings`/`_require_db_url` pattern from `app/cli/capsules.py`, `make_engine`/`make_session_factory` from `app.db.session`.
- Produces: `nexus theses synthesize --domain <pack_id> [--min-strength 0.6] [--dry-run] [--json]` CLI command.

- [ ] **Step 1: Write failing CLI smoke test**

Append to `tests/test_cli_e2e.py` (same file/pattern as `test_capsules_backfill_help_works`):

```python
def test_theses_synthesize_help_works():
    result = runner.invoke(app, ["theses", "synthesize", "--help"])
    assert result.exit_code == 0
    assert "--domain" in result.stdout
```

- [ ] **Step 2: Run test, verify it fails**

Run: `pytest tests/test_cli_e2e.py::test_theses_synthesize_help_works -v`
Expected: FAIL — `theses` is not a registered subcommand (non-zero exit or "No such command")

- [ ] **Step 3: Implement `app/cli/theses.py`**

```python
"""nexus theses sub-commands — cluster semantic_relations into Thesis rows."""

from __future__ import annotations

import asyncio
import json
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from app.cli.capsules import _require_db_url
from app.cli.config import CLISettings
from app.db.session import make_engine, make_session_factory
from app.intelligence.theses import synthesize_theses_from_relations

console = Console()
theses_app = typer.Typer(help="Thesis management commands.")


@theses_app.command("synthesize")
def synthesize(
    domain: str = typer.Option(..., "--domain", help="Domain pack id to cluster within."),
    min_strength: float = typer.Option(0.6, "--min-strength", help="Minimum relation strength to cluster on."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report clusters without writing."),
    db_url: Optional[str] = typer.Option(None, "--db-url", help="Override DATABASE_URL."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON instead of a table."),
) -> None:
    """Cluster strongly-related same-family capsules into Thesis rows.

    Reads semantic_relations written by classify_relations, unions connected
    capsules via strength >= --min-strength, and writes one Thesis per
    cluster of size >= 2. Re-running is not idempotent in this first writer
    (no unique constraint on theses) — intended for manual/reviewed use.
    """
    cfg = CLISettings(**{"database_url": db_url} if db_url else {})
    database_url = _require_db_url(cfg)
    engine = make_engine(database_url)
    sf = make_session_factory(engine)

    async def _run() -> list:
        async with sf() as session:
            if dry_run:
                # Dry-run: build clusters but roll back instead of commit.
                theses = await synthesize_theses_from_relations(session, domain=domain, min_strength=min_strength)
                await session.rollback()
                return theses
            return await synthesize_theses_from_relations(session, domain=domain, min_strength=min_strength)

    theses = asyncio.run(_run())

    if json_output:
        typer.echo(json.dumps({"domain": domain, "theses_written": len(theses), "dry_run": dry_run}, indent=2))
        return

    label = " (DRY RUN — no rows committed)" if dry_run else ""
    table = Table(title=f"Thesis Synthesis{label}")
    table.add_column("Metric", style="bold")
    table.add_column("Count", justify="right")
    table.add_row("Theses written" + (" (would write)" if dry_run else ""), str(len(theses)))
    console.print(table)
```

- [ ] **Step 4: Register `theses_app` in `app/cli/main.py`**

Find the two lines that register `capsules_app` (`from app.cli.capsules import capsules_app` and
`app.add_typer(capsules_app, name="capsules")`) and add matching lines for `theses_app` directly
after each.

- [ ] **Step 5: Run test, verify it passes**

Run: `pytest tests/test_cli_e2e.py::test_theses_synthesize_help_works -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/cli/theses.py app/cli/main.py tests/test_cli_e2e.py
git commit -m "feat(cli): nexus theses synthesize command (C3b)"
```

---

### Task 3: Decision artefact writer (`app/intelligence/decision_artefacts.py`)

**Files:**
- Create: `app/intelligence/decision_artefacts.py`
- Test: `tests/intelligence/test_decision_artefacts.py`

**Interfaces:**
- Consumes: `app.db.models.DecisionArtefact` (existing).
- Produces: `build_decision_artefact_row(*, artefact_id: uuid.UUID, artefact_type: str, domain: str | None, question: str | None, answer: str | None, linked_thesis_ids: list[uuid.UUID], linked_capsule_ids: list[uuid.UUID], source_refs: list, created_by_tier: str) -> DecisionArtefact`. Task 4 (CLI) imports it.

- [ ] **Step 1: Write failing unit tests**

```python
# tests/intelligence/test_decision_artefacts.py
import uuid
import pytest
from app.db.models import DecisionArtefact
from app.intelligence.decision_artefacts import build_decision_artefact_row


def test_build_decision_artefact_row_basic_shape():
    artefact_id = uuid.uuid4()
    cap_id = uuid.uuid4()
    artefact = build_decision_artefact_row(
        artefact_id=artefact_id,
        artefact_type="memo",
        domain="personal_ai_tech",
        question="Is GPT-5 better than GPT-4?",
        answer="Yes, per benchmark X.",
        linked_thesis_ids=[],
        linked_capsule_ids=[cap_id],
        source_refs=[],
        created_by_tier="t2",
    )
    assert isinstance(artefact, DecisionArtefact)
    assert artefact.id == artefact_id
    assert artefact.artefact_type == "memo"
    assert artefact.linked_capsule_ids == [cap_id]
    assert artefact.created_by_tier == "t2"


def test_build_decision_artefact_row_rejects_invalid_tier():
    with pytest.raises(ValueError, match="created_by_tier"):
        build_decision_artefact_row(
            artefact_id=uuid.uuid4(),
            artefact_type="memo",
            domain="personal_ai_tech",
            question="q",
            answer="a",
            linked_thesis_ids=[],
            linked_capsule_ids=[],
            source_refs=[],
            created_by_tier="t1",
        )
```

- [ ] **Step 2: Run test, verify it fails**

Run: `pytest tests/intelligence/test_decision_artefacts.py -v --noconftest`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/intelligence/decision_artefacts.py`**

```python
"""Decision artefact writer: build_decision_artefact_row (pure row construction).

Per docs/superpowers/specs/2026-07-02-phase-c-remainder-design.md, this is a
standalone writer with no automatic trigger (no /chat/answer hook) — Phase E
owns deciding when artefacts get created automatically.
"""

from __future__ import annotations

import uuid

from app.db.models import DecisionArtefact

__all__ = ["build_decision_artefact_row"]

_VALID_TIERS = ("t2", "t3", "t4")


def build_decision_artefact_row(
    *,
    artefact_id: uuid.UUID,
    artefact_type: str,
    domain: str | None,
    question: str | None,
    answer: str | None,
    linked_thesis_ids: list[uuid.UUID],
    linked_capsule_ids: list[uuid.UUID],
    source_refs: list,
    created_by_tier: str,
) -> DecisionArtefact:
    if created_by_tier not in _VALID_TIERS:
        raise ValueError(f"created_by_tier must be one of {_VALID_TIERS}, got {created_by_tier!r}")
    return DecisionArtefact(
        id=artefact_id,
        artefact_type=artefact_type,
        domain=domain,
        question=question,
        answer=answer,
        linked_thesis_ids=linked_thesis_ids,
        linked_capsule_ids=linked_capsule_ids,
        source_refs=source_refs,
        created_by_tier=created_by_tier,
    )
```

- [ ] **Step 4: Run test, verify pass**

Run: `pytest tests/intelligence/test_decision_artefacts.py -v --noconftest`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add app/intelligence/decision_artefacts.py tests/intelligence/test_decision_artefacts.py
git commit -m "feat(intelligence): decision artefact writer — build_decision_artefact_row (C4a)"
```

---

### Task 4: Decision artefact CLI (`app/cli/artefacts.py`)

**Files:**
- Create: `app/cli/artefacts.py`
- Modify: `app/cli/main.py` (register `artefacts_app`)
- Test: `tests/test_cli_e2e.py` (append)

**Interfaces:**
- Consumes: `build_decision_artefact_row` from Task 3.
- Produces: `nexus artefacts create --domain <id> --question <q> --answer <a> [--capsule-id <uuid> ...] [--thesis-id <uuid> ...] [--json]`.

- [ ] **Step 1: Write failing CLI smoke test**

Append to `tests/test_cli_e2e.py`:

```python
def test_artefacts_create_help_works():
    result = runner.invoke(app, ["artefacts", "create", "--help"])
    assert result.exit_code == 0
    assert "--question" in result.stdout
```

- [ ] **Step 2: Run test, verify it fails**

Run: `pytest tests/test_cli_e2e.py::test_artefacts_create_help_works -v`
Expected: FAIL

- [ ] **Step 3: Implement `app/cli/artefacts.py`**

```python
"""nexus artefacts sub-commands — manual DecisionArtefact creation."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Optional

import typer
from rich.console import Console

from app.cli.capsules import _require_db_url
from app.cli.config import CLISettings
from app.db.session import make_engine, make_session_factory
from app.intelligence.decision_artefacts import build_decision_artefact_row

console = Console()
artefacts_app = typer.Typer(help="DecisionArtefact management commands.")


@artefacts_app.command("create")
def create(
    domain: str = typer.Option(..., "--domain", help="Domain pack id."),
    question: str = typer.Option(..., "--question", help="Question this artefact answers."),
    answer: str = typer.Option(..., "--answer", help="Answer text."),
    capsule_id: list[str] = typer.Option([], "--capsule-id", help="Linked capsule UUID (repeatable)."),
    thesis_id: list[str] = typer.Option([], "--thesis-id", help="Linked thesis UUID (repeatable)."),
    db_url: Optional[str] = typer.Option(None, "--db-url", help="Override DATABASE_URL."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON instead of a table."),
) -> None:
    """Manually create a `memo`-type DecisionArtefact linking capsules/theses."""
    cfg = CLISettings(**{"database_url": db_url} if db_url else {})
    database_url = _require_db_url(cfg)
    engine = make_engine(database_url)
    sf = make_session_factory(engine)

    artefact_id = uuid.uuid4()
    artefact = build_decision_artefact_row(
        artefact_id=artefact_id,
        artefact_type="memo",
        domain=domain,
        question=question,
        answer=answer,
        linked_thesis_ids=[uuid.UUID(t) for t in thesis_id],
        linked_capsule_ids=[uuid.UUID(c) for c in capsule_id],
        source_refs=[],
        created_by_tier="t2",
    )

    async def _run() -> None:
        async with sf() as session:
            session.add(artefact)
            await session.commit()

    asyncio.run(_run())

    if json_output:
        typer.echo(json.dumps({"artefact_id": str(artefact_id)}, indent=2))
    else:
        console.print(f"Created decision artefact [bold]{artefact_id}[/bold]")
```

- [ ] **Step 4: Register `artefacts_app` in `app/cli/main.py`**

Same pattern as Task 2 Step 4, for `artefacts_app` / `"artefacts"`.

- [ ] **Step 5: Run test, verify pass**

Run: `pytest tests/test_cli_e2e.py::test_artefacts_create_help_works -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/cli/artefacts.py app/cli/main.py tests/test_cli_e2e.py
git commit -m "feat(cli): nexus artefacts create command (C4b)"
```

---

### Task 5: DB-bound integration tests (`tests/intelligence/test_reasoning_layer_db.py`)

**Depends on:** Tasks 1 and 3 landed (imports `synthesize_theses_from_relations`).

**Files:**
- Create: `tests/intelligence/test_reasoning_layer_db.py`

**Interfaces:**
- Consumes: `make_extraction_graph` (for `judge_capsules` node — accessed via the compiled graph since it's not module-level), `_run_classify_relations` (module-level, `app.intelligence.extraction`), `synthesize_theses_from_relations` (`app.intelligence.theses`), the `async_engine`/`session_factory`/`clean_db` fixtures from `tests/conftest.py`.

- [ ] **Step 1: Write the DB-bound test module**

```python
"""DB-bound integration tests for judge_capsules, classify_relations, and the
C3a thesis-clustering round trip. Real Postgres via tests/conftest.py fixtures;
LLM client mocked.

Run: pytest tests/intelligence/test_reasoning_layer_db.py -v -m slow
"""

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.db.models import Document, SemanticCapsule, SemanticRelation, Source
from app.domain_packs.loader import load_pack
from app.intelligence.extraction import _run_classify_relations
from app.intelligence.llm_client import JudgeVerdict
from app.intelligence.prompts.classify_relations import RelationClassification
from app.intelligence.theses import synthesize_theses_from_relations

pytestmark = pytest.mark.slow


async def _seed_source_document(session):
    source = Source(id=uuid.uuid4(), name="t", url="https://example.com", domain_pack="personal_ai_tech", source_type="rss")
    document = Document(id=uuid.uuid4(), source_id=source.id, url="https://example.com/a", status="embedded")
    session.add_all([source, document])
    await session.commit()
    return source, document


async def _seed_capsule(session, *, source_id, document_id, family="model_release_event", text="t", escalation_state="none"):
    capsule = SemanticCapsule(
        id=uuid.uuid4(),
        source_id=source_id,
        document_id=document_id,
        idempotency_key=str(uuid.uuid4()),
        core_type="claim",
        text=text,
        domain="personal_ai_tech",
        object_family=family,
        domain_object_type="model_release",
        facets={},
        salience=0.8,
        confidence=0.8,
        escalation_state=escalation_state,
        created_by_tier="t2",
    )
    session.add(capsule)
    await session.commit()
    return capsule


@pytest.mark.asyncio
async def test_judge_capsules_writes_real_relation_row(session_factory):
    async with session_factory() as session:
        source, document = await _seed_source_document(session)
        capsule = await _seed_capsule(session, source_id=source.id, document_id=document.id, escalation_state="flagged")

    from app.intelligence.extraction import make_extraction_graph

    mock_client = AsyncMock()
    mock_client.complete_json.return_value = (
        JudgeVerdict(escalate=True, rationale="needs review", recommended_confidence=0.4),
        10,
    )
    graph = make_extraction_graph(session_factory, mock_client)
    judge_capsules_node = graph.nodes["judge_capsules"].bound

    pack = load_pack("personal_ai_tech")
    state = {
        "error": None,
        "pack": pack,
        "model": "test-model",
        "stored_capsule_ids": [capsule.id],
        "t2_calls_used": 0,
    }
    result = await judge_capsules_node(state)

    assert len(result["judge_results"]) == 1
    async with session_factory() as session:
        rel = (
            await session.execute(
                select(SemanticRelation).where(SemanticRelation.source_capsule_id == capsule.id)
            )
        ).scalar_one()
        assert rel.target_capsule_id == capsule.id  # unary self-reference
        assert rel.domain_relation_type == "judge_escalated"

        refreshed = await session.get(SemanticCapsule, capsule.id)
        assert refreshed.escalation_state == "escalated"


@pytest.mark.asyncio
async def test_classify_relations_writes_real_binary_relation(session_factory):
    async with session_factory() as session:
        source, document = await _seed_source_document(session)
        cap_a = await _seed_capsule(session, source_id=source.id, document_id=document.id, text="GPT-5 scored 90% on MMLU.")
        cap_b = await _seed_capsule(session, source_id=source.id, document_id=document.id, text="GPT-4 scored 86% on MMLU.")

    mock_client = AsyncMock()
    mock_client.complete_json.return_value = (
        RelationClassification(relation_type="supports", polarity="positive", strength=0.8, rationale="both benchmark MMLU"),
        10,
    )
    pack = load_pack("personal_ai_tech")
    state = {
        "error": None,
        "pack": pack,
        "model": "test-model",
        "stored_capsule_ids": [cap_a.id, cap_b.id],
        "t2_calls_used": 0,
    }
    result = await _run_classify_relations(state, session_factory, mock_client)

    assert len(result["relation_ids"]) == 1
    async with session_factory() as session:
        rel = (
            await session.execute(
                select(SemanticRelation).where(SemanticRelation.id == result["relation_ids"][0])
            )
        ).scalar_one()
        assert {rel.source_capsule_id, rel.target_capsule_id} == {cap_a.id, cap_b.id}
        assert rel.relation_type == "supports"


@pytest.mark.asyncio
async def test_classify_relations_to_thesis_round_trip(session_factory):
    """C1(implicit)->C2->C3a: real relation rows cluster into a real Thesis row."""
    async with session_factory() as session:
        source, document = await _seed_source_document(session)
        cap_a = await _seed_capsule(session, source_id=source.id, document_id=document.id, text="GPT-5 scored 90% on MMLU.")
        cap_b = await _seed_capsule(session, source_id=source.id, document_id=document.id, text="GPT-4 scored 86% on MMLU.")

    mock_client = AsyncMock()
    mock_client.complete_json.return_value = (
        RelationClassification(relation_type="supports", polarity="positive", strength=0.8, rationale="r"),
        10,
    )
    pack = load_pack("personal_ai_tech")
    state = {
        "error": None,
        "pack": pack,
        "model": "test-model",
        "stored_capsule_ids": [cap_a.id, cap_b.id],
        "t2_calls_used": 0,
    }
    await _run_classify_relations(state, session_factory, mock_client)

    async with session_factory() as session:
        theses = await synthesize_theses_from_relations(session, domain="personal_ai_tech", min_strength=0.6)

    assert len(theses) == 1
    assert set(theses[0].supporting_capsule_ids) == {cap_a.id, cap_b.id}
```

- [ ] **Step 2: Run, verify it fails before Tasks 1/3 land (skip if run after)**

Run: `pytest tests/intelligence/test_reasoning_layer_db.py -v -m slow`
Expected: PASS once Tasks 1, 3 are committed (this task depends on them); if run standalone first, `ImportError` on `app.intelligence.theses`.

- [ ] **Step 3: Run full DB suite, verify pass**

Run: `pytest tests/intelligence/test_reasoning_layer_db.py -v -m slow`
Expected: PASS (3 tests)

- [ ] **Step 4: Commit**

```bash
git add tests/intelligence/test_reasoning_layer_db.py
git commit -m "test(intelligence): DB-bound integration tests for judge_capsules/classify_relations/theses round-trip (C5)"
```

## Self-Review Notes

- **Spec coverage:** Task 1-2 = C3a/C3b, Task 3-4 = C4a/C4b, Task 5 = C5. All five TODO sub-items covered.
- **`graph.nodes["judge_capsules"].bound` access:** verified directly against the installed `langgraph` in this environment — `graph.nodes["foo"]` is a `PregelNode`; `await node.bound(state)` calls the original async node function and returns its dict update (confirmed with a throwaway `StateGraph` in a REPL). `node.ainvoke(state)` is NOT a drop-in substitute (raises `TypeError: 'RunnableCallable' object is not callable` without a `RunnableConfig`) — use `.bound`.
- **Type consistency:** `synthesize_theses_from_relations` signature matches between Task 1 (produces) and Task 2/Task 5 (consumes) — `session, *, domain, min_strength, min_cluster_size, created_by_tier`.
