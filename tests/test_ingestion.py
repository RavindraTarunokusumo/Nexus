"""Integration tests for ingestion layer: RSS, URL, text, deduplication, provenance."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import Document, Source


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_rss_source(
    client: AsyncClient, url: str = "https://example.com/feed.xml"
) -> dict:
    r = await client.post(
        "/sources",
        json={"name": "Test Feed", "source_type": "rss", "url": url},
    )
    assert r.status_code == 201
    return r.json()


# ---------------------------------------------------------------------------
# Text ingestion tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_text_success(client: AsyncClient, session_factory: async_sessionmaker):
    response = await client.post(
        "/ingest/text",
        json={
            "title": "My AI Note",
            "text": "OpenAI released GPT-5 with significantly improved reasoning capabilities.",
            "source_name": "manual",
            "domain_pack": "personal_ai_tech",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ingested"] == 1
    assert data["skipped"] == 0
    assert len(data["documents"]) == 1

    doc = data["documents"][0]
    assert doc["status"] == "fetched"
    assert doc["url"] is None

    # Verify provenance: document links back to a source
    async with session_factory() as session:
        stored = await session.get(Document, uuid.UUID(doc["id"]))
        assert stored is not None
        assert stored.source_id is not None
        source = await session.get(Source, stored.source_id)
        assert source is not None
        assert source.source_type == "manual"


@pytest.mark.asyncio
async def test_ingest_text_empty_rejected(client: AsyncClient):
    response = await client.post(
        "/ingest/text",
        json={
            "title": "Empty",
            "text": "   ",
            "source_name": "manual",
            "domain_pack": "personal_ai_tech",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ingest_text_dedup_content_hash(client: AsyncClient):
    payload = {
        "title": "Duplicate Note",
        "text": "This is a unique piece of text that will be deduplicated on second insert.",
        "source_name": "manual",
        "domain_pack": "personal_ai_tech",
    }
    r1 = await client.post("/ingest/text", json=payload)
    assert r1.json()["ingested"] == 1

    r2 = await client.post("/ingest/text", json=payload)
    assert r2.status_code == 200
    assert r2.json()["ingested"] == 0
    assert r2.json()["skipped"] == 1


@pytest.mark.asyncio
async def test_ingest_text_provenance(client: AsyncClient, session_factory: async_sessionmaker):
    """Every ingested document must link to a real source row."""
    response = await client.post(
        "/ingest/text",
        json={
            "title": "Provenance Check",
            "text": "A unique provenance-test article about embedding models.",
            "source_name": "provenance-test",
            "domain_pack": "personal_ai_tech",
        },
    )
    assert response.status_code == 200
    doc_id = uuid.UUID(response.json()["documents"][0]["id"])

    async with session_factory() as session:
        doc = await session.get(Document, doc_id)
        assert doc is not None
        source = await session.get(Source, doc.source_id)
        assert source is not None
        assert source.name == "provenance-test"


# ---------------------------------------------------------------------------
# URL ingestion tests (mock network)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_url_success(client: AsyncClient):
    with patch(
        "app.api.routes_ingestion.fetch_and_clean",
        new=AsyncMock(return_value=("<html>content</html>", "Cleaned article text about LLMs.")),
    ):
        response = await client.post(
            "/ingest/url",
            json={"url": "https://example.com/llm-article", "domain_pack": "personal_ai_tech"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["ingested"] == 1
    assert data["documents"][0]["url"] is not None


@pytest.mark.asyncio
async def test_ingest_url_dedup_same_url(client: AsyncClient):
    with patch(
        "app.api.routes_ingestion.fetch_and_clean",
        new=AsyncMock(return_value=("<html/>", "Article text unique enough to hash.")),
    ):
        r1 = await client.post(
            "/ingest/url",
            json={"url": "https://example.com/article-dedup"},
        )
        assert r1.json()["ingested"] == 1

        r2 = await client.post(
            "/ingest/url",
            json={"url": "https://example.com/article-dedup"},
        )
        assert r2.json()["ingested"] == 0
        assert r2.json()["skipped"] == 1


@pytest.mark.asyncio
async def test_ingest_url_dedup_content_hash(client: AsyncClient):
    """Two different URLs with identical content should deduplicate on content hash."""
    identical_text = "Identical article body that is long enough to be meaningful content."
    with patch(
        "app.api.routes_ingestion.fetch_and_clean",
        new=AsyncMock(return_value=("<html/>", identical_text)),
    ):
        r1 = await client.post("/ingest/url", json={"url": "https://example.com/original"})
        assert r1.json()["ingested"] == 1

        r2 = await client.post("/ingest/url", json={"url": "https://mirror.example.com/copy"})
        assert r2.json()["ingested"] == 0
        assert r2.json()["skipped"] == 1


@pytest.mark.asyncio
async def test_ingest_url_blocked_scheme(client: AsyncClient):
    response = await client.post("/ingest/url", json={"url": "file:///etc/passwd"})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# RSS ingestion tests (mock network)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_rss_success(client: AsyncClient, session_factory: async_sessionmaker):
    source = await _create_rss_source(client)
    source_id = source["id"]

    mock_entries = [
        {
            "url": "https://example.com/article-1",
            "title": "Article One",
            "raw_text": "<p>Raw content one</p>",
            "clean_text": "Raw content one about AI developments.",
            "published_at": datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc),
        },
        {
            "url": "https://example.com/article-2",
            "title": "Article Two",
            "raw_text": "<p>Raw content two</p>",
            "clean_text": "Raw content two about open-source models.",
            "published_at": datetime(2026, 5, 15, 11, 0, tzinfo=timezone.utc),
        },
    ]

    with patch(
        "app.api.routes_ingestion.fetch_rss_entries",
        new=AsyncMock(return_value=mock_entries),
    ):
        response = await client.post(f"/ingest/rss/{source_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["ingested"] == 2
    assert data["skipped"] == 0
    assert len(data["documents"]) == 2

    # Verify provenance: each document links to the RSS source
    async with session_factory() as session:
        for doc_data in data["documents"]:
            doc = await session.get(Document, uuid.UUID(doc_data["id"]))
            assert doc is not None
            assert str(doc.source_id) == source_id


@pytest.mark.asyncio
async def test_ingest_rss_dedup_skips_seen_entries(client: AsyncClient):
    source = await _create_rss_source(client)
    source_id = source["id"]

    entry = {
        "url": "https://example.com/already-seen",
        "title": "Seen Article",
        "raw_text": "raw",
        "clean_text": "Content that is already in the database from a prior run.",
        "published_at": None,
    }

    with patch(
        "app.api.routes_ingestion.fetch_rss_entries",
        new=AsyncMock(return_value=[entry]),
    ):
        r1 = await client.post(f"/ingest/rss/{source_id}")
        assert r1.json()["ingested"] == 1

        r2 = await client.post(f"/ingest/rss/{source_id}")
        assert r2.json()["ingested"] == 0
        assert r2.json()["skipped"] == 1


@pytest.mark.asyncio
async def test_ingest_rss_wrong_source_type(client: AsyncClient):
    r = await client.post(
        "/sources",
        json={"name": "Manual", "source_type": "manual"},
    )
    source_id = r.json()["id"]
    response = await client.post(f"/ingest/rss/{source_id}")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ingest_rss_source_not_found(client: AsyncClient):
    response = await client.post(f"/ingest/rss/{uuid.uuid4()}")
    assert response.status_code == 404
