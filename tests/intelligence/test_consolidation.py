"""DB-bound integration tests for consolidate_domain (E3 consolidation worker)."""

import uuid

import pytest
from sqlalchemy import func, select

from app.db.models import Document, SemanticCapsule, SemanticRelation, Source, Thesis
from app.domain_packs.loader import load_pack
from app.intelligence.consolidation import consolidate_domain

pytestmark = pytest.mark.slow


async def _seed_source_document(session):
    suffix = uuid.uuid4().hex
    source = Source(
        id=uuid.uuid4(),
        name="t",
        url=f"https://example.com/{suffix}",
        domain_pack="personal_ai_tech",
        source_type="rss",
    )
    document = Document(
        id=uuid.uuid4(),
        source_id=source.id,
        url=f"https://example.com/a/{suffix}",
        content_hash=f"h-{suffix}",
        status="embedded",
    )
    session.add_all([source, document])
    await session.commit()
    return source, document


async def _seed_capsule(
    session,
    *,
    source_id,
    document_id,
    family="model_release_event",
    text="t",
    salience=0.8,
):
    capsule = SemanticCapsule(
        id=uuid.uuid4(),
        source_id=source_id,
        document_id=document_id,
        idempotency_key=str(uuid.uuid4()),
        core_type="claim",
        text=text,
        domain="personal_ai_tech",
        object_family=family,
        domain_object_type="model_release",
        facets={},
        salience=salience,
        confidence=0.8,
        escalation_state="none",
        created_by_tier="t2",
    )
    session.add(capsule)
    await session.commit()
    return capsule


async def _seed_support_relation(session, *, source_id, target_id, strength=0.8):
    session.add(
        SemanticRelation(
            source_capsule_id=source_id,
            target_capsule_id=target_id,
            relation_type="supports",
            polarity="positive",
            strength=strength,
            confidence=0.8,
            created_by_tier="t2",
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_consolidate_domain_creates_thesis_from_strong_relations(session_factory):
    """Three connected capsules cluster into one thesis via consolidate_domain."""
    async with session_factory() as session:
        source, document = await _seed_source_document(session)
        cap_a = await _seed_capsule(
            session,
            source_id=source.id,
            document_id=document.id,
            text="GPT-5 scored 90% on MMLU.",
            salience=0.9,
        )
        cap_b = await _seed_capsule(
            session,
            source_id=source.id,
            document_id=document.id,
            text="GPT-5 leads benchmark leaderboards.",
        )
        cap_c = await _seed_capsule(
            session,
            source_id=source.id,
            document_id=document.id,
            text="GPT-4 scored 86% on MMLU.",
        )
        await _seed_support_relation(session, source_id=cap_a.id, target_id=cap_b.id)
        await _seed_support_relation(session, source_id=cap_b.id, target_id=cap_c.id)

    pack = load_pack("personal_ai_tech")
    async with session_factory() as session:
        report = await consolidate_domain(session, domain="personal_ai_tech", pack=pack)

    assert report.domain == "personal_ai_tech"
    assert report.theses_created == 1
    assert len(report.thesis_ids) == 1

    async with session_factory() as session:
        thesis = await session.get(Thesis, report.thesis_ids[0])
        assert thesis is not None
        assert set(thesis.supporting_capsule_ids) == {cap_a.id, cap_b.id, cap_c.id}
        assert thesis.created_by_tier == "t3"


@pytest.mark.asyncio
async def test_consolidate_domain_dry_run_does_not_persist(session_factory):
    async with session_factory() as session:
        source, document = await _seed_source_document(session)
        cap_a = await _seed_capsule(
            session,
            source_id=source.id,
            document_id=document.id,
            text="GPT-5 scored 90% on MMLU.",
        )
        cap_b = await _seed_capsule(
            session,
            source_id=source.id,
            document_id=document.id,
            text="GPT-4 scored 86% on MMLU.",
        )
        await _seed_support_relation(session, source_id=cap_a.id, target_id=cap_b.id)

    pack = load_pack("personal_ai_tech")
    async with session_factory() as session:
        report = await consolidate_domain(
            session, domain="personal_ai_tech", pack=pack, dry_run=True
        )

    assert report.theses_created == 1
    assert len(report.thesis_ids) == 1

    async with session_factory() as session:
        count = (
            await session.execute(
                select(func.count()).select_from(Thesis).where(Thesis.domain == "personal_ai_tech")
            )
        ).scalar_one()
        assert count == 0


@pytest.mark.asyncio
async def test_consolidate_domain_second_run_creates_nothing_new(session_factory):
    async with session_factory() as session:
        source, document = await _seed_source_document(session)
        cap_a = await _seed_capsule(
            session,
            source_id=source.id,
            document_id=document.id,
            text="GPT-5 scored 90% on MMLU.",
        )
        cap_b = await _seed_capsule(
            session,
            source_id=source.id,
            document_id=document.id,
            text="GPT-4 scored 86% on MMLU.",
        )
        await _seed_support_relation(session, source_id=cap_a.id, target_id=cap_b.id)

    pack = load_pack("personal_ai_tech")
    async with session_factory() as session:
        first = await consolidate_domain(session, domain="personal_ai_tech", pack=pack)
    assert first.theses_created == 1

    async with session_factory() as session:
        second = await consolidate_domain(session, domain="personal_ai_tech", pack=pack)

    assert second.theses_created == 0
    assert second.thesis_ids == []

    async with session_factory() as session:
        count = (
            await session.execute(
                select(func.count()).select_from(Thesis).where(Thesis.domain == "personal_ai_tech")
            )
        ).scalar_one()
        assert count == 1
