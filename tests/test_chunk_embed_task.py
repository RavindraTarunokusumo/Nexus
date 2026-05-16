"""Tests for the _chunk_and_embed background task."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.routes_ingestion import _chunk_and_embed
from app.db.models import Document, Source, Span

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_doc(
    session_factory: async_sessionmaker,
    *,
    clean_text: str = "word " * 700,
    status: str = "fetched",
) -> uuid.UUID:
    async with session_factory() as session:
        source = Source(
            name=uuid.uuid4().hex[:8],
            source_type="manual",
            domain_pack="personal_ai_tech",
        )
        session.add(source)
        await session.flush()
        doc = Document(
            source_id=source.id,
            title="Task Test",
            url=None,
            raw_text=clean_text,
            clean_text=clean_text,
            content_hash=uuid.uuid4().hex,
            status=status,
        )
        session.add(doc)
        await session.commit()
        return doc.id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chunk_embed_happy_path(session_factory: async_sessionmaker, mock_embedder):
    doc_id = await _create_doc(session_factory, clean_text="word " * 700)

    await _chunk_and_embed(doc_id, session_factory, mock_embedder)

    async with session_factory() as session:
        doc = await session.get(Document, doc_id)
        assert doc.status == "embedded"

        spans = (
            (await session.execute(select(Span).where(Span.document_id == doc_id))).scalars().all()
        )
        assert len(spans) > 0
        assert all(s.embedding is not None for s in spans)


@pytest.mark.asyncio
async def test_chunk_embed_idempotency(session_factory: async_sessionmaker, mock_embedder):
    """Calling _chunk_and_embed twice must not create duplicate spans."""
    doc_id = await _create_doc(session_factory, clean_text="word " * 700)

    await _chunk_and_embed(doc_id, session_factory, mock_embedder)

    # Second call — document is now "embedded", should be a no-op.
    await _chunk_and_embed(doc_id, session_factory, mock_embedder)

    async with session_factory() as session:
        spans = (
            (await session.execute(select(Span).where(Span.document_id == doc_id))).scalars().all()
        )
        indices = [s.span_index for s in spans]
        assert len(indices) == len(set(indices)), "Duplicate span_index found"


@pytest.mark.asyncio
async def test_chunk_embed_empty_text(session_factory: async_sessionmaker, mock_embedder):
    doc_id = await _create_doc(session_factory, clean_text="")

    await _chunk_and_embed(doc_id, session_factory, mock_embedder)

    async with session_factory() as session:
        doc = await session.get(Document, doc_id)
        spans = (
            (await session.execute(select(Span).where(Span.document_id == doc_id))).scalars().all()
        )
        assert len(spans) == 0
        # Status is "chunked" since the chunking phase completed (zero spans produced).
        assert doc.status == "chunked"
