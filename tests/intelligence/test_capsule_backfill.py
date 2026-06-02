"""Tests for B3 — backfill_capsules and capsule_from_claim.

Unit tests (no DB):
  - test_capsule_from_claim_pure_function

DB-bound tests (require Docker or a running Postgres with pgvector):
  - test_backfill_idempotent
  - test_backfill_dry_run
  - test_backfill_skips_phase_a_claim_without_v07_key
  - test_backfill_multi_source_ref

NOTE: The DB-bound tests require a running Postgres instance with pgvector.
They cannot run locally without Docker (testcontainers) or a pre-existing
Nexus dev DB at postgresql+asyncpg://nexus:nexus@localhost:5432/nexus.
They run automatically in CI via the testcontainers path in tests/db/conftest.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
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
from app.intelligence.backfill import BackfillResult, backfill_capsules, capsule_from_claim
from app.intelligence.projection import build_capsule_idempotency_key

# ---------------------------------------------------------------------------
# Helpers — build minimal Claim / v0_7 payload dicts
# ---------------------------------------------------------------------------

_NOW = datetime(2025, 1, 1, tzinfo=timezone.utc)

_SPAN_ID_A = uuid.uuid4()
_SPAN_ID_B = uuid.uuid4()
_SPAN_ID_C = uuid.uuid4()


def _make_v07(
    *,
    span_ids: list[uuid.UUID],
    text: str = "GPT-5 was released.",
    core_type: str = "event",
    domain_family: str = "model_system",
    domain_object_type: str = "model_release",
    function: str = "Marks a new model version entering availability.",
    salience: float = 0.9,
    confidence: float = 0.92,
    needs_escalation: bool = False,
) -> dict:
    """Return a _v0_7 blob matching what projection.project() writes."""
    return {
        "source_refs": [str(s) for s in span_ids],
        "core_type": core_type,
        "domain_family": domain_family,
        "domain_object_type": domain_object_type,
        "function": function,
        "text": text,
        "original_text": None,
        "facets": {"orgs": ["OpenAI"], "models": ["GPT-5"]},
        "epistemic": {
            "status": "reported",
            "source_authority": "primary",
            "confidence": confidence,
            "evidence_quality": "high",
            "uncertainty": None,
            "needs_escalation": needs_escalation,
        },
        "salience": salience,
        "mvp_claim_type": "model_release",
    }


class _FakeClaim:
    """Minimal stand-in for app.db.models.Claim used in pure unit tests (no SA session)."""

    def __init__(
        self,
        *,
        doc_id: uuid.UUID,
        span_ids: list[uuid.UUID],
        text: str = "GPT-5 was released.",
        domain_object_type: str = "model_release",
        status: str = "active",
    ) -> None:
        v07 = _make_v07(span_ids=span_ids, text=text, domain_object_type=domain_object_type)
        self.id: uuid.UUID = uuid.uuid4()
        self.document_id: uuid.UUID = doc_id
        self.claim_text: str = text
        self.claim_type: str = "model_release"
        self.entities_json: dict = {
            "_function": "Marks a new model version entering availability.",
            "_domain_family": "model_system",
            "_v0_7": v07,
        }
        self.topics_json: dict = {}
        self.confidence: float = v07["epistemic"]["confidence"]
        self.status: str = status
        self.created_at: datetime = _NOW


# ---------------------------------------------------------------------------
# Seed helpers (DB-bound tests)
# ---------------------------------------------------------------------------


async def _seed_source_doc_spans(
    session_factory: async_sessionmaker,
    *,
    n_spans: int = 1,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, list[uuid.UUID]]:
    """Return (source_id, doc_id, claim_id, span_ids) after seeding all rows."""
    async with session_factory() as session:
        src = Source(
            name="Backfill Test Source",
            source_type="rss",
            url=f"https://backfill-test-{uuid.uuid4()}.example/feed",
            domain_pack="personal_ai_tech",
        )
        session.add(src)
        await session.flush()

        doc = Document(
            source_id=src.id,
            title="Backfill Test Doc",
            clean_text="x" * 100,
            content_hash=f"h-{uuid.uuid4()}",
            status="claims_extracted",
        )
        session.add(doc)
        await session.flush()

        span_ids: list[uuid.UUID] = []
        for i in range(n_spans):
            span = Span(
                document_id=doc.id,
                span_index=i,
                text=f"Test span {i}.",
                token_count=10,
            )
            session.add(span)
            await session.flush()
            span_ids.append(span.id)

        await session.commit()
        return src.id, doc.id, span_ids


async def _seed_claim_with_v07(
    session_factory: async_sessionmaker,
    *,
    doc_id: uuid.UUID,
    span_ids: list[uuid.UUID],
    text: str = "GPT-5 was released.",
) -> uuid.UUID:
    """Insert a Claim + ClaimEvidence rows. Returns claim_id."""
    v07 = _make_v07(span_ids=span_ids, text=text)
    async with session_factory() as session:
        claim = Claim(
            document_id=doc_id,
            claim_text=text,
            claim_type="model_release",
            entities_json={
                "_function": "Marks a new model version entering availability.",
                "_domain_family": "model_system",
                "_v0_7": v07,
            },
            topics_json={},
            confidence=0.92,
            status="active",
        )
        session.add(claim)
        await session.flush()
        for span_id in span_ids:
            ev = ClaimEvidence(
                claim_id=claim.id,
                span_id=span_id,
                evidence_role="support",
                confidence=0.92,
            )
            session.add(ev)
        claim_id = claim.id
        await session.commit()
    return claim_id


# ---------------------------------------------------------------------------
# Unit test — no DB
# ---------------------------------------------------------------------------


def test_capsule_from_claim_pure_function():
    """Pure unit: capsule_from_claim maps _v0_7 fields to capsule columns correctly.

    Verifies:
    - idempotency_key matches build_capsule_idempotency_key output exactly.
    - N segments == len(source_refs).
    - Every capsule field matches the plan §6 mapping.
    """
    doc_id = uuid.uuid4()
    source_id = uuid.uuid4()
    span_id = uuid.uuid4()
    dummy_embedding = [0.0] * 384

    claim = _FakeClaim(doc_id=doc_id, span_ids=[span_id])
    v07 = claim.entities_json["_v0_7"]

    capsule, segments = capsule_from_claim(
        claim,
        source_id=source_id,
        domain="personal_ai_tech",
        source_telos="Track the AI landscape.",
        embedding=dummy_embedding,
    )

    # idempotency_key must match the shared formula
    expected_key = build_capsule_idempotency_key(
        document_id=doc_id,
        source_refs=[str(span_id)],
        domain_object_type="model_release",
        text="GPT-5 was released.",
    )
    assert capsule.idempotency_key == expected_key

    # Deterministic UUID from the idempotency key
    assert capsule.id == uuid.uuid5(uuid.NAMESPACE_OID, expected_key)

    # Field-by-field mapping (plan §6)
    assert capsule.source_id == source_id
    assert capsule.document_id == doc_id
    assert capsule.claim_id == claim.id
    assert capsule.core_type == v07["core_type"]
    assert capsule.text == v07["text"]
    assert capsule.domain == "personal_ai_tech"
    assert capsule.source_telos == "Track the AI landscape."
    assert capsule.object_family == v07["domain_family"]
    assert capsule.domain_object_type == v07["domain_object_type"]
    assert capsule.function == v07["function"]
    assert capsule.facets == v07["facets"]
    assert capsule.epistemic_state == v07["epistemic"]
    assert capsule.salience == v07["salience"]
    assert capsule.confidence == v07["epistemic"]["confidence"]
    assert capsule.lifecycle_state == "active"
    assert capsule.escalation_state == "none"
    assert capsule.embedding == dummy_embedding
    assert capsule.created_by_tier == "backfill"
    assert capsule.created_by_model is None
    assert capsule.created_at == _NOW

    # One segment per source_ref
    assert len(segments) == 1
    assert segments[0].capsule_id == capsule.id
    assert segments[0].segment_id == span_id
    assert segments[0].role == "grounds"


# ---------------------------------------------------------------------------
# DB-bound tests
# ---------------------------------------------------------------------------


pytestmark_db = pytest.mark.asyncio


@pytest.mark.asyncio
async def test_backfill_idempotent(session_factory: async_sessionmaker):
    """Running backfill twice produces no duplicate capsule rows.

    NOTE: requires Docker (testcontainers) or a local Postgres with pgvector.
    """
    src_id, doc_id, span_ids = await _seed_source_doc_spans(session_factory, n_spans=1)
    await _seed_claim_with_v07(session_factory, doc_id=doc_id, span_ids=span_ids)

    result1 = await backfill_capsules(session_factory, dry_run=False)
    assert result1.capsules_written >= 1
    assert result1.errors == []

    # Second run — same claim is already backfilled.
    result2 = await backfill_capsules(session_factory, dry_run=False)
    assert result2.claims_skipped_already_backfilled >= 1
    assert result2.capsules_written == 0

    # Confirm no duplicate capsule rows exist.
    async with session_factory() as session:
        count = len(
            (await session.execute(select(SemanticCapsule).where(
                SemanticCapsule.document_id == doc_id
            ))).scalars().all()
        )
    assert count == 1


@pytest.mark.asyncio
async def test_backfill_dry_run(session_factory: async_sessionmaker):
    """--dry-run reports would-write counts but leaves no rows in DB.

    NOTE: requires Docker (testcontainers) or a local Postgres with pgvector.
    """
    src_id, doc_id, span_ids = await _seed_source_doc_spans(session_factory, n_spans=1)
    await _seed_claim_with_v07(session_factory, doc_id=doc_id, span_ids=span_ids)

    result = await backfill_capsules(session_factory, dry_run=True)

    # Should report at least one would-be capsule write.
    assert result.capsules_written >= 1

    # But no rows actually committed.
    async with session_factory() as session:
        caps = (
            (await session.execute(select(SemanticCapsule).where(
                SemanticCapsule.document_id == doc_id
            ))).scalars().all()
        )
    assert len(caps) == 0


@pytest.mark.asyncio
async def test_backfill_skips_phase_a_claim_without_v07_key(
    session_factory: async_sessionmaker,
):
    """Claims without _v0_7 key in entities_json are skipped with no error.

    NOTE: requires Docker (testcontainers) or a local Postgres with pgvector.
    """
    src_id, doc_id, span_ids = await _seed_source_doc_spans(session_factory, n_spans=1)

    # Insert claim WITHOUT _v0_7 key.
    async with session_factory() as session:
        claim = Claim(
            document_id=doc_id,
            claim_text="Some legacy claim.",
            claim_type="observation",
            entities_json={"foo": "bar"},
            topics_json={},
            confidence=0.5,
            status="active",
        )
        session.add(claim)
        await session.commit()

    result = await backfill_capsules(session_factory, dry_run=False)

    assert result.claims_skipped_no_v07 >= 1
    assert result.capsules_written == 0
    assert result.errors == []

    async with session_factory() as session:
        caps = (
            (await session.execute(select(SemanticCapsule).where(
                SemanticCapsule.document_id == doc_id
            ))).scalars().all()
        )
    assert len(caps) == 0


@pytest.mark.asyncio
async def test_backfill_multi_source_ref(session_factory: async_sessionmaker):
    """A claim with 3 source_refs produces 1 capsule + 3 capsule_segment rows.

    NOTE: requires Docker (testcontainers) or a local Postgres with pgvector.
    """
    src_id, doc_id, span_ids = await _seed_source_doc_spans(session_factory, n_spans=3)
    assert len(span_ids) == 3

    await _seed_claim_with_v07(session_factory, doc_id=doc_id, span_ids=span_ids)

    result = await backfill_capsules(session_factory, dry_run=False)

    assert result.capsules_written >= 1
    assert result.capsule_segments_written >= 3
    assert result.errors == []

    async with session_factory() as session:
        caps = (
            (await session.execute(select(SemanticCapsule).where(
                SemanticCapsule.document_id == doc_id
            ))).scalars().all()
        )
        assert len(caps) == 1
        cap = caps[0]

        segs = (
            (await session.execute(select(CapsuleSegment).where(
                CapsuleSegment.capsule_id == cap.id
            ))).scalars().all()
        )
        assert len(segs) == 3
        seg_span_ids = {s.segment_id for s in segs}
        assert seg_span_ids == set(span_ids)
