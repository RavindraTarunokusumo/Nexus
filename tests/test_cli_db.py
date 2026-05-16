"""Integration tests for app/cli/db.py against testcontainers Postgres."""
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.cli.db import (
    count_documents_by_status,
    get_document_with_spans,
    get_status_snapshot,
    list_documents,
    list_sources,
)
from app.db.models import Document, Source, Span


async def _seed_basic(session_factory: async_sessionmaker) -> dict:
    """Seed two sources and four documents in different statuses."""
    async with session_factory() as session:
        src_a = Source(name="Feed A", source_type="rss", url="https://a.example/feed", enabled=True)
        src_b = Source(name="Feed B", source_type="rss", url="https://b.example/feed", enabled=False)
        session.add_all([src_a, src_b])
        await session.flush()
        docs = [
            Document(source_id=src_a.id, title="D1", clean_text="x", content_hash=f"h{uuid.uuid4()}", status="fetched"),
            Document(source_id=src_a.id, title="D2", clean_text="y", content_hash=f"h{uuid.uuid4()}", status="chunked"),
            Document(source_id=src_a.id, title="D3", clean_text="z", content_hash=f"h{uuid.uuid4()}", status="embedded"),
            Document(source_id=src_b.id, title="D4", clean_text="w", content_hash=f"h{uuid.uuid4()}", status="embedded"),
        ]
        session.add_all(docs)
        await session.commit()
        return {"src_a": src_a.id, "src_b": src_b.id, "docs": [d.id for d in docs]}


@pytest.mark.asyncio
async def test_count_documents_by_status(session_factory, db_url):
    await _seed_basic(session_factory)
    counts = await count_documents_by_status(db_url)
    assert counts["fetched"] == 1
    assert counts["chunked"] == 1
    assert counts["embedded"] == 2


@pytest.mark.asyncio
async def test_list_sources_all(session_factory, db_url):
    ids = await _seed_basic(session_factory)
    sources = await list_sources(db_url, enabled=None)
    assert len(sources) == 2
    assert {s["name"] for s in sources} == {"Feed A", "Feed B"}


@pytest.mark.asyncio
async def test_list_sources_enabled_only(session_factory, db_url):
    await _seed_basic(session_factory)
    sources = await list_sources(db_url, enabled=True)
    assert len(sources) == 1
    assert sources[0]["name"] == "Feed A"


@pytest.mark.asyncio
async def test_list_documents_filter_by_status(session_factory, db_url):
    await _seed_basic(session_factory)
    docs = await list_documents(db_url, status="embedded", source_id=None, since=None, limit=50)
    assert len(docs) == 2
    assert all(d["status"] == "embedded" for d in docs)


@pytest.mark.asyncio
async def test_list_documents_filter_by_source(session_factory, db_url):
    ids = await _seed_basic(session_factory)
    docs = await list_documents(db_url, status=None, source_id=ids["src_b"], since=None, limit=50)
    assert len(docs) == 1
    assert docs[0]["title"] == "D4"


@pytest.mark.asyncio
async def test_get_document_with_spans_includes_spans_sorted(session_factory, db_url):
    ids = await _seed_basic(session_factory)
    doc_id = ids["docs"][2]  # D3, status=embedded
    async with session_factory() as session:
        session.add_all([
            Span(document_id=doc_id, span_index=2, text="span2", token_count=10),
            Span(document_id=doc_id, span_index=0, text="span0", token_count=10),
            Span(document_id=doc_id, span_index=1, text="span1", token_count=10),
        ])
        await session.commit()

    detail = await get_document_with_spans(db_url, doc_id)
    assert detail is not None
    assert detail["id"] == doc_id
    assert detail["title"] == "D3"
    assert [s["span_index"] for s in detail["spans"]] == [0, 1, 2]
    # Embedding vector must NOT be in the result
    assert "embedding" not in detail["spans"][0]


@pytest.mark.asyncio
async def test_get_document_with_spans_returns_none_for_unknown(db_url):
    result = await get_document_with_spans(db_url, uuid.uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_get_status_snapshot(session_factory, db_url):
    await _seed_basic(session_factory)
    snapshot = await get_status_snapshot(db_url)
    assert snapshot["docs_by_status"]["fetched"] == 1
    assert snapshot["docs_by_status"]["chunked"] == 1
    assert snapshot["docs_by_status"]["embedded"] == 2
    assert snapshot["total_documents"] == 4
    assert snapshot["total_sources"] == 2
    assert snapshot["enabled_sources"] == 1
    assert snapshot["total_spans"] == 0  # no spans seeded in basic
    assert snapshot["last_ingest_at"] is not None
