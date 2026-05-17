"""Integration tests for claim extraction endpoints."""

import uuid
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import Claim, Document, Source, Span


async def _seed_embedded_doc(session_factory: async_sessionmaker) -> tuple[uuid.UUID, uuid.UUID]:
    async with session_factory() as session:
        src = Source(name="Src", source_type="rss", url=f"https://s{uuid.uuid4()}.example/feed")
        session.add(src)
        await session.flush()
        doc = Document(
            source_id=src.id,
            title="Article",
            clean_text="x" * 200,
            content_hash=f"h-{uuid.uuid4()}",
            status="embedded",
        )
        session.add(doc)
        await session.flush()
        span = Span(
            document_id=doc.id,
            span_index=0,
            text="GPT-5 released.",
            token_count=5,
            metadata_json={"title": "Article"},
        )
        session.add(span)
        await session.commit()
        return doc.id, span.id


def _fake_graph_final_state(doc_id: uuid.UUID, span_id: uuid.UUID) -> dict:
    """Pre-built final state mimicking a successful graph run."""
    return {
        "document_id": doc_id,
        "model": "openai/gpt-4o-mini",
        "spans": [
            {
                "id": str(span_id),
                "text": "GPT-5 released.",
                "token_count": 5,
                "metadata_json": {},
            }
        ],
        "results": [
            {
                "span_id": str(span_id),
                "claims": [
                    {
                        "claim_text": "GPT-5 was released.",
                        "claim_type": "model_release",
                        "entities": ["OpenAI"],
                        "topics": ["LLM"],
                        "confidence": 0.9,
                        "rationale": "Directly stated.",
                    }
                ],
                "tokens": 100,
                "error": None,
            }
        ],
        "total_tokens": 100,
        "error": None,
    }


@pytest.mark.asyncio
async def test_extract_claims_success(
    client: AsyncClient, session_factory: async_sessionmaker, monkeypatch
):
    doc_id, span_id = await _seed_embedded_doc(session_factory)

    # Mock the graph so it returns a known final state without making real LLM calls.
    # We also pre-seed the claim that the real graph would have written so the
    # endpoint's "count claims after ainvoke" query returns 1. The graph's storage
    # logic is verified separately in test_extraction_graph.
    mock_graph = MagicMock()

    async def fake_ainvoke(state):
        async with session_factory() as session:
            session.add(
                Claim(
                    document_id=doc_id,
                    claim_text="GPT-5 was released.",
                    claim_type="model_release",
                    entities_json=["OpenAI"],
                    topics_json=["LLM"],
                    confidence=0.9,
                    status="active",
                )
            )
            await session.commit()
        return _fake_graph_final_state(doc_id, span_id)

    mock_graph.ainvoke = fake_ainvoke
    monkeypatch.setattr("app.api.routes_claims.make_extraction_graph", lambda *_: mock_graph)

    resp = await client.post(f"/documents/{doc_id}/extract-claims")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["document_id"] == str(doc_id)
    assert data["tokens_used"] == 100
    assert isinstance(data["claim_ids"], list)
    assert len(data["claim_ids"]) == 1


@pytest.mark.asyncio
async def test_extract_claims_404_for_unknown_doc(client: AsyncClient):
    resp = await client.post(f"/documents/{uuid.uuid4()}/extract-claims")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_extract_claims_422_when_not_embedded(
    client: AsyncClient, session_factory: async_sessionmaker
):
    async with session_factory() as session:
        src = Source(name="S", source_type="rss", url=f"https://x{uuid.uuid4()}.example")
        session.add(src)
        await session.flush()
        doc = Document(
            source_id=src.id,
            title="D",
            clean_text="y",
            content_hash=f"h-{uuid.uuid4()}",
            status="fetched",
        )
        session.add(doc)
        await session.commit()
        doc_id = doc.id

    resp = await client.post(f"/documents/{doc_id}/extract-claims")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_extract_claims_409_when_claims_already_exist(
    client: AsyncClient, session_factory: async_sessionmaker
):
    doc_id, _ = await _seed_embedded_doc(session_factory)
    async with session_factory() as session:
        session.add(
            Claim(
                document_id=doc_id,
                claim_text="existing",
                claim_type="other",
                entities_json=[],
                topics_json=[],
                confidence=0.5,
                status="active",
            )
        )
        await session.commit()

    resp = await client.post(f"/documents/{doc_id}/extract-claims")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_claims_returns_correct_claims(
    client: AsyncClient, session_factory: async_sessionmaker
):
    doc_id, _ = await _seed_embedded_doc(session_factory)
    async with session_factory() as session:
        for ct in ("model_release", "benchmark_result"):
            session.add(
                Claim(
                    document_id=doc_id,
                    claim_text=f"Claim {ct}",
                    claim_type=ct,
                    entities_json=[],
                    topics_json=[],
                    confidence=0.8,
                    status="active",
                )
            )
        await session.commit()

    resp = await client.get(f"/claims?document_id={doc_id}")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_get_claims_filters_by_claim_type(
    client: AsyncClient, session_factory: async_sessionmaker
):
    doc_id, _ = await _seed_embedded_doc(session_factory)
    async with session_factory() as session:
        session.add(
            Claim(
                document_id=doc_id,
                claim_text="A",
                claim_type="model_release",
                entities_json=[],
                topics_json=[],
                confidence=0.9,
                status="active",
            )
        )
        session.add(
            Claim(
                document_id=doc_id,
                claim_text="B",
                claim_type="other",
                entities_json=[],
                topics_json=[],
                confidence=0.5,
                status="active",
            )
        )
        await session.commit()

    resp = await client.get(f"/claims?document_id={doc_id}&claim_type=model_release")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["claim_type"] == "model_release"


@pytest.mark.asyncio
async def test_get_claims_requires_document_id(client: AsyncClient):
    resp = await client.get("/claims")
    assert resp.status_code == 422
