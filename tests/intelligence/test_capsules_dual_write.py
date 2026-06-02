"""DB-integration tests for the B2 dual-write: SemanticCapsule + CapsuleSegment
rows land in the same transaction as Claim + ClaimEvidence writes.

Requires Docker (testcontainers/postgres) or a local Postgres instance.
Tests that only need DB isolation use the session-scoped fixtures from
tests/conftest.py (which already handles Docker vs local fallback).

NOTE: these tests require a running Postgres with the pgvector extension.
They cannot run locally without Docker or a pre-existing Nexus dev DB.
They will run in CI via the testcontainers path.
"""

from __future__ import annotations

import hashlib
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import (
    CapsuleSegment,
    Claim,
    ClaimEvidence,
    Document,
    SemanticCapsule,
    Source,
    Span,
)
from app.intelligence.extraction import make_extraction_graph
from app.intelligence.projection import build_capsule_idempotency_key

# ---------------------------------------------------------------------------
# Fake LLM client (no HTTP calls)
# ---------------------------------------------------------------------------


class FakeLLMClient:
    def __init__(self, responses: list) -> None:
        self._responses = iter(responses)
        self.calls: list = []

    async def complete_json(self, *, model, system, user, response_model, **kwargs):
        self.calls.append({"user": user})
        resp = next(self._responses)
        if isinstance(resp, BaseException):
            raise resp
        return response_model.model_validate(resp), 100


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


async def _seed_doc(
    session_factory: async_sessionmaker,
    *,
    n_spans: int = 1,
    status: str = "embedded",
) -> tuple[uuid.UUID, uuid.UUID, list[uuid.UUID]]:
    """Return (doc_id, source_id, span_ids)."""
    async with session_factory() as session:
        src = Source(
            name="Test Source",
            source_type="rss",
            url=f"https://test-{uuid.uuid4()}.example/feed",
            domain_pack="personal_ai_tech",
        )
        session.add(src)
        await session.flush()
        doc = Document(
            source_id=src.id,
            title="Test Doc",
            clean_text="x" * 100,
            content_hash=f"h-{uuid.uuid4()}",
            status=status,
        )
        session.add(doc)
        await session.flush()
        span_ids: list[uuid.UUID] = []
        for i in range(n_spans):
            span = Span(
                document_id=doc.id,
                span_index=i,
                text=f"GPT-5 released (span {i}).",
                token_count=10,
                metadata_json={"title": "Test Doc", "source_name": "Test Source"},
            )
            session.add(span)
            await session.flush()
            span_ids.append(span.id)
        await session.commit()
        return doc.id, src.id, span_ids


def _semantic_response(span_ids: list[str], *, claim_text: str = "GPT-5 was released.") -> dict:
    """Build a SemanticExtractionOutput-compatible dict with source_refs pointing to span_ids."""
    return {
        "objects": [
            {
                "source_refs": span_ids,
                "core_type": "event",
                "domain_family": "model_system",
                "domain_object_type": "model_release",
                "function": "Marks a new model version entering availability.",
                "text": claim_text,
                "original_text": None,
                "facets": {"orgs": ["OpenAI"], "models": ["GPT-5"]},
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


def _initial_state(doc_id: uuid.UUID) -> dict:
    return {
        "document_id": doc_id,
        "run_id": None,
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
async def test_happy_path_single_object(session_factory: async_sessionmaker):
    """1 SemanticObject → 1 Claim + 1 ClaimEvidence + 1 SemanticCapsule + 1 CapsuleSegment."""
    doc_id, source_id, span_ids = await _seed_doc(session_factory, n_spans=1)

    client = FakeLLMClient(
        responses=[_semantic_response([str(span_ids[0])], claim_text="GPT-5 was released.")]
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
        claim = claims[0]

        evidences = (
            (await session.execute(select(ClaimEvidence).where(ClaimEvidence.claim_id == claim.id)))
            .scalars()
            .all()
        )
        assert len(evidences) == 1

        capsules = (
            (
                await session.execute(
                    select(SemanticCapsule).where(SemanticCapsule.document_id == doc_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(capsules) == 1
        cap = capsules[0]

        # Verify capsule field mapping (§6)
        assert cap.id is not None
        assert cap.source_id == source_id
        assert cap.document_id == doc_id
        assert cap.claim_id == claim.id
        assert cap.core_type == "event"
        assert cap.text == "GPT-5 was released."
        assert cap.domain == "personal_ai_tech"
        assert cap.object_family == "model_system"
        assert cap.domain_object_type == "model_release"
        assert cap.lifecycle_state == "active"
        assert cap.escalation_state == "none"
        assert cap.created_by_tier == "t2"
        assert cap.created_by_model == "deepseek/deepseek-v4-flash"
        assert cap.confidence == pytest.approx(0.92)
        assert cap.salience == pytest.approx(0.9)
        # Embedding: 384-dim vector
        assert cap.embedding is not None
        assert len(cap.embedding) == 384

        # idempotency_key must be deterministic
        expected_key = build_capsule_idempotency_key(
            document_id=doc_id,
            source_refs=[str(span_ids[0])],
            domain_object_type="model_release",
            text="GPT-5 was released.",
        )
        assert cap.idempotency_key == expected_key

        # CapsuleSegment
        segments = (
            (
                await session.execute(
                    select(CapsuleSegment).where(CapsuleSegment.capsule_id == cap.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(segments) == 1
        assert segments[0].segment_id == span_ids[0]
        assert segments[0].role == "grounds"


@pytest.mark.asyncio
async def test_multi_source_refs(session_factory: async_sessionmaker):
    """An object with 2 source_refs → 1 Capsule + 2 CapsuleSegment rows."""
    doc_id, source_id, span_ids = await _seed_doc(session_factory, n_spans=2)

    # Single object referencing both spans
    client = FakeLLMClient(responses=[_semantic_response([str(span_ids[0]), str(span_ids[1])])])
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
        claim = claims[0]

        capsules = (
            (
                await session.execute(
                    select(SemanticCapsule).where(SemanticCapsule.document_id == doc_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(capsules) == 1

        segments = (
            (
                await session.execute(
                    select(CapsuleSegment).where(CapsuleSegment.capsule_id == capsules[0].id)
                )
            )
            .scalars()
            .all()
        )
        assert len(segments) == 2
        segment_ids = {s.segment_id for s in segments}
        assert segment_ids == set(span_ids)

        evidences = (
            (await session.execute(select(ClaimEvidence).where(ClaimEvidence.claim_id == claim.id)))
            .scalars()
            .all()
        )
        assert len(evidences) == 2


@pytest.mark.asyncio
async def test_transaction_atomicity(session_factory: async_sessionmaker):
    """If the session commit fails, neither Claim nor Capsule rows are written."""
    doc_id, source_id, span_ids = await _seed_doc(session_factory, n_spans=1)

    client = FakeLLMClient(responses=[_semantic_response([str(span_ids[0])])])
    graph = make_extraction_graph(session_factory, client)

    # Patch session.commit to raise IntegrityError on the first call (store_claims transaction)
    original_commit_count = 0

    import sqlalchemy.ext.asyncio as _sa_async

    original_commit = _sa_async.AsyncSession.commit

    commit_count = [0]

    async def failing_commit(self):
        commit_count[0] += 1
        if commit_count[0] == 1:
            raise IntegrityError("simulated", {}, Exception("forced"))
        return await original_commit(self)

    with patch.object(_sa_async.AsyncSession, "commit", failing_commit):
        final = await graph.ainvoke(_initial_state(doc_id))

    # The graph catches the error internally and update_status still runs,
    # but no rows should have been committed.
    async with session_factory() as session:
        claims = (
            (await session.execute(select(Claim).where(Claim.document_id == doc_id)))
            .scalars()
            .all()
        )
        assert len(claims) == 0

        capsules = (
            (
                await session.execute(
                    select(SemanticCapsule).where(SemanticCapsule.document_id == doc_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(capsules) == 0


@pytest.mark.asyncio
async def test_embedding_present(session_factory: async_sessionmaker):
    """The embedding column is a 384-element vector after dual-write (not NULL)."""
    doc_id, _, span_ids = await _seed_doc(session_factory, n_spans=1)

    client = FakeLLMClient(responses=[_semantic_response([str(span_ids[0])])])
    graph = make_extraction_graph(session_factory, client)
    await graph.ainvoke(_initial_state(doc_id))

    async with session_factory() as session:
        cap = (
            await session.execute(
                select(SemanticCapsule).where(SemanticCapsule.document_id == doc_id)
            )
        ).scalar_one()

        assert cap.embedding is not None
        assert len(cap.embedding) == 384
        # All values should be finite floats (not nan/inf from a broken model load)
        import math

        assert all(math.isfinite(v) for v in cap.embedding)


def test_idempotency_key_is_deterministic():
    """Same inputs always produce the same idempotency_key (no randomness)."""
    doc_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    source_refs = ["aaa", "bbb"]
    dot = "model_release"
    text = "GPT-5 was released."

    key1 = build_capsule_idempotency_key(
        document_id=doc_id, source_refs=source_refs, domain_object_type=dot, text=text
    )
    key2 = build_capsule_idempotency_key(
        document_id=doc_id, source_refs=source_refs, domain_object_type=dot, text=text
    )
    assert key1 == key2

    # Order of source_refs must not matter (sorted internally)
    key3 = build_capsule_idempotency_key(
        document_id=doc_id, source_refs=["bbb", "aaa"], domain_object_type=dot, text=text
    )
    assert key1 == key3

    # Different text → different key
    key4 = build_capsule_idempotency_key(
        document_id=doc_id, source_refs=source_refs, domain_object_type=dot, text="Different text."
    )
    assert key1 != key4

    # Verify the sha256 component manually
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    expected = f"{doc_id}:aaa,bbb:{dot}:{text_hash}"
    assert key1 == expected
