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
