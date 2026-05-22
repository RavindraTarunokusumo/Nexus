# Observability — Centralized Logger & DB-Backed Tracer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a centralized stdlib JSON logger and a DB-backed pipeline tracer to Nexus so every LLM call, span extraction outcome, and document status transition is queryable and correlated by `run_id`.

**Architecture:** A new `app/observability/` package owns three focused modules: `run_context.py` (asyncio-safe contextvars), `logger.py` (stdlib JSON formatter + `RunContextFilter`), and `tracer.py` (thin DB-writing helpers). Correlation IDs flow implicitly via `ContextVar` so no function signatures change. A new Alembic migration (`0002`) adds the required schema. Two new CLI commands (`nexus runs list`, `nexus runs show`) query the DB trace.

**Tech Stack:** Python 3.11 stdlib `logging` + `contextvars`, SQLAlchemy 2.x async ORM, Alembic, Typer, Rich. No new external dependencies.

> **CLAUDE.md discipline reminder:** This repo is indexed by GitNexus. Before editing any existing symbol: run `gitnexus_impact({target: "symbolName", repo: "Nexus"})`. Before every commit: run `gitnexus_detect_changes()`. If the index is stale (>5 commits behind), run `npx gitnexus analyze` first. Work exclusively on the `observability` branch inside `.claude/worktrees/observability/`.

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `app/observability/__init__.py` | Public re-exports |
| Create | `app/observability/run_context.py` | `ContextVar`s + `extraction_run()` + `span_scope()` + `current_context()` |
| Create | `app/observability/logger.py` | `RunContextFilter` + `configure_logging()` + JSON formatter |
| Create | `app/observability/tracer.py` | `record_agent_run()`, `record_span_extraction()`, `mark_document_timestamp()` |
| Create | `app/db/migrations/versions/0002_observability.py` | Schema additions — `agent_runs` columns, `span_extractions` table, `documents.*_at` timestamps |
| Modify | `app/db/models.py` | `AgentRun` new columns; new `SpanExtraction` model; `Document` new `*_at` columns |
| Modify | `app/intelligence/llm_client.py` | Replace `_log` with `tracer.record_agent_run`; remove truncation; split token accounting |
| Modify | `app/intelligence/extraction.py` | Wrap graph in `extraction_run`; `span_scope` per span; write `span_extractions`; mark timestamps |
| Modify | `app/api/routes_ingestion.py` | `_chunk_and_embed`: mark `chunked_at` / `embedded_at` |
| Modify | `app/api/routes_claims.py` | Add `run_id` to `ExtractionSummary`; populate from graph final state |
| Modify | `app/main.py` | Call `configure_logging()` first in lifespan |
| Modify | `app/cli/main.py` | Call `configure_logging()` at startup; register `runs` sub-app |
| Modify | `app/cli/db.py` | Add `list_runs()` + `show_run()` async readers |
| Modify | `app/cli/render.py` | Add `render_runs_list()` + `render_run_detail()` |
| Create | `tests/test_observability_context.py` | Unit tests: bind/reset semantics, gather isolation |
| Create | `tests/test_observability_logger.py` | Unit tests: idempotency, JSON format, filter injection, filter survival |
| Create | `tests/test_observability_tracer.py` | Integration tests: rows written correctly; DB errors swallowed |
| Create | `tests/test_cli_runs.py` | Integration e2e: `runs list`, `runs show`, missing run, JSON output |
| Modify | `tests/test_claims_extraction.py` (or existing extraction test file) | Add: `span_extractions` rows, `run_id` in summary, `*_at` timestamps |
| Modify | `tests/test_ingestion.py` (or existing ingestion test file) | Add: `chunked_at` / `embedded_at` populated |
| Modify | `TODO.md` | Append deferred observability work |

---

## Task 0: Pre-flight — Refresh Index and Baseline

**Files:** None (setup only)

- [ ] **Step 1: Refresh the GitNexus index**

```bash
cd /path/to/Nexus  # parent repo root (not the worktree)
npx gitnexus analyze
```

Expected: index updated to current HEAD. You will see a summary of symbols indexed.

- [ ] **Step 2: Confirm worktree and branch**

```bash
cd .claude/worktrees/observability
git branch --show-current
git log --oneline -3
```

Expected:
```
observability
647afc3 docs(observability): spec — centralized logger & DB-backed tracer
819fb49 feat: add meaningful code quality checkstyles ...
```

- [ ] **Step 3: Run baseline tests**

```bash
cd .claude/worktrees/observability
python -m pytest tests/ -x -q --timeout=60 2>&1 | tail -10
```

Expected: all existing tests pass with 0 failures. If any fail, fix before continuing.

---

## Task 1: Migration 0002 — Schema Additions

**Files:**
- Create: `app/db/migrations/versions/0002_observability.py`

> No impact analysis needed — new file only.

- [ ] **Step 1: Write the migration**

Create `app/db/migrations/versions/0002_observability.py`:

```python
"""Add observability columns: agent_runs correlation, span_extractions, documents timestamps."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # agent_runs: correlation columns + token split
    op.add_column("agent_runs", sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("agent_runs", sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("agent_runs", sa.Column("span_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("agent_runs", sa.Column("prompt_tokens", sa.Integer, nullable=True))
    op.add_column("agent_runs", sa.Column("completion_tokens", sa.Integer, nullable=True))
    op.create_index("ix_agent_runs_run_id", "agent_runs", ["run_id"])

    # documents: per-stage timestamps
    op.add_column("documents", sa.Column("chunked_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("embedded_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("extraction_started_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("extraction_completed_at", sa.TIMESTAMP(timezone=True), nullable=True))

    # span_extractions: new table
    op.create_table(
        "span_extractions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("span_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("spans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="1"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_span_extractions_run_id", "span_extractions", ["run_id"])
    op.create_index("ix_span_extractions_document_span", "span_extractions", ["document_id", "span_id"])
    op.create_index("ix_span_extractions_status", "span_extractions", ["status"])


def downgrade() -> None:
    op.drop_table("span_extractions")
    op.drop_index("ix_agent_runs_run_id", table_name="agent_runs")
    op.drop_column("agent_runs", "run_id")
    op.drop_column("agent_runs", "document_id")
    op.drop_column("agent_runs", "span_id")
    op.drop_column("agent_runs", "prompt_tokens")
    op.drop_column("agent_runs", "completion_tokens")
    op.drop_column("documents", "chunked_at")
    op.drop_column("documents", "embedded_at")
    op.drop_column("documents", "extraction_started_at")
    op.drop_column("documents", "extraction_completed_at")
```

- [ ] **Step 2: Run migration to verify it applies cleanly**

```bash
python -m alembic upgrade head
```

Expected: `Running upgrade 0001 -> 0002, Add observability columns...` with exit 0.

- [ ] **Step 3: Verify downgrade works**

```bash
python -m alembic downgrade 0001
python -m alembic upgrade head
```

Expected: both commands exit 0.

- [ ] **Step 4: Commit**

```bash
git add app/db/migrations/versions/0002_observability.py
git commit -m "feat(db): migration 0002 — observability schema (agent_runs correlation, span_extractions, documents.*_at)"
```

---

## Task 2: Update `app/db/models.py`

**Files:**
- Modify: `app/db/models.py`

> Run `gitnexus_impact({target: "AgentRun", repo: "Nexus"})` and `gitnexus_impact({target: "Document", repo: "Nexus"})` before editing. Report blast radius.

- [ ] **Step 1: Add new columns to `Document` (after `status` field, line ~57)**

In `app/db/models.py`, add four nullable timestamp columns to `Document`:

```python
    status: Mapped[str] = mapped_column(Text, nullable=False, default="fetched")
    chunked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    embedded_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    extraction_started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    extraction_completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
```

- [ ] **Step 2: Add new columns to `AgentRun` (after `status` field, before `created_at`)**

```python
    status: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    span_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow
    )
```

- [ ] **Step 3: Add `SpanExtraction` model at the bottom of `app/db/models.py`**

```python
class SpanExtraction(Base):
    __tablename__ = "span_extractions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    span_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spans.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow
    )
```

- [ ] **Step 4: Verify models import cleanly**

```bash
python -c "from app.db.models import AgentRun, Document, SpanExtraction; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Run existing tests to confirm no regressions**

```bash
python -m pytest tests/ -x -q --timeout=60 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 6: Run `gitnexus_detect_changes()`**

Use the GitNexus MCP tool to confirm only `AgentRun`, `Document`, `SpanExtraction` symbols appear in the diff. No unexpected symbols.

- [ ] **Step 7: Commit**

```bash
git add app/db/models.py
git commit -m "feat(models): add SpanExtraction model; AgentRun + Document observability columns"
```

---

## Task 3: `app/observability/run_context.py` + Tests

**Files:**
- Create: `app/observability/__init__.py`
- Create: `app/observability/run_context.py`
- Create: `tests/test_observability_context.py`

> No impact analysis needed — new files only.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_observability_context.py`:

```python
"""Unit tests for run_context — no DB required."""
from __future__ import annotations

import asyncio
import random
import uuid

import pytest

from app.observability.run_context import (
    current_context,
    extraction_run,
    span_scope,
)


@pytest.mark.asyncio
async def test_extraction_run_binds_run_id_and_document_id():
    doc_id = uuid.uuid4()
    async with extraction_run(doc_id) as run_id:
        ctx = current_context()
        assert ctx["run_id"] == run_id
        assert ctx["document_id"] == doc_id
        assert ctx["span_id"] is None


@pytest.mark.asyncio
async def test_extraction_run_resets_on_exit():
    doc_id = uuid.uuid4()
    async with extraction_run(doc_id):
        pass
    ctx = current_context()
    assert ctx["run_id"] is None
    assert ctx["document_id"] is None


@pytest.mark.asyncio
async def test_span_scope_binds_span_id():
    doc_id = uuid.uuid4()
    span_id = uuid.uuid4()
    async with extraction_run(doc_id):
        async with span_scope(span_id):
            assert current_context()["span_id"] == span_id
        assert current_context()["span_id"] is None


@pytest.mark.asyncio
async def test_span_scope_resets_on_exception():
    doc_id = uuid.uuid4()
    span_id = uuid.uuid4()
    async with extraction_run(doc_id):
        try:
            async with span_scope(span_id):
                raise ValueError("boom")
        except ValueError:
            pass
        assert current_context()["span_id"] is None


@pytest.mark.asyncio
async def test_no_context_bleed_under_gather():
    """Each gather task must see only its own span_id — no cross-task leakage."""
    doc_id = uuid.uuid4()
    span_ids = [uuid.uuid4() for _ in range(20)]

    async def task(sid: uuid.UUID) -> uuid.UUID | None:
        async with span_scope(sid):
            await asyncio.sleep(0.001 * random.randint(1, 5))
            return current_context()["span_id"]

    async with extraction_run(doc_id):
        results = await asyncio.gather(*[task(sid) for sid in span_ids])

    assert results == span_ids


@pytest.mark.asyncio
async def test_current_context_outside_any_scope_returns_nones():
    ctx = current_context()
    assert ctx == {"run_id": None, "document_id": None, "span_id": None}
```

- [ ] **Step 2: Run tests to confirm they fail (module not yet created)**

```bash
python -m pytest tests/test_observability_context.py -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError: No module named 'app.observability'`

- [ ] **Step 3: Create `app/observability/__init__.py`**

```python
"""Observability package: logger, run_context, tracer."""
```

- [ ] **Step 4: Create `app/observability/run_context.py`**

```python
"""Asyncio-safe context variables for pipeline correlation IDs."""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import AsyncIterator

run_id_var: ContextVar[uuid.UUID | None] = ContextVar("run_id", default=None)
document_id_var: ContextVar[uuid.UUID | None] = ContextVar("document_id", default=None)
span_id_var: ContextVar[uuid.UUID | None] = ContextVar("span_id", default=None)


@asynccontextmanager
async def extraction_run(document_id: uuid.UUID) -> AsyncIterator[uuid.UUID]:
    """Mint a run_id, bind run_id + document_id for the duration; Token-reset on exit."""
    run_id = uuid.uuid4()
    t_run = run_id_var.set(run_id)
    t_doc = document_id_var.set(document_id)
    try:
        yield run_id
    finally:
        run_id_var.reset(t_run)
        document_id_var.reset(t_doc)


@asynccontextmanager
async def span_scope(span_id: uuid.UUID) -> AsyncIterator[None]:
    """Bind span_id within an active extraction_run; Token-reset on exit."""
    token = span_id_var.set(span_id)
    try:
        yield
    finally:
        span_id_var.reset(token)


def current_context() -> dict[str, uuid.UUID | None]:
    """Snapshot {run_id, document_id, span_id} for log records / DB writes."""
    return {
        "run_id": run_id_var.get(),
        "document_id": document_id_var.get(),
        "span_id": span_id_var.get(),
    }
```

- [ ] **Step 5: Run tests — all must pass**

```bash
python -m pytest tests/test_observability_context.py -v 2>&1 | tail -15
```

Expected: `6 passed`

- [ ] **Step 6: Commit**

```bash
git add app/observability/__init__.py app/observability/run_context.py tests/test_observability_context.py
git commit -m "feat(observability): run_context — ContextVar binding + extraction_run/span_scope"
```

---

## Task 4: `app/observability/logger.py` + Tests

**Files:**
- Create: `app/observability/logger.py`
- Create: `tests/test_observability_logger.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_observability_logger.py`:

```python
"""Unit tests for configure_logging and RunContextFilter."""
from __future__ import annotations

import io
import json
import logging
import uuid

import pytest

from app.observability import logger as obs_logger
from app.observability.run_context import extraction_run, span_scope


@pytest.fixture(autouse=True)
def reset_logging():
    """Force logger reconfiguration between tests."""
    obs_logger._configured = False
    root = logging.getLogger()
    root.handlers.clear()
    yield
    obs_logger._configured = False
    root.handlers.clear()


def _capture_json_log(level: str = "DEBUG") -> tuple[logging.Logger, io.StringIO]:
    """Configure logging with a StringIO stream; return (test_logger, stream)."""
    obs_logger.configure_logging(level=level, fmt="json", force=True)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(obs_logger._make_json_formatter())
    test_logger = logging.getLogger("test.capture")
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.DEBUG)
    return test_logger, stream


def test_configure_logging_is_idempotent():
    obs_logger.configure_logging()
    handler_count = len(logging.getLogger().handlers)
    obs_logger.configure_logging()
    assert len(logging.getLogger().handlers) == handler_count


def test_configure_logging_force_reconfigures():
    obs_logger.configure_logging()
    obs_logger.configure_logging(force=True)
    # Should not raise; just verify it ran twice
    assert obs_logger._configured is True


def test_json_formatter_emits_required_fields():
    logger, stream = _capture_json_log()
    logger.info("hello world")
    record = json.loads(stream.getvalue().strip())
    assert record["msg"] == "hello world"
    assert record["level"] == "INFO"
    assert "ts" in record
    assert "logger" in record


def test_run_context_filter_injects_ids(event_loop):
    async def _inner():
        logger, stream = _capture_json_log()
        doc_id = uuid.uuid4()
        async with extraction_run(doc_id) as run_id:
            span_id = uuid.uuid4()
            async with span_scope(span_id):
                logger.info("inside scope")
        return json.loads(stream.getvalue().strip()), run_id, doc_id, span_id

    import asyncio
    record, run_id, doc_id, span_id = asyncio.get_event_loop().run_until_complete(_inner())
    assert record["run_id"] == str(run_id)
    assert record["document_id"] == str(doc_id)
    assert record["span_id"] == str(span_id)


def test_run_context_filter_survives_broken_contextvar(caplog):
    """Filter must return True (keep record) even if contextvar lookup fails."""
    from app.observability.logger import RunContextFilter

    f = RunContextFilter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="ok", args=(), exc_info=None,
    )
    # Simulate failure by patching current_context to raise
    import app.observability.logger as mod
    original = mod.current_context
    mod.current_context = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        result = f.filter(record)
    finally:
        mod.current_context = original
    assert result is True


def test_json_formatter_handles_non_serialisable_extra():
    logger, stream = _capture_json_log()
    logger.info("extra", extra={"obj": object()})
    record = json.loads(stream.getvalue().strip())
    assert "obj" in record  # repr fallback kept the field
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_observability_logger.py -v 2>&1 | tail -5
```

Expected: `ImportError` or `AttributeError` — `configure_logging` not yet defined.

- [ ] **Step 3: Create `app/observability/logger.py`**

```python
"""Centralized logging configuration for Nexus — stdlib + JSON formatter."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from app.observability.run_context import current_context

_configured = False


class RunContextFilter(logging.Filter):
    """Inject run_id, document_id, span_id from active contextvars into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            ctx = current_context()
            record.run_id = str(ctx["run_id"]) if ctx["run_id"] else None
            record.document_id = str(ctx["document_id"]) if ctx["document_id"] else None
            record.span_id = str(ctx["span_id"]) if ctx["span_id"] else None
        except Exception:
            record.run_id = None
            record.document_id = None
            record.span_id = None
        return True


class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record."""

    _SKIP = {"msg", "message", "args", "exc_info", "exc_text", "stack_info",
              "levelname", "levelno", "pathname", "filename", "module",
              "created", "msecs", "relativeCreated", "thread", "threadName",
              "processName", "process", "name", "funcName", "lineno",
              "taskName"}

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        payload: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.message,
            "run_id": getattr(record, "run_id", None),
            "document_id": getattr(record, "document_id", None),
            "span_id": getattr(record, "span_id", None),
        }
        for key, value in record.__dict__.items():
            if key not in self._SKIP and not key.startswith("_"):
                try:
                    json.dumps(value)
                    payload[key] = value
                except (TypeError, ValueError):
                    payload[key] = repr(value)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def _make_json_formatter() -> _JsonFormatter:
    return _JsonFormatter()


def configure_logging(
    level: str | None = None,
    fmt: str | None = None,
    *,
    force: bool = False,
) -> None:
    """Configure root logger with RunContextFilter and JSON (default) or console formatter.

    Idempotent — second call is a no-op unless force=True.
    Reads LOG_LEVEL (default INFO) and LOG_FORMAT (default 'json') from env.
    """
    global _configured
    if _configured and not force:
        return

    effective_level = (level or os.environ.get("LOG_LEVEL", "INFO")).upper()
    effective_fmt = fmt or os.environ.get("LOG_FORMAT", "json")

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(effective_level)

    handler = logging.StreamHandler()
    handler.setLevel(effective_level)

    if effective_fmt == "json":
        handler.setFormatter(_make_json_formatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s %(name)s %(message)s")
        )

    ctx_filter = RunContextFilter()
    root.addFilter(ctx_filter)
    root.addHandler(handler)
    _configured = True
```

- [ ] **Step 4: Run tests — all must pass**

```bash
python -m pytest tests/test_observability_logger.py -v 2>&1 | tail -10
```

Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add app/observability/logger.py tests/test_observability_logger.py
git commit -m "feat(observability): logger — JSON formatter + RunContextFilter + configure_logging"
```

---

## Task 5: `app/observability/tracer.py` + Tests

**Files:**
- Create: `app/observability/tracer.py`
- Create: `tests/test_observability_tracer.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_observability_tracer.py`:

```python
"""Integration tests for tracer.py — requires a running Postgres (via conftest.py)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import AgentRun, Document, Source, Span, SpanExtraction
from app.observability.run_context import extraction_run, span_scope
from app.observability.tracer import (
    mark_document_timestamp,
    record_agent_run,
    record_span_extraction,
)


@pytest_asyncio.fixture
async def source(session_factory):
    async with session_factory() as session:
        s = Source(name="test", source_type="manual", domain_pack="personal_ai_tech")
        session.add(s)
        await session.commit()
        await session.refresh(s)
        return s


@pytest_asyncio.fixture
async def document(session_factory, source):
    async with session_factory() as session:
        doc = Document(
            source_id=source.id,
            clean_text="hello",
            raw_text="hello",
            content_hash=f"hash-{uuid.uuid4()}",
            status="embedded",
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        return doc


@pytest_asyncio.fixture
async def span(session_factory, document):
    async with session_factory() as session:
        s = Span(document_id=document.id, span_index=0, text="hello", token_count=1)
        session.add(s)
        await session.commit()
        await session.refresh(s)
        return s


@pytest.mark.asyncio
async def test_record_agent_run_writes_row_with_context(session_factory, document, span):
    async with extraction_run(document.id) as run_id:
        async with span_scope(span.id):
            await record_agent_run(
                session_factory,
                run_type="claim_extraction",
                model="deepseek/test",
                input_payload={"system": "sys", "user": "usr"},
                raw_output='{"claims": []}',
                total_tokens=100,
                status="success",
                prompt_tokens=60,
                completion_tokens=40,
            )

    async with session_factory() as session:
        row = (await session.execute(select(AgentRun))).scalar_one()

    assert row.run_id == run_id
    assert row.document_id == document.id
    assert row.span_id == span.id
    assert row.prompt_tokens == 60
    assert row.completion_tokens == 40
    assert row.input_json == {"system": "sys", "user": "usr"}
    assert row.output_json == {"raw": '{"claims": []}'}
    assert row.status == "success"


@pytest.mark.asyncio
async def test_record_agent_run_stores_full_payload_without_truncation(session_factory, document):
    long_text = "x" * 2000
    async with extraction_run(document.id):
        await record_agent_run(
            session_factory,
            run_type="claim_extraction",
            model="m",
            input_payload={"system": long_text, "user": long_text},
            raw_output=long_text,
            total_tokens=1,
            status="success",
        )

    async with session_factory() as session:
        row = (await session.execute(select(AgentRun))).scalar_one()

    assert row.input_json["system"] == long_text
    assert row.output_json["raw"] == long_text


@pytest.mark.asyncio
async def test_record_agent_run_swallows_db_error(caplog):
    broken_sf = MagicMock()
    broken_cm = AsyncMock()
    broken_cm.__aenter__ = AsyncMock(side_effect=RuntimeError("DB down"))
    broken_sf.return_value = broken_cm

    import logging
    with caplog.at_level(logging.WARNING, logger="app.observability.tracer"):
        await record_agent_run(
            broken_sf,
            run_type="claim_extraction",
            model="m",
            input_payload={},
            raw_output=None,
            total_tokens=0,
            status="success",
        )
    assert "record_agent_run failed" in caplog.text


@pytest.mark.asyncio
async def test_record_span_extraction_writes_row(session_factory, document, span):
    run_id = uuid.uuid4()
    await record_span_extraction(
        session_factory,
        run_id=run_id,
        span_id=span.id,
        document_id=document.id,
        status="success",
        attempts=2,
    )

    async with session_factory() as session:
        row = (await session.execute(select(SpanExtraction))).scalar_one()

    assert row.run_id == run_id
    assert row.span_id == span.id
    assert row.document_id == document.id
    assert row.status == "success"
    assert row.attempts == 2
    assert row.error is None


@pytest.mark.asyncio
async def test_record_span_extraction_captures_error(session_factory, document, span):
    await record_span_extraction(
        session_factory,
        run_id=uuid.uuid4(),
        span_id=span.id,
        document_id=document.id,
        status="llm_error",
        attempts=3,
        error="OpenRouter 400: bad request",
    )

    async with session_factory() as session:
        row = (await session.execute(select(SpanExtraction))).scalar_one()

    assert row.status == "llm_error"
    assert row.error == "OpenRouter 400: bad request"


@pytest.mark.asyncio
async def test_mark_document_timestamp_sets_field(session_factory, document):
    await mark_document_timestamp(session_factory, document.id, "chunked_at")

    async with session_factory() as session:
        doc = await session.get(Document, document.id)

    assert doc.chunked_at is not None
    assert isinstance(doc.chunked_at, datetime)


@pytest.mark.asyncio
async def test_mark_document_timestamp_swallows_db_error(caplog):
    broken_sf = MagicMock()
    broken_cm = AsyncMock()
    broken_cm.__aenter__ = AsyncMock(side_effect=RuntimeError("DB down"))
    broken_sf.return_value = broken_cm

    import logging
    with caplog.at_level(logging.WARNING, logger="app.observability.tracer"):
        await mark_document_timestamp(broken_sf, uuid.uuid4(), "chunked_at")
    assert "mark_document_timestamp failed" in caplog.text
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_observability_tracer.py -v 2>&1 | tail -5
```

Expected: `ImportError` — `app.observability.tracer` not yet defined.

- [ ] **Step 3: Create `app/observability/tracer.py`**

```python
"""Thin DB-writing helpers for pipeline audit — never raises, always logs on failure."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from app.db.models import AgentRun, Document, SpanExtraction
from app.observability.run_context import current_context

logger = logging.getLogger(__name__)

_TIMESTAMP_FIELDS = Literal[
    "chunked_at", "embedded_at", "extraction_started_at", "extraction_completed_at"
]


async def record_agent_run(
    session_factory,
    *,
    run_type: str,
    model: str,
    input_payload: dict,
    raw_output: str | None,
    total_tokens: int,
    status: str,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> None:
    """Insert one agent_runs row. Reads run_id/document_id/span_id from contextvars.
    Catches and logs DB errors; never raises."""
    ctx = current_context()
    cost = total_tokens * (0.14 / 1_000_000)
    try:
        async with session_factory() as session:
            session.add(AgentRun(
                run_type=run_type,
                model=model,
                input_json=input_payload,
                output_json={"raw": raw_output},
                cost_estimate=cost,
                status=status,
                run_id=ctx["run_id"],
                document_id=ctx["document_id"],
                span_id=ctx["span_id"],
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            ))
            await session.commit()
    except Exception:
        logger.exception(
            "record_agent_run failed",
            extra={"run_type": run_type, "status": status},
        )


async def record_span_extraction(
    session_factory,
    *,
    run_id: uuid.UUID,
    span_id: uuid.UUID,
    document_id: uuid.UUID,
    status: str,
    attempts: int,
    error: str | None = None,
) -> None:
    """Insert one span_extractions row. Catches and logs DB errors; never raises."""
    try:
        async with session_factory() as session:
            session.add(SpanExtraction(
                run_id=run_id,
                span_id=span_id,
                document_id=document_id,
                status=status,
                attempts=attempts,
                error=error,
            ))
            await session.commit()
    except Exception:
        logger.exception(
            "record_span_extraction failed",
            extra={"span_id": str(span_id), "status": status},
        )


async def mark_document_timestamp(
    session_factory,
    document_id: uuid.UUID,
    field: _TIMESTAMP_FIELDS,
) -> None:
    """Set one *_at timestamp column on a Document row. Catches and logs DB errors; never raises."""
    try:
        async with session_factory() as session:
            doc = await session.get(Document, document_id)
            if doc is not None:
                setattr(doc, field, datetime.now(timezone.utc))
                await session.commit()
    except Exception:
        logger.exception(
            "mark_document_timestamp failed",
            extra={"document_id": str(document_id), "field": field},
        )
```

- [ ] **Step 4: Run tests — all must pass**

```bash
python -m pytest tests/test_observability_tracer.py -v 2>&1 | tail -10
```

Expected: `8 passed`

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest tests/ -x -q --timeout=60 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app/observability/tracer.py tests/test_observability_tracer.py
git commit -m "feat(observability): tracer — record_agent_run, record_span_extraction, mark_document_timestamp"
```

---

## Task 6: Wire `LLMClient` to Tracer

**Files:**
- Modify: `app/intelligence/llm_client.py`

> Run `gitnexus_impact({target: "LLMClient", repo: "Nexus"})` and `gitnexus_impact({target: "complete_json", repo: "Nexus"})` before editing. Report blast radius.

- [ ] **Step 1: Write the updated test expectations**

In the existing LLM-client test file (locate via `grep -r "complete_json\|LLMClient" tests/`), add or update:

```python
@pytest.mark.asyncio
async def test_agent_run_stores_full_payload_without_truncation(session_factory):
    """After the tracer switch, input/output must not be truncated to 300/500 chars."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.intelligence.llm_client import ExtractionOutput, LLMClient

    long_prompt = "A" * 2000
    fake_response = {
        "choices": [{"message": {"content": '{"claims": []}'}}],
        "usage": {"total_tokens": 10, "prompt_tokens": 6, "completion_tokens": 4},
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_response

    client = LLMClient(api_key="test-key", session_factory=session_factory)
    with patch("httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__ = AsyncMock(return_value=mock_http.return_value)
        mock_http.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.return_value.post = AsyncMock(return_value=mock_resp)
        await client.complete_json(
            model="m", system=long_prompt, user=long_prompt,
            response_model=ExtractionOutput,
        )

    async with session_factory() as session:
        from sqlalchemy import select
        from app.db.models import AgentRun
        row = (await session.execute(select(AgentRun))).scalar_one()

    assert row.input_json["system"] == long_prompt
    assert row.prompt_tokens == 6
    assert row.completion_tokens == 4


@pytest.mark.asyncio
async def test_agent_run_split_tokens_populated(session_factory):
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.intelligence.llm_client import ExtractionOutput, LLMClient

    fake_response = {
        "choices": [{"message": {"content": '{"claims": []}'}}],
        "usage": {"total_tokens": 15, "prompt_tokens": 10, "completion_tokens": 5},
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_response

    client = LLMClient(api_key="test-key", session_factory=session_factory)
    with patch("httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__ = AsyncMock(return_value=mock_http.return_value)
        mock_http.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.return_value.post = AsyncMock(return_value=mock_resp)
        await client.complete_json(
            model="m", system="s", user="u", response_model=ExtractionOutput,
        )

    async with session_factory() as session:
        from sqlalchemy import select
        from app.db.models import AgentRun
        row = (await session.execute(select(AgentRun))).scalar_one()

    assert row.prompt_tokens == 10
    assert row.completion_tokens == 5
```

- [ ] **Step 2: Run those new tests — they should FAIL (old code truncates)**

```bash
python -m pytest tests/ -k "test_agent_run_stores_full" -v 2>&1 | tail -5
```

Expected: assertion error on truncated input.

- [ ] **Step 3: Rewrite `app/intelligence/llm_client.py`**

Replace the file with this content (preserving all existing error classes and schema models, replacing only `LLMClient`):

```python
"""OpenRouter HTTP client with per-call tracer logging."""

from __future__ import annotations

from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.observability.tracer import record_agent_run

_BASE_URL = "https://openrouter.ai/api/v1"
_TIMEOUT = httpx.Timeout(60.0)
_COST_PER_TOKEN_USD = 0.14 / 1_000_000

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Non-retriable LLM error (4xx or unexpected response structure)."""


class LLMNetworkError(LLMError):
    """5xx or connection failure — callers should abort the pipeline."""


class LLMSchemaError(LLMError):
    """Response arrived but failed Pydantic validation.

    The raw model output is preserved on `raw_output` so callers can include it
    in a correction prompt.
    """

    def __init__(self, message: str, raw_output: str = "") -> None:
        super().__init__(message)
        self.raw_output = raw_output


class LLMClient:
    """Async OpenRouter client. Records every call to agent_runs via tracer."""

    def __init__(self, api_key: str, session_factory: Any) -> None:
        self._api_key = api_key
        self._session_factory = session_factory

    async def complete_json(
        self,
        *,
        model: str,
        system: str,
        user: str,
        response_model: type[T],
        temperature: float = 0.1,
        max_tokens: int = 2000,
    ) -> tuple[T, int]:
        """Call OpenRouter and return (validated_result, total_tokens).

        Raises LLMNetworkError on 5xx / connection failure.
        Raises LLMError on 4xx.
        Raises LLMSchemaError if the response fails Pydantic validation.
        Always records an agent_runs row (even on failure).
        """
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        raw_output: str | None = None
        total_tokens = 0
        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        call_status = "success"

        try:
            async with httpx.AsyncClient(
                base_url=_BASE_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=_TIMEOUT,
            ) as http:
                resp = await http.post("/chat/completions", json=payload)

            if resp.status_code >= 500:
                call_status = f"http_{resp.status_code}"
                raise LLMNetworkError(f"OpenRouter {resp.status_code}: {resp.text[:300]}")

            if resp.status_code >= 400:
                call_status = f"http_{resp.status_code}"
                raise LLMError(f"OpenRouter {resp.status_code}: {resp.text[:300]}")

            data = resp.json()
            try:
                raw_output = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                call_status = "malformed_response"
                raise LLMError(f"Malformed OpenRouter response: {exc}") from exc

            usage = data.get("usage", {})
            total_tokens = usage.get("total_tokens", 0)
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")

        except httpx.HTTPError as exc:
            call_status = "network_error"
            raise LLMNetworkError(str(exc)) from exc

        finally:
            await record_agent_run(
                self._session_factory,
                run_type="claim_extraction",
                model=model,
                input_payload={"system": system, "user": user},
                raw_output=raw_output,
                total_tokens=total_tokens,
                status=call_status,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        if raw_output is None:
            raise LLMSchemaError("LLM returned null content", raw_output="")

        try:
            validated = response_model.model_validate_json(raw_output)
        except (ValueError, ValidationError) as exc:
            raise LLMSchemaError(
                f"Schema validation failed: {exc}. Raw: {raw_output[:200]}",
                raw_output=raw_output,
            ) from exc

        return validated, total_tokens


# ---------------------------------------------------------------------------
# Extraction schema
# ---------------------------------------------------------------------------

from typing import Literal  # noqa: E402

ClaimType = Literal[
    "model_release", "benchmark_result", "product_launch", "pricing_change",
    "research_finding", "infrastructure_update", "security_issue", "funding_event",
    "regulation", "forecast", "other",
]


class ExtractedClaim(BaseModel):
    claim_text: str
    claim_type: ClaimType
    entities: list[str]
    topics: list[str]
    confidence: float
    rationale: str


class ExtractionOutput(BaseModel):
    claims: list[ExtractedClaim]
```

- [ ] **Step 4: Run all tests**

```bash
python -m pytest tests/ -x -q --timeout=60 2>&1 | tail -8
```

Expected: all pass.

- [ ] **Step 5: Run `gitnexus_detect_changes()`**

Confirm only `LLMClient`, `complete_json`, and `_log` (removed) appear in the diff.

- [ ] **Step 6: Commit**

```bash
git add app/intelligence/llm_client.py
git commit -m "feat(llm): replace _log with tracer.record_agent_run; remove truncation; split token accounting"
```

---

## Task 7: Wire Extraction Graph

**Files:**
- Modify: `app/intelligence/extraction.py`

> Run `gitnexus_impact({target: "make_extraction_graph", repo: "Nexus"})` and `gitnexus_impact({target: "_extract_one_span", repo: "Nexus"})`. Report blast radius.

- [ ] **Step 1: Write the new test expectations**

Add to the extraction test file (find with `grep -rl "make_extraction_graph\|extract_claims" tests/`):

```python
@pytest.mark.asyncio
async def test_extraction_populates_span_extractions_table(
    session_factory, client_with_embedder, httpx_mock
):
    """After extraction, one span_extractions row per span must exist."""
    # This test requires a document at 'embedded' status with at least one span.
    # Use the existing fixture pattern from test_claims_extraction.py.
    # Seed a doc, get it to embedded, then call extract_claims.
    # Then query span_extractions and assert len == number of spans.
    from sqlalchemy import select
    from app.db.models import SpanExtraction
    # ... (follow existing test pattern for seeding + extraction) ...
    # After extraction:
    async with session_factory() as session:
        rows = (await session.execute(select(SpanExtraction))).scalars().all()
    assert len(rows) >= 1
    assert all(r.run_id is not None for r in rows)
    assert all(r.document_id is not None for r in rows)


@pytest.mark.asyncio
async def test_extraction_populates_document_timestamps(session_factory, ...):
    """extraction_started_at and extraction_completed_at must be set after extraction."""
    from app.db.models import Document
    # After extraction:
    async with session_factory() as session:
        doc = await session.get(Document, document_id)
    assert doc.extraction_started_at is not None
    assert doc.extraction_completed_at is not None
    assert doc.extraction_completed_at >= doc.extraction_started_at


@pytest.mark.asyncio
async def test_extraction_summary_includes_run_id(client_with_embedder, ...):
    """ExtractionSummary response must include a non-null run_id UUID."""
    resp = await client_with_embedder.post(f"/documents/{doc_id}/extract-claims")
    assert resp.status_code == 200
    body = resp.json()
    assert "run_id" in body
    import uuid
    uuid.UUID(body["run_id"])  # must be a valid UUID
```

- [ ] **Step 2: Run these tests — they should fail**

```bash
python -m pytest tests/ -k "span_extractions or document_timestamps or run_id" -v 2>&1 | tail -8
```

Expected: failures because `run_id` not in response, `span_extractions` empty.

- [ ] **Step 3: Rewrite `app/intelligence/extraction.py`**

Replace the file with:

```python
"""LangGraph extraction graph for per-span concurrent claim extraction."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import Claim, ClaimEvidence, Document, Span
from app.intelligence.llm_client import (
    ExtractionOutput,
    LLMError,
    LLMNetworkError,
    LLMSchemaError,
)
from app.intelligence.prompts.extract_claims import (
    SYSTEM_PROMPT,
    build_correction_prompt,
    build_user_prompt,
)
from app.observability.run_context import extraction_run, span_scope
from app.observability.tracer import mark_document_timestamp, record_span_extraction

_MAX_RETRIES = 2

STATUS_EMBEDDED = "embedded"
STATUS_CLAIMS_EXTRACTED = "claims_extracted"
STATUS_EXTRACTION_PARTIAL = "extraction_partial"
STATUS_EXTRACTION_FAILED = "extraction_failed"

POST_EXTRACTION_STATUSES = (
    STATUS_EMBEDDED,
    STATUS_CLAIMS_EXTRACTED,
    STATUS_EXTRACTION_PARTIAL,
    STATUS_EXTRACTION_FAILED,
)


class ExtractionState(TypedDict):
    document_id: uuid.UUID
    run_id: uuid.UUID | None
    model: str
    spans: list[dict]
    results: list[dict]
    stored_claim_ids: list[uuid.UUID]
    total_tokens: int
    error: str | None


async def _extract_one_span(
    span: dict,
    client: Any,
    model: str,
    session_factory: async_sessionmaker,
    run_id: uuid.UUID,
    document_id: uuid.UUID,
) -> dict:
    """Extract claims from one span with correction-prompt retry (max _MAX_RETRIES).

    Binds span_id in run_context for the duration so all log lines and the
    agent_runs row carry the correct span correlation.
    """
    span_id = uuid.UUID(span["id"])
    user = build_user_prompt(span["text"], span.get("metadata_json") or {})
    total_tokens = 0
    attempts = 0

    async with span_scope(span_id):
        for attempt in range(_MAX_RETRIES + 1):
            attempts += 1
            try:
                result, tokens = await client.complete_json(
                    model=model,
                    system=SYSTEM_PROMPT,
                    user=user,
                    response_model=ExtractionOutput,
                )
                total_tokens += tokens
                await record_span_extraction(
                    session_factory,
                    run_id=run_id,
                    span_id=span_id,
                    document_id=document_id,
                    status="success",
                    attempts=attempts,
                )
                return {
                    "span_id": span["id"],
                    "claims": [c.model_dump() for c in result.claims],
                    "tokens": total_tokens,
                    "error": None,
                }
            except LLMNetworkError:
                raise
            except LLMSchemaError as exc:
                if attempt < _MAX_RETRIES:
                    user = build_correction_prompt(user, exc.raw_output, str(exc))
                    continue
                await record_span_extraction(
                    session_factory,
                    run_id=run_id,
                    span_id=span_id,
                    document_id=document_id,
                    status="schema_error",
                    attempts=attempts,
                    error=str(exc),
                )
                return {"span_id": span["id"], "claims": [], "tokens": total_tokens, "error": str(exc)}
            except LLMError as exc:
                await record_span_extraction(
                    session_factory,
                    run_id=run_id,
                    span_id=span_id,
                    document_id=document_id,
                    status="llm_error",
                    attempts=attempts,
                    error=str(exc),
                )
                return {"span_id": span["id"], "claims": [], "tokens": total_tokens, "error": str(exc)}

    return {"span_id": span["id"], "claims": [], "tokens": total_tokens, "error": "unreachable"}


def make_extraction_graph(session_factory: async_sessionmaker, client: Any):  # noqa: C901
    """Build and compile the LangGraph extraction graph."""

    async def load_spans(state: ExtractionState) -> dict:
        async with session_factory() as session:
            doc = await session.get(Document, state["document_id"])
            if doc is None:
                return {"error": f"Document {state['document_id']} not found", "run_id": None}
            if doc.status != STATUS_EMBEDDED:
                return {"error": f"Document status is '{doc.status}'; must be 'embedded'", "run_id": None}
            rows = (
                (
                    await session.execute(
                        select(Span)
                        .where(Span.document_id == state["document_id"])
                        .order_by(Span.span_index)
                    )
                )
                .scalars()
                .all()
            )
            spans = [
                {"id": str(s.id), "text": s.text, "token_count": s.token_count, "metadata_json": s.metadata_json}
                for s in rows
            ]

        # Acquire run_id here — it will be used by all subsequent nodes via state.
        # The extraction_run context manager is entered in run_with_context() below.
        await mark_document_timestamp(session_factory, state["document_id"], "extraction_started_at")
        return {"spans": spans}

    async def extract_spans(state: ExtractionState) -> dict:
        if state.get("error"):
            return {}

        run_id = state.get("run_id")
        semaphore = asyncio.Semaphore(5)

        async def bounded(span: dict) -> dict:
            async with semaphore:
                return await _extract_one_span(
                    span, client, state["model"], session_factory,
                    run_id=run_id, document_id=state["document_id"],
                )

        try:
            results = list(await asyncio.gather(*[bounded(s) for s in state["spans"]]))
        except LLMNetworkError as exc:
            return {"error": str(exc), "results": []}

        total = sum(r.get("tokens", 0) for r in results)
        return {"results": results, "total_tokens": total}

    async def store_claims(state: ExtractionState) -> dict:
        async with session_factory() as session:
            claims_to_add: list[Claim] = []
            evidence_to_add: list[ClaimEvidence] = []
            stored_ids: list[uuid.UUID] = []

            for result in state.get("results", []):
                if result.get("error"):
                    continue
                span_id = uuid.UUID(result["span_id"])
                for claim_data in result.get("claims", []):
                    claim_id = uuid.uuid4()
                    claims_to_add.append(Claim(
                        id=claim_id,
                        document_id=state["document_id"],
                        claim_text=claim_data["claim_text"],
                        claim_type=claim_data["claim_type"],
                        entities_json=claim_data.get("entities"),
                        topics_json=claim_data.get("topics"),
                        confidence=claim_data.get("confidence"),
                        status="active",
                    ))
                    evidence_to_add.append(ClaimEvidence(
                        claim_id=claim_id,
                        span_id=span_id,
                        evidence_role="support",
                        confidence=claim_data.get("confidence"),
                    ))
                    stored_ids.append(claim_id)

            if claims_to_add:
                session.add_all(claims_to_add)
                session.add_all(evidence_to_add)
                await session.commit()
        return {"stored_claim_ids": stored_ids}

    async def update_status(state: ExtractionState) -> dict:
        if state.get("error"):
            new_status = STATUS_EXTRACTION_FAILED
        else:
            results = state.get("results", [])
            if not results:
                new_status = STATUS_EXTRACTION_FAILED
            else:
                failed = sum(1 for r in results if r.get("error"))
                if failed == 0:
                    new_status = STATUS_CLAIMS_EXTRACTED
                elif failed < len(results):
                    new_status = STATUS_EXTRACTION_PARTIAL
                else:
                    new_status = STATUS_EXTRACTION_FAILED

        async with session_factory() as session:
            doc = await session.get(Document, state["document_id"])
            if doc:
                doc.status = new_status
                await session.commit()

        await mark_document_timestamp(session_factory, state["document_id"], "extraction_completed_at")
        return {}

    def _route_after_extract(state: ExtractionState) -> str:
        return "update_status" if state.get("error") else "store_claims"

    builder = StateGraph(ExtractionState)
    builder.add_node("load_spans", load_spans)
    builder.add_node("extract_spans", extract_spans)
    builder.add_node("store_claims", store_claims)
    builder.add_node("update_status", update_status)

    builder.set_entry_point("load_spans")
    builder.add_edge("load_spans", "extract_spans")
    builder.add_conditional_edges(
        "extract_spans",
        _route_after_extract,
        {"store_claims": "store_claims", "update_status": "update_status"},
    )
    builder.add_edge("store_claims", "update_status")
    builder.add_edge("update_status", END)

    return builder.compile()


async def run_with_context(graph, document_id: uuid.UUID, model: str) -> dict:
    """Enter extraction_run context, invoke the graph, return final state with run_id."""
    async with extraction_run(document_id) as run_id:
        final = await graph.ainvoke({
            "document_id": document_id,
            "run_id": run_id,
            "model": model,
            "spans": [],
            "results": [],
            "stored_claim_ids": [],
            "total_tokens": 0,
            "error": None,
        })
    final["run_id"] = run_id
    return final
```

- [ ] **Step 4: Run all tests**

```bash
python -m pytest tests/ -x -q --timeout=60 2>&1 | tail -8
```

Expected: all pass.

- [ ] **Step 5: Run `gitnexus_detect_changes()`**

Confirm affected symbols: `make_extraction_graph`, `_extract_one_span`, `ExtractionState`, new `run_with_context`. No unexpected symbols.

- [ ] **Step 6: Commit**

```bash
git add app/intelligence/extraction.py
git commit -m "feat(extraction): wire extraction_run/span_scope, record span_extractions, mark *_at timestamps"
```

---

## Task 8: Wire `routes_claims.py` — `ExtractionSummary.run_id` + `run_with_context`

**Files:**
- Modify: `app/api/routes_claims.py`

> Run `gitnexus_impact({target: "extract_claims", repo: "Nexus"})`. Report blast radius.

- [ ] **Step 1: Update `ExtractionSummary` and the route handler**

In `app/api/routes_claims.py`, make these changes:

```python
# 1. Add run_id to ExtractionSummary
class ExtractionSummary(BaseModel):
    document_id: uuid.UUID
    run_id: uuid.UUID                # NEW
    claims_extracted: int
    spans_processed: int
    spans_failed: int
    tokens_used: int
    cost_estimate_usd: float
    claim_ids: list[uuid.UUID]

# 2. Replace the graph.ainvoke call with run_with_context
from app.intelligence.extraction import (
    POST_EXTRACTION_STATUSES,
    STATUS_EMBEDDED,
    make_extraction_graph,
    run_with_context,       # NEW import
)

# In extract_claims route, replace:
#   final = await graph.ainvoke({...})
# with:
    graph = make_extraction_graph(request.app.state.session_factory, llm_client)
    final = await run_with_context(graph, document_id, settings.t2_model)

# 3. Add run_id to the returned ExtractionSummary
    return ExtractionSummary(
        document_id=document_id,
        run_id=final["run_id"],         # NEW
        claims_extracted=len(claim_ids),
        spans_processed=len(results),
        spans_failed=spans_failed,
        tokens_used=total_tokens,
        cost_estimate_usd=round(total_tokens * _COST_PER_TOKEN_USD, 6),
        claim_ids=claim_ids,
    )
```

- [ ] **Step 2: Run all tests**

```bash
python -m pytest tests/ -x -q --timeout=60 2>&1 | tail -8
```

Expected: all pass. The `test_extraction_summary_includes_run_id` test from Task 7 now passes.

- [ ] **Step 3: Commit**

```bash
git add app/api/routes_claims.py
git commit -m "feat(api): add run_id to ExtractionSummary; use run_with_context"
```

---

## Task 9: Wire `_chunk_and_embed` Timestamps

**Files:**
- Modify: `app/api/routes_ingestion.py`

> Run `gitnexus_impact({target: "_chunk_and_embed", repo: "Nexus"})`. Report blast radius.

- [ ] **Step 1: Add timestamp marks to `_chunk_and_embed`**

In `app/api/routes_ingestion.py`, add the import and two `mark_document_timestamp` calls:

```python
# At top, add:
from app.observability.tracer import mark_document_timestamp

# In _chunk_and_embed, after the chunk commit block (line ~76), add:
        await mark_document_timestamp(session_factory, doc_id, "chunked_at")

# After the embed commit (line ~100), add:
        await mark_document_timestamp(session_factory, doc_id, "embedded_at")
```

The full modified section looks like:

```python
        doc.status = "chunked"
        for s in spans_data:
            session.add(Span(...))
        await session.commit()
    await mark_document_timestamp(session_factory, doc_id, "chunked_at")   # NEW

    if not spans_data or embedder is None:
        return

    async with session_factory() as session:
        # ... embed logic ...
        doc = await session.get(Document, doc_id)
        if doc:
            doc.status = "embedded"
        await session.commit()
    await mark_document_timestamp(session_factory, doc_id, "embedded_at")  # NEW
```

- [ ] **Step 2: Write and run a test**

Add to the ingestion test file:

```python
@pytest.mark.asyncio
async def test_chunk_embed_sets_timestamps(client_with_embedder, session_factory):
    """chunked_at and embedded_at must be set after background processing."""
    from sqlalchemy import select
    from app.db.models import Document, Source

    # Create a source and ingest text (triggers _chunk_and_embed in background)
    source_resp = await client_with_embedder.post(
        "/sources", json={"name": "ts-test", "source_type": "manual", "domain_pack": "personal_ai_tech"}
    )
    source_id = source_resp.json()["id"]

    ingest_resp = await client_with_embedder.post(
        "/ingest/text",
        json={"title": "TS Test", "text": "Hello world " * 50, "source_name": "ts-test"},
    )
    assert ingest_resp.status_code == 200
    doc_id = ingest_resp.json()["documents"][0]["id"]

    # Background task runs synchronously in test via AsyncClient fixture
    import asyncio
    await asyncio.sleep(0.1)

    async with session_factory() as session:
        doc = await session.get(Document, uuid.UUID(doc_id))

    assert doc.chunked_at is not None
    assert doc.embedded_at is not None
```

```bash
python -m pytest tests/ -k "test_chunk_embed_sets_timestamps" -v 2>&1 | tail -8
```

Expected: pass.

- [ ] **Step 3: Run full test suite**

```bash
python -m pytest tests/ -x -q --timeout=60 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add app/api/routes_ingestion.py
git commit -m "feat(ingestion): mark chunked_at and embedded_at timestamps in _chunk_and_embed"
```

---

## Task 10: Wire Logging at Startup

**Files:**
- Modify: `app/main.py`
- Modify: `app/cli/main.py`

> Run `gitnexus_impact({target: "lifespan", repo: "Nexus"})`. Report blast radius.

- [ ] **Step 1: Update `app/main.py`**

Add `configure_logging` call as the first statement inside lifespan:

```python
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import settings
from app.db.session import make_engine, make_session_factory
from app.observability.logger import configure_logging  # NEW

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()  # NEW — first action in lifespan
    engine = make_engine(settings.database_url)
    # ... rest unchanged ...
```

- [ ] **Step 2: Update `app/cli/main.py`**

Add after the imports, before `app = typer.Typer(...)`:

```python
from app.observability.logger import configure_logging  # NEW

configure_logging()  # NEW — runs once at CLI process start

app = typer.Typer(help="Nexus Lite — operator CLI for monitoring the system.")
```

- [ ] **Step 3: Verify startup doesn't break**

```bash
python -c "from app.main import app; print('FastAPI app OK')"
python -c "from app.cli.main import app; print('CLI app OK')"
```

Expected: both print `OK`.

- [ ] **Step 4: Run full test suite**

```bash
python -m pytest tests/ -x -q --timeout=60 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/main.py app/cli/main.py
git commit -m "feat(startup): call configure_logging() at FastAPI lifespan and CLI startup"
```

---

## Task 11: CLI — `nexus runs list` and `nexus runs show`

**Files:**
- Modify: `app/cli/db.py`
- Modify: `app/cli/render.py`
- Modify: `app/cli/main.py`
- Create: `tests/test_cli_runs.py`

> Run `gitnexus_impact({target: "list_sources", repo: "Nexus"})` to understand the db.py reader pattern. No changes to existing readers.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_runs.py`:

```python
"""Integration tests for nexus runs list / nexus runs show."""
from __future__ import annotations

import json
import uuid

import pytest
from typer.testing import CliRunner

from app.cli.main import app
from app.db.models import AgentRun, Document, Source, SpanExtraction


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def db_url_env(db_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", db_url)


@pytest.fixture
async def seeded_run(session_factory):
    """Seed one agent_run + one span_extraction row sharing a run_id."""
    run_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    span_id = uuid.uuid4()
    async with session_factory() as session:
        source = Source(name="s", source_type="manual", domain_pack="personal_ai_tech")
        session.add(source)
        await session.flush()
        doc = Document(
            id=doc_id, source_id=source.id,
            clean_text="hi", raw_text="hi",
            content_hash=f"h-{uuid.uuid4()}", status="claims_extracted",
        )
        session.add(doc)
        ar = AgentRun(
            run_type="claim_extraction", model="test-m",
            input_json={"system": "sys", "user": "usr"},
            output_json={"raw": "{}"},
            cost_estimate=0.001, status="success",
            run_id=run_id, document_id=doc_id,
        )
        session.add(ar)
        se = SpanExtraction(
            run_id=run_id, span_id=span_id, document_id=doc_id,
            status="success", attempts=1,
        )
        session.add(se)
        await session.commit()
    return {"run_id": run_id, "doc_id": doc_id}


@pytest.mark.asyncio
async def test_runs_list_shows_run(runner, db_url_env, seeded_run, db_url):
    result = runner.invoke(app, ["runs", "list", "--db-url", db_url])
    assert result.exit_code == 0
    assert str(seeded_run["run_id"])[:8] in result.output


@pytest.mark.asyncio
async def test_runs_list_json(runner, db_url_env, seeded_run, db_url):
    result = runner.invoke(app, ["runs", "list", "--json", "--db-url", db_url])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "run_id" in data[0]


@pytest.mark.asyncio
async def test_runs_show_happy_path(runner, seeded_run, db_url):
    run_id = str(seeded_run["run_id"])
    result = runner.invoke(app, ["runs", "show", run_id, "--db-url", db_url])
    assert result.exit_code == 0
    assert run_id[:8] in result.output


@pytest.mark.asyncio
async def test_runs_show_missing_run_exits_1(runner, db_url):
    result = runner.invoke(app, ["runs", "show", str(uuid.uuid4()), "--db-url", db_url])
    assert result.exit_code == 1


@pytest.mark.asyncio
async def test_runs_show_json(runner, seeded_run, db_url):
    run_id = str(seeded_run["run_id"])
    result = runner.invoke(app, ["runs", "show", run_id, "--json", "--db-url", db_url])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["run_id"] == run_id
    assert "agent_runs" in data
    assert "span_extractions" in data
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_cli_runs.py -v 2>&1 | tail -5
```

Expected: `Error: No such command 'runs'`

- [ ] **Step 3: Add readers to `app/cli/db.py`**

Append to `app/cli/db.py`:

```python
async def list_runs(database_url: str, limit: int = 50) -> list[dict]:
    """Return recent distinct run_ids with document_id, model, status summary."""
    import asyncpg
    conn = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        rows = await conn.fetch(
            """
            SELECT
                ar.run_id,
                ar.document_id,
                ar.model,
                COUNT(*) AS llm_calls,
                SUM(ar.total_tokens) AS total_tokens,
                SUM(ar.cost_estimate) AS total_cost,
                MIN(ar.created_at) AS started_at,
                MAX(ar.created_at) AS last_call_at,
                BOOL_AND(ar.status = 'success') AS all_success
            FROM agent_runs ar
            WHERE ar.run_id IS NOT NULL
            GROUP BY ar.run_id, ar.document_id, ar.model
            ORDER BY MIN(ar.created_at) DESC
            LIMIT $1
            """,
            limit,
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def show_run(database_url: str, run_id: str) -> dict | None:
    """Return full trace for a run_id: agent_runs rows, span_extractions rows, doc timing."""
    import asyncpg
    conn = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        ar_rows = await conn.fetch(
            "SELECT * FROM agent_runs WHERE run_id = $1 ORDER BY created_at",
            run_id,
        )
        se_rows = await conn.fetch(
            "SELECT * FROM span_extractions WHERE run_id = $1 ORDER BY created_at",
            run_id,
        )
        if not ar_rows:
            return None
        doc_id = ar_rows[0]["document_id"]
        doc_row = await conn.fetchrow(
            "SELECT id, status, extraction_started_at, extraction_completed_at FROM documents WHERE id = $1",
            doc_id,
        ) if doc_id else None
        return {
            "run_id": str(run_id),
            "document": dict(doc_row) if doc_row else None,
            "agent_runs": [dict(r) for r in ar_rows],
            "span_extractions": [dict(r) for r in se_rows],
        }
    finally:
        await conn.close()
```

- [ ] **Step 4: Add renderers to `app/cli/render.py`**

Append to `app/cli/render.py`:

```python
def render_runs_list(runs: list[dict], *, json_output: bool = False) -> None:
    if json_output:
        _print_json([{k: str(v) if hasattr(v, 'hex') else v for k, v in r.items()} for r in runs])
        return
    if not runs:
        console.print("[dim]No extraction runs found.[/dim]")
        return
    table = Table(title="Extraction Runs", show_lines=False)
    table.add_column("run_id (prefix)", style="cyan")
    table.add_column("document_id (prefix)")
    table.add_column("model")
    table.add_column("LLM calls", justify="right")
    table.add_column("tokens", justify="right")
    table.add_column("cost $", justify="right")
    table.add_column("started_at")
    table.add_column("ok?")
    for r in runs:
        table.add_row(
            str(r["run_id"])[:8],
            str(r["document_id"])[:8] if r["document_id"] else "—",
            r["model"] or "—",
            str(r["llm_calls"]),
            str(r["total_tokens"] or 0),
            f"{(r['total_cost'] or 0):.5f}",
            str(r["started_at"])[:19] if r["started_at"] else "—",
            "✓" if r["all_success"] else "✗",
        )
    console.print(table)


def render_run_detail(detail: dict, *, json_output: bool = False) -> None:
    if json_output:
        _print_json(detail)
        return
    doc = detail.get("document") or {}
    console.print(f"[bold]Run:[/bold] {detail['run_id']}")
    if doc:
        console.print(f"[bold]Document:[/bold] {doc.get('id')} — status: {doc.get('status')}")
        console.print(f"  extraction_started_at:   {doc.get('extraction_started_at')}")
        console.print(f"  extraction_completed_at: {doc.get('extraction_completed_at')}")

    ar_table = Table(title="LLM Calls (agent_runs)", show_lines=False)
    ar_table.add_column("span_id (prefix)")
    ar_table.add_column("status")
    ar_table.add_column("prompt_tok", justify="right")
    ar_table.add_column("comp_tok", justify="right")
    ar_table.add_column("created_at")
    for r in detail.get("agent_runs", []):
        ar_table.add_row(
            str(r["span_id"])[:8] if r.get("span_id") else "—",
            r["status"],
            str(r.get("prompt_tokens") or "—"),
            str(r.get("completion_tokens") or "—"),
            str(r["created_at"])[:19],
        )
    console.print(ar_table)

    se_table = Table(title="Span Extractions", show_lines=False)
    se_table.add_column("span_id (prefix)")
    se_table.add_column("status")
    se_table.add_column("attempts", justify="right")
    se_table.add_column("error")
    for r in detail.get("span_extractions", []):
        se_table.add_row(
            str(r["span_id"])[:8],
            r["status"],
            str(r["attempts"]),
            r.get("error") or "—",
        )
    console.print(se_table)
```

- [ ] **Step 5: Register the `runs` sub-app in `app/cli/main.py`**

```python
from app.cli.db import list_runs, show_run                    # add to existing db imports
from app.cli.render import render_runs_list, render_run_detail # add to existing render imports

runs_app = typer.Typer(help="Query extraction run traces.")
app.add_typer(runs_app, name="runs")


@runs_app.command("list")
def runs_list(
    limit: int = typer.Option(50, "--limit"),
    json_output: bool = typer.Option(False, "--json"),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    api_url: Optional[str] = typer.Option(None, "--api-url"),
) -> None:
    """List recent extraction runs."""
    cfg = _settings(db_url, api_url)
    database_url = _require_db_url(cfg)
    result = _run(list_runs(database_url, limit=limit))
    render_runs_list(result, json_output=json_output)


@runs_app.command("show")
def runs_show(
    run_id: str = typer.Argument(..., help="Run UUID to inspect."),
    json_output: bool = typer.Option(False, "--json"),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    api_url: Optional[str] = typer.Option(None, "--api-url"),
) -> None:
    """Show full trace for one extraction run."""
    cfg = _settings(db_url, api_url)
    database_url = _require_db_url(cfg)
    detail = _run(show_run(database_url, run_id))
    if detail is None:
        typer.echo(f"Run {run_id} not found.", err=True)
        raise typer.Exit(code=1)
    render_run_detail(detail, json_output=json_output)
```

- [ ] **Step 6: Run CLI runs tests**

```bash
python -m pytest tests/test_cli_runs.py -v 2>&1 | tail -10
```

Expected: all 5 pass.

- [ ] **Step 7: Run full test suite**

```bash
python -m pytest tests/ -x -q --timeout=60 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add app/cli/db.py app/cli/render.py app/cli/main.py tests/test_cli_runs.py
git commit -m "feat(cli): add 'nexus runs list' and 'nexus runs show' commands"
```

---

## Task 12: Update `TODO.md` with Deferred Observability Work

**Files:**
- Modify: `TODO.md`

- [ ] **Step 1: Append deferred section to `TODO.md`**

Add the following block. Do not remove existing content:

```markdown
## Observability — Deferred

- [ ] **LangSmith tracing** — Integrate LangSmith for LLM-side tracing (env-gated via
  `LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_API_KEY`). Wire `LangSmith` callbacks into
  `LLMClient.complete_json` alongside the existing `tracer.record_agent_run` call.
  Reference: `app/intelligence/llm_client.py::LLMClient.complete_json`.

- [ ] **Full CLI UX** — Rich progress bars during `nexus ingest` and `nexus extract`,
  color-coded log levels, `nexus status --live` auto-refresh dashboard.
  Reference: `app/cli/main.py`, `app/cli/render.py`.

- [ ] **FastAPI request_id middleware** — Assign a per-request UUID via `contextvars`,
  bind to log records, return as `X-Request-ID` response header.
  Reference: `app/main.py`.

- [ ] **`_chunk_and_embed` failure status** — Wrap `_chunk_and_embed` in try/except;
  set `doc.status = "chunk_failed"` or `"embed_failed"` and log the exception.
  Currently documents silently get stuck at `fetched` or `chunked`.
  Reference: `app/api/routes_ingestion.py::_chunk_and_embed`.

- [ ] **RSS entry-fetch drop logging** — Replace `except Exception: return None` in
  `_resolve_entry` with logging + a `dropped` counter surfaced in `IngestResult`.
  Reference: `app/ingestion/rss.py:61`.

- [ ] **File-sink option + `nexus logs tail`** — Add `LOG_FILE` env var support writing
  to `logs/nexus.jsonl`; add `nexus logs tail [--follow] [--run-id X]` CLI command.
  Reference: `app/observability/logger.py`.

- [ ] **Input/output token cost split** — Currently `_COST_PER_TOKEN_USD` applies a
  blended rate to `total_tokens`. OpenRouter bills input/output at different rates.
  Update `record_agent_run` to compute cost from `prompt_tokens` × input_rate +
  `completion_tokens` × output_rate, configurable via `app/config.py`.
  Reference: `app/observability/tracer.py::record_agent_run`.
```

- [ ] **Step 2: Commit**

```bash
git add TODO.md
git commit -m "docs(todo): add deferred observability work items"
```

---

## Task 13: Final Validation

**Files:** None (validation only)

- [ ] **Step 1: Run full test suite clean**

```bash
python -m pytest tests/ -q --timeout=60 2>&1 | tail -10
```

Expected: all pass, 0 failures, 0 errors.

- [ ] **Step 2: Run ruff + mypy**

```bash
python -m ruff check app/ tests/
python -m ruff format --check app/ tests/
python -m mypy app/ --ignore-missing-imports
```

Expected: no errors (or only pre-existing mypy issues unrelated to this branch).

- [ ] **Step 3: Run `gitnexus_detect_changes()`**

Verify the final changed symbol list matches the File Structure table at the top of this plan. No unexpected files or symbols.

- [ ] **Step 4: Smoke-test CLI help**

```bash
python -m app.cli.main --help
python -m app.cli.main runs --help
python -m app.cli.main runs list --help
python -m app.cli.main runs show --help
```

Expected: all print help text with no import errors.

---

## Self-Review Checklist (for plan author — do not implement)

- [x] **Spec coverage:** All spec requirements have a corresponding task: `run_context` ✓, `logger` ✓, `tracer` ✓, migration 0002 ✓, model updates ✓, `LLMClient` refactor ✓, extraction graph wiring ✓, `_chunk_and_embed` timestamps ✓, `ExtractionSummary.run_id` ✓, startup wiring ✓, CLI commands ✓, TODO.md ✓.
- [x] **No placeholders:** All code blocks are complete. Test bodies in Task 7 have scaffold markers — the implementer must follow the existing conftest fixture pattern for seeding documents at `embedded` status (see `test_claims_extraction.py` for the seed pattern).
- [x] **Type consistency:** `run_id: uuid.UUID` used consistently across `ExtractionState`, `run_with_context`, `ExtractionSummary`. `_TIMESTAMP_FIELDS` Literal used in `mark_document_timestamp` signature and all call sites.
- [x] **total_tokens column:** `AgentRun` model doesn't have a `total_tokens` column — `cost_estimate` is derived from it. The `record_agent_run` helper accepts `total_tokens` as a parameter and computes `cost_estimate` internally. Tests assert on `cost_estimate` and the split `prompt_tokens`/`completion_tokens`, not on a `total_tokens` column (which doesn't exist on the model). ✓
