"""Integration tests for the LangGraph extraction graph.

Uses a real testcontainers DB but a fake LLMClient so no real OpenRouter calls are made.
"""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import Claim, ClaimEvidence, Document, Source, Span
from app.intelligence.extraction import make_extraction_graph
from app.intelligence.llm_client import LLMNetworkError, LLMSchemaError


# ---------------------------------------------------------------------------
# Fake LLMClient
# ---------------------------------------------------------------------------


class FakeLLMClient:
    """Returns pre-configured results without making HTTP calls."""

    def __init__(self, responses: list):
        self._responses = iter(responses)
        self.calls: list[dict] = []

    async def complete_json(self, *, model, system, user, response_model, **kwargs):
        self.calls.append({"user": user})
        resp = next(self._responses)
        if isinstance(resp, BaseException):
            raise resp
        return response_model.model_validate(resp), 100


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


async def _seed_doc_with_spans(
    session_factory: async_sessionmaker,
    *,
    n_spans: int = 2,
    status: str = "embedded",
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    async with session_factory() as session:
        src = Source(name="S", source_type="rss", url=f"https://s{uuid.uuid4()}.example/feed")
        session.add(src)
        await session.flush()
        doc = Document(
            source_id=src.id,
            title="Doc",
            clean_text="x" * 100,
            content_hash=f"h-{uuid.uuid4()}",
            status=status,
        )
        session.add(doc)
        await session.flush()
        span_ids = []
        for i in range(n_spans):
            span = Span(
                document_id=doc.id,
                span_index=i,
                text=f"GPT-5 released with span {i}.",
                token_count=10,
                metadata_json={"title": "Doc", "source_name": "S"},
            )
            session.add(span)
            await session.flush()
            span_ids.append(span.id)
        await session.commit()
        return doc.id, span_ids


def _make_claim_response(claim_text: str = "GPT-5 was released."):
    return {
        "claims": [
            {
                "claim_text": claim_text,
                "claim_type": "model_release",
                "entities": ["OpenAI", "GPT-5"],
                "topics": ["LLM releases"],
                "confidence": 0.92,
                "rationale": "Directly stated in text.",
            }
        ]
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_stores_claims(session_factory: async_sessionmaker, db_url: str):
    doc_id, _span_ids = await _seed_doc_with_spans(session_factory, n_spans=2)
    client = FakeLLMClient(
        responses=[_make_claim_response("GPT-5 released."), _make_claim_response("GPT-5 fast.")]
    )
    graph = make_extraction_graph(session_factory, client)

    final = await graph.ainvoke(
        {
            "document_id": doc_id,
            "model": "openai/gpt-4o-mini",
            "spans": [],
            "results": [],
            "total_tokens": 0,
            "error": None,
        }
    )

    assert final.get("error") is None

    async with session_factory() as session:
        doc = await session.get(Document, doc_id)
        assert doc.status == "claims_extracted"
        claims = (
            await session.execute(select(Claim).where(Claim.document_id == doc_id))
        ).scalars().all()
        assert len(claims) == 2
        evidences = (
            await session.execute(
                select(ClaimEvidence).where(ClaimEvidence.claim_id.in_([c.id for c in claims]))
            )
        ).scalars().all()
        assert len(evidences) == 2
        assert all(e.evidence_role == "support" for e in evidences)


@pytest.mark.asyncio
async def test_network_error_marks_document_failed(session_factory: async_sessionmaker):
    doc_id, _ = await _seed_doc_with_spans(session_factory, n_spans=1)
    client = FakeLLMClient(responses=[LLMNetworkError("OpenRouter 503")])
    graph = make_extraction_graph(session_factory, client)

    final = await graph.ainvoke(
        {
            "document_id": doc_id,
            "model": "openai/gpt-4o-mini",
            "spans": [],
            "results": [],
            "total_tokens": 0,
            "error": None,
        }
    )

    assert final.get("error") is not None
    async with session_factory() as session:
        doc = await session.get(Document, doc_id)
        assert doc.status == "extraction_failed"


@pytest.mark.asyncio
async def test_schema_error_retried_then_succeeds(session_factory: async_sessionmaker):
    """First call raises LLMSchemaError; second (correction) call succeeds."""
    doc_id, _ = await _seed_doc_with_spans(session_factory, n_spans=1)
    client = FakeLLMClient(
        responses=[LLMSchemaError("missing field"), _make_claim_response()]
    )
    graph = make_extraction_graph(session_factory, client)

    final = await graph.ainvoke(
        {
            "document_id": doc_id,
            "model": "openai/gpt-4o-mini",
            "spans": [],
            "results": [],
            "total_tokens": 0,
            "error": None,
        }
    )

    assert final.get("error") is None
    async with session_factory() as session:
        claims = (
            await session.execute(select(Claim).where(Claim.document_id == doc_id))
        ).scalars().all()
        assert len(claims) == 1
        assert len(client.calls) == 2  # first attempt + one retry


@pytest.mark.asyncio
async def test_all_retries_exhausted_marks_failed(session_factory: async_sessionmaker):
    """One span fails all retries → extraction_failed."""
    doc_id, _ = await _seed_doc_with_spans(session_factory, n_spans=1)
    client = FakeLLMClient(
        responses=[
            LLMSchemaError("e1"),
            LLMSchemaError("e2"),
            LLMSchemaError("e3"),
        ]
    )
    graph = make_extraction_graph(session_factory, client)

    await graph.ainvoke(
        {
            "document_id": doc_id,
            "model": "openai/gpt-4o-mini",
            "spans": [],
            "results": [],
            "total_tokens": 0,
            "error": None,
        }
    )

    async with session_factory() as session:
        doc = await session.get(Document, doc_id)
        assert doc.status == "extraction_failed"
        claims = (
            await session.execute(select(Claim).where(Claim.document_id == doc_id))
        ).scalars().all()
        assert len(claims) == 0
