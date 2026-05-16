"""Integration tests for POST /search/spans."""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import Document, Source, Span


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_span(
    session_factory: async_sessionmaker,
    *,
    text: str,
    embedding: list[float],
    status: str = "embedded",
) -> tuple[uuid.UUID, uuid.UUID]:
    """Insert a source, document, and one span with a known embedding; return (doc_id, span_id)."""
    async with session_factory() as session:
        source = Source(name=uuid.uuid4().hex[:8], source_type="manual", domain_pack="personal_ai_tech")
        session.add(source)
        await session.flush()

        doc = Document(
            source_id=source.id,
            title="Seeded doc",
            url=None,
            raw_text=text,
            clean_text=text,
            content_hash=uuid.uuid4().hex,
            status=status,
        )
        session.add(doc)
        await session.flush()

        span = Span(
            document_id=doc.id,
            span_index=0,
            text=text,
            token_count=len(text.split()),
            embedding=embedding,
        )
        session.add(span)
        await session.commit()
        return doc.id, span.id


def _unit_vec(dim: int, index: int) -> list[float]:
    """Unit vector with 1.0 at *index*, zero elsewhere."""
    v = [0.0] * dim
    v[index] = 1.0
    return v


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_empty_index_returns_empty_list(client_with_embedder: AsyncClient):
    response = await client_with_embedder.post(
        "/search/spans", json={"query": "anything", "top_k": 5}
    )
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_search_returns_results(
    client_with_embedder: AsyncClient, session_factory: async_sessionmaker
):
    dim = 384
    await _seed_span(session_factory, text="neural networks", embedding=_unit_vec(dim, 0))

    response = await client_with_embedder.post(
        "/search/spans", json={"query": "deep learning", "top_k": 5}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    result = data[0]
    assert "span_id" in result
    assert "document_id" in result
    assert "score" in result
    assert "text" in result
    assert "document_status" in result


@pytest.mark.asyncio
async def test_search_top_k_respected(
    client_with_embedder: AsyncClient, session_factory: async_sessionmaker
):
    dim = 384
    for i in range(5):
        await _seed_span(session_factory, text=f"span {i}", embedding=_unit_vec(dim, i))

    response = await client_with_embedder.post(
        "/search/spans", json={"query": "query text", "top_k": 3}
    )
    assert response.status_code == 200
    assert len(response.json()) == 3


@pytest.mark.asyncio
async def test_search_semantic_ranking(async_engine, session_factory: async_sessionmaker):
    """Span with embedding closest to the query vector ranks first."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.api.routes_documents import router as documents_router
    from app.api.routes_ingestion import router as ingestion_router
    from app.api.routes_sources import router as sources_router

    dim = 384

    class FixedEmbedder:
        """Always returns e_0 direction, making span A score 1.0 and span B score 0.0."""

        def embed(self, texts):
            return [_unit_vec(dim, 0) for _ in texts]

        def embed_one(self, text):
            return _unit_vec(dim, 0)

    test_app = FastAPI()
    test_app.state.engine = async_engine
    test_app.state.session_factory = session_factory
    test_app.state.embedder = FixedEmbedder()
    test_app.include_router(sources_router)
    test_app.include_router(ingestion_router)
    test_app.include_router(documents_router)

    # Span A: e_0 direction
    doc_a_id, span_a_id = await _seed_span(
        session_factory, text="span A", embedding=_unit_vec(dim, 0)
    )
    # Span B: e_1 direction (orthogonal to A, cosine similarity = 0)
    doc_b_id, span_b_id = await _seed_span(
        session_factory, text="span B", embedding=_unit_vec(dim, 1)
    )

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/search/spans", json={"query": "any query", "top_k": 2}
        )

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 2
    assert results[0]["span_id"] == str(span_a_id)
    assert results[0]["score"] > results[1]["score"]
