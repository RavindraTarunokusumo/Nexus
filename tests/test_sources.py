"""Integration tests for source management API."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_source_rss(client: AsyncClient):
    response = await client.post(
        "/sources",
        json={
            "name": "Test RSS Feed",
            "source_type": "rss",
            "url": "https://example.com/feed.xml",
            "domain_pack": "personal_ai_tech",
            "enabled": True,
            "credibility_score": 0.9,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test RSS Feed"
    assert data["source_type"] == "rss"
    assert data["url"] == "https://example.com/feed.xml"
    assert data["domain_pack"] == "personal_ai_tech"
    assert data["enabled"] is True
    assert data["credibility_score"] == pytest.approx(0.9)
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_create_source_manual_no_url(client: AsyncClient):
    response = await client.post(
        "/sources",
        json={"name": "Paste Source", "source_type": "manual"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["url"] is None
    assert data["domain_pack"] == "personal_ai_tech"


@pytest.mark.asyncio
async def test_create_source_invalid_type(client: AsyncClient):
    response = await client.post(
        "/sources",
        json={"name": "Bad Source", "source_type": "webhook"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_source_duplicate_url(client: AsyncClient):
    payload = {
        "name": "Feed A",
        "source_type": "rss",
        "url": "https://example.com/feed.xml",
    }
    r1 = await client.post("/sources", json=payload)
    assert r1.status_code == 201

    r2 = await client.post("/sources", json={**payload, "name": "Feed B"})
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_list_sources_empty(client: AsyncClient):
    response = await client.get("/sources")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_sources(client: AsyncClient):
    await client.post("/sources", json={"name": "Feed 1", "source_type": "rss", "url": "https://a.example.com/f"})
    await client.post("/sources", json={"name": "Feed 2", "source_type": "rss", "url": "https://b.example.com/f"})
    response = await client.get("/sources")
    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_get_source_by_id(client: AsyncClient):
    create = await client.post(
        "/sources",
        json={"name": "Single", "source_type": "manual"},
    )
    source_id = create.json()["id"]
    response = await client.get(f"/sources/{source_id}")
    assert response.status_code == 200
    assert response.json()["id"] == source_id


@pytest.mark.asyncio
async def test_get_source_not_found(client: AsyncClient):
    response = await client.get("/sources/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
