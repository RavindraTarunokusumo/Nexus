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
            await asyncio.sleep(0.001 * random.randint(1, 5))  # noqa: S311
            return current_context()["span_id"]

    async with extraction_run(doc_id):
        results = await asyncio.gather(*[task(sid) for sid in span_ids])

    assert results == span_ids


@pytest.mark.asyncio
async def test_current_context_outside_any_scope_returns_nones():
    ctx = current_context()
    assert ctx == {"run_id": None, "document_id": None, "span_id": None}
