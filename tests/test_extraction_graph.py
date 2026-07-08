"""Integration tests for the LangGraph extraction graph.

Uses a real testcontainers DB but a fake LLMClient so no real OpenRouter calls are made.
"""

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import Claim, ClaimEvidence, Document, Source, Span, SpanExtraction
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
        self.calls.append({"user": user, "model": model})
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
        src = Source(
            name="S",
            source_type="rss",
            url=f"https://s{uuid.uuid4()}.example/feed",
            domain_pack="personal_ai_tech",
        )
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


def _make_semantic_response(span_id: str, claim_text: str = "GPT-5 was released."):
    """Build a SemanticExtractionOutput-compatible dict for a model_release object.

    Uses model_system / model_release to match the personal_ai_tech pack's
    mvp_claim_type mapping (model_release → model_release).
    """
    return {
        "objects": [
            {
                "source_refs": [span_id],
                "core_type": "event",
                "domain_family": "model_system",
                "domain_object_type": "model_release",
                "function": "Marks a new model version entering availability.",
                "text": claim_text,
                "original_text": None,
                "facets": {
                    "orgs": ["OpenAI"],
                    "models": ["GPT-5"],
                },
                "epistemic": {
                    "status": "reported",
                    "source_authority": "primary",
                    "confidence": 0.92,
                    "evidence_quality": "high",
                    "uncertainty": None,
                    "needs_escalation": False,
                },
                "salience": 0.9,
                "mvp_claim_type": "model_release",
            }
        ]
    }


# Initial state template — now includes the new fields.
def _initial_state(doc_id: uuid.UUID, run_id: uuid.UUID | None = None) -> dict:
    return {
        "document_id": doc_id,
        "run_id": run_id,
        "model": "deepseek/deepseek-v4-flash",
        "pack": None,
        "source_type": None,
        "source_id": None,
        "spans": [],
        "results": [],
        "projected_claims": [],
        "semantic_objects": [],
        "stored_claim_ids": [],
        "total_tokens": 0,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_stores_claims(session_factory: async_sessionmaker, db_url: str):
    doc_id, span_ids = await _seed_doc_with_spans(session_factory, n_spans=2)
    client = FakeLLMClient(
        responses=[
            _make_semantic_response(str(span_ids[0]), "GPT-5 released."),
            _make_semantic_response(str(span_ids[1]), "GPT-5 fast."),
        ]
    )
    graph = make_extraction_graph(session_factory, client)

    final = await graph.ainvoke(_initial_state(doc_id))

    assert final.get("error") is None

    async with session_factory() as session:
        doc = await session.get(Document, doc_id)
        assert doc.status == "claims_extracted"
        claims = (
            (await session.execute(select(Claim).where(Claim.document_id == doc_id)))
            .scalars()
            .all()
        )
        assert len(claims) == 2
        for claim in claims:
            assert claim.claim_type == "model_release"
            # v0.7 traceability keys must be present in entities_json
            assert "_v0_7" in claim.entities_json
            assert "_function" in claim.entities_json
            assert "_domain_family" in claim.entities_json
        evidences = (
            (
                await session.execute(
                    select(ClaimEvidence).where(ClaimEvidence.claim_id.in_([c.id for c in claims]))
                )
            )
            .scalars()
            .all()
        )
        assert len(evidences) == 2
        assert all(e.evidence_role == "support" for e in evidences)


@pytest.mark.asyncio
async def test_network_error_marks_document_failed(session_factory: async_sessionmaker):
    doc_id, _ = await _seed_doc_with_spans(session_factory, n_spans=1)
    client = FakeLLMClient(responses=[LLMNetworkError("OpenRouter 503")])
    graph = make_extraction_graph(session_factory, client)

    final = await graph.ainvoke(_initial_state(doc_id))

    assert final.get("error") is not None
    async with session_factory() as session:
        doc = await session.get(Document, doc_id)
        assert doc.status == "extraction_failed"


@pytest.mark.asyncio
async def test_schema_error_retried_then_succeeds(session_factory: async_sessionmaker):
    """First call raises LLMSchemaError; second (correction) call succeeds."""
    doc_id, span_ids = await _seed_doc_with_spans(session_factory, n_spans=1)
    client = FakeLLMClient(
        responses=[
            LLMSchemaError("missing field"),
            _make_semantic_response(str(span_ids[0])),
        ]
    )
    graph = make_extraction_graph(session_factory, client)

    final = await graph.ainvoke(_initial_state(doc_id))

    assert final.get("error") is None
    async with session_factory() as session:
        claims = (
            (await session.execute(select(Claim).where(Claim.document_id == doc_id)))
            .scalars()
            .all()
        )
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

    await graph.ainvoke(_initial_state(doc_id))

    async with session_factory() as session:
        doc = await session.get(Document, doc_id)
        assert doc.status == "extraction_failed"
        claims = (
            (await session.execute(select(Claim).where(Claim.document_id == doc_id)))
            .scalars()
            .all()
        )
        assert len(claims) == 0


@pytest.mark.asyncio
async def test_partial_extraction_status(session_factory: async_sessionmaker):
    """Two spans: first exhausts all retries (schema errors), second succeeds → extraction_partial.

    Deterministic ordering: FakeLLMClient.complete_json has no internal awaits, so when
    asyncio.gather runs both bounded(span_0) and bounded(span_1), span_0's retry loop
    consumes its responses before span_1 starts. The semaphore acquire is also non-yielding
    when capacity is available.
    """
    doc_id, span_ids = await _seed_doc_with_spans(session_factory, n_spans=2)
    client = FakeLLMClient(
        responses=[
            LLMSchemaError("e1"),
            LLMSchemaError("e2"),
            LLMSchemaError("e3"),
            _make_semantic_response(str(span_ids[1]), "Second span succeeded."),
        ]
    )
    graph = make_extraction_graph(session_factory, client)

    final = await graph.ainvoke(_initial_state(doc_id))

    assert final.get("error") is None
    async with session_factory() as session:
        doc = await session.get(Document, doc_id)
        assert doc.status == "extraction_partial"
        claims = (
            (await session.execute(select(Claim).where(Claim.document_id == doc_id)))
            .scalars()
            .all()
        )
        assert len(claims) == 1


@pytest.mark.asyncio
async def test_extraction_populates_span_extractions_table(session_factory: async_sessionmaker):
    """After extraction, one span_extractions row per span must exist with run_id set."""
    doc_id, span_ids = await _seed_doc_with_spans(session_factory, n_spans=2)
    client = FakeLLMClient(
        responses=[
            _make_semantic_response(str(span_ids[0]), "GPT-5 released."),
            _make_semantic_response(str(span_ids[1]), "GPT-5 fast."),
        ]
    )
    graph = make_extraction_graph(session_factory, client)

    run_id = uuid.uuid4()
    await graph.ainvoke(_initial_state(doc_id, run_id))

    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(SpanExtraction).where(SpanExtraction.document_id == doc_id)
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) >= 1
    assert all(r.run_id is not None for r in rows)
    assert all(r.document_id == doc_id for r in rows)
    assert all(r.status == "success" for r in rows)


@pytest.mark.asyncio
async def test_extraction_populates_document_timestamps(session_factory: async_sessionmaker):
    """extraction_started_at and extraction_completed_at must be set after extraction."""
    doc_id, span_ids = await _seed_doc_with_spans(session_factory, n_spans=1)
    client = FakeLLMClient(responses=[_make_semantic_response(str(span_ids[0]))])
    graph = make_extraction_graph(session_factory, client)

    await graph.ainvoke(_initial_state(doc_id, uuid.uuid4()))

    async with session_factory() as session:
        doc = await session.get(Document, doc_id)
    assert doc.extraction_started_at is not None
    assert doc.extraction_completed_at is not None
    assert doc.extraction_completed_at >= doc.extraction_started_at


@pytest.mark.asyncio
async def test_claim_has_v07_traceability_keys(session_factory: async_sessionmaker):
    """Accepted objects must stash _v0_7, _function, _domain_family in entities_json."""
    doc_id, span_ids = await _seed_doc_with_spans(session_factory, n_spans=1)
    client = FakeLLMClient(responses=[_make_semantic_response(str(span_ids[0]), "GPT-5 released.")])
    graph = make_extraction_graph(session_factory, client)

    await graph.ainvoke(_initial_state(doc_id))

    async with session_factory() as session:
        claims = (
            (await session.execute(select(Claim).where(Claim.document_id == doc_id)))
            .scalars()
            .all()
        )
    assert len(claims) == 1
    ej = claims[0].entities_json
    assert ej["_domain_family"] == "model_system"
    assert ej["_function"] is not None
    assert isinstance(ej["_v0_7"], dict)
    assert ej["_v0_7"]["domain_object_type"] == "model_release"


@pytest.mark.asyncio
async def test_extraction_uses_extraction_model_override(session_factory: async_sessionmaker):
    """Span extraction passes settings.extraction_model instead of graph state model."""
    doc_id, span_ids = await _seed_doc_with_spans(session_factory, n_spans=1)
    client = FakeLLMClient(responses=[_make_semantic_response(str(span_ids[0]), "GPT-5 released.")])
    graph = make_extraction_graph(session_factory, client)

    with patch("app.intelligence.extraction.settings.extraction_model", "qwen3.6-flash-2026-04-16"):
        final = await graph.ainvoke(_initial_state(doc_id))

    assert final.get("error") is None
    assert len(client.calls) == 1
    assert client.calls[0]["model"] == "qwen3.6-flash-2026-04-16"
