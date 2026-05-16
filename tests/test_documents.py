"""Integration tests for GET /documents and GET /documents/{id}."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import Document, Source, Span


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_source(session_factory: async_sessionmaker) -> uuid.UUID:
    async with session_factory() as session:
        source = Source(
            name="doc-test",
            source_type="manual",
            domain_pack="personal_ai_tech",
        )
        session.add(source)
        await session.commit()
        return source.id


async def _create_doc(
    session_factory: async_sessionmaker,
    source_id: uuid.UUID,
    *,
    title: str = "Test Doc",
    status: str = "fetched",
    url: str | None = None,
    content_hash: str | None = None,
) -> uuid.UUID:
    async with session_factory() as session:
        doc = Document(
            source_id=source_id,
            title=title,
            url=url,
            raw_text="raw",
            clean_text="some clean text content",
            content_hash=content_hash or uuid.uuid4().hex,
            status=status,
        )
        session.add(doc)
        await session.commit()
        return doc.id


# ---------------------------------------------------------------------------
# GET /documents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_documents_empty(client: AsyncClient):
    response = await client.get("/documents")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_documents_returns_all(client: AsyncClient, session_factory: async_sessionmaker):
    source_id = await _create_source(session_factory)
    await _create_doc(session_factory, source_id, title="Doc A", content_hash="aaa")
    await _create_doc(session_factory, source_id, title="Doc B", content_hash="bbb")

    response = await client.get("/documents")
    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_list_documents_filter_by_status(
    client: AsyncClient, session_factory: async_sessionmaker
):
    source_id = await _create_source(session_factory)
    await _create_doc(session_factory, source_id, status="fetched", content_hash="c1")
    await _create_doc(session_factory, source_id, status="embedded", content_hash="c2")

    response = await client.get("/documents?status=embedded")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["status"] == "embedded"


@pytest.mark.asyncio
async def test_list_documents_filter_by_source_id(
    client: AsyncClient, session_factory: async_sessionmaker
):
    source_a = await _create_source(session_factory)
    async with session_factory() as session:
        source_b = Source(name="other", source_type="manual", domain_pack="personal_ai_tech")
        session.add(source_b)
        await session.commit()
        source_b_id = source_b.id

    await _create_doc(session_factory, source_a, content_hash="d1")
    await _create_doc(session_factory, source_b_id, content_hash="d2")

    response = await client.get(f"/documents?source_id={source_a}")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["source_id"] == str(source_a)


@pytest.mark.asyncio
async def test_list_documents_pagination(
    client: AsyncClient, session_factory: async_sessionmaker
):
    source_id = await _create_source(session_factory)
    for i in range(5):
        await _create_doc(session_factory, source_id, content_hash=f"p{i}")

    page1 = await client.get("/documents?limit=3&offset=0")
    page2 = await client.get("/documents?limit=3&offset=3")
    assert len(page1.json()) == 3
    assert len(page2.json()) == 2


# ---------------------------------------------------------------------------
# GET /documents/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_document_with_spans(
    client: AsyncClient, session_factory: async_sessionmaker
):
    source_id = await _create_source(session_factory)
    doc_id = await _create_doc(session_factory, source_id, status="embedded", content_hash="e1")

    async with session_factory() as session:
        session.add(
            Span(
                document_id=doc_id,
                span_index=0,
                text="first span text",
                token_count=3,
                metadata_json={},
            )
        )
        await session.commit()

    response = await client.get(f"/documents/{doc_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(doc_id)
    assert len(data["spans"]) == 1
    assert data["spans"][0]["text"] == "first span text"
    # Embedding vectors must not be exposed
    assert "embedding" not in data["spans"][0]


@pytest.mark.asyncio
async def test_get_document_not_found(client: AsyncClient):
    response = await client.get(f"/documents/{uuid.uuid4()}")
    assert response.status_code == 404
