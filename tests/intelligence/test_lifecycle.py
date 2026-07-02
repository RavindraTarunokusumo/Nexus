"""DB-bound integration tests for apply_lifecycle_transitions."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.db.models import Document, SemanticCapsule, SemanticRelation, Source
from app.domain_packs.loader import load_pack
from app.intelligence.lifecycle import apply_lifecycle_transitions

pytestmark = pytest.mark.slow

_DOMAIN = "personal_ai_tech"
_NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


async def _seed_source_document(session):
    suffix = uuid.uuid4().hex
    source = Source(
        id=uuid.uuid4(),
        name="t",
        url=f"https://example.com/{suffix}",
        domain_pack=_DOMAIN,
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
    lifecycle_state: str = "active",
    domain_object_type: str = "model_release",
    core_type: str = "claim",
    facets: dict | None = None,
    epistemic_state: dict | None = None,
    created_at: datetime | None = None,
    text: str = "t",
):
    capsule = SemanticCapsule(
        id=uuid.uuid4(),
        source_id=source_id,
        document_id=document_id,
        idempotency_key=str(uuid.uuid4()),
        core_type=core_type,
        text=text,
        domain=_DOMAIN,
        object_family="model_release_event",
        domain_object_type=domain_object_type,
        facets=facets or {},
        epistemic_state=epistemic_state or {},
        salience=0.8,
        confidence=0.8,
        lifecycle_state=lifecycle_state,
        escalation_state="none",
        created_by_tier="t2",
        created_at=created_at or _NOW,
        updated_at=created_at or _NOW,
    )
    session.add(capsule)
    await session.commit()
    return capsule


def _minimal_pack(**retention_overrides):
    pack = load_pack(_DOMAIN)
    return pack.model_copy(
        update={"retention_policy": pack.retention_policy.model_copy(update=retention_overrides)}
    )


@pytest.mark.asyncio
async def test_superseded_by_incoming_relation(session_factory):
    pack = load_pack(_DOMAIN)
    async with session_factory() as session:
        source, document = await _seed_source_document(session)
        older = await _seed_capsule(session, source_id=source.id, document_id=document.id)
        newer = await _seed_capsule(session, source_id=source.id, document_id=document.id)
        session.add(
            SemanticRelation(
                source_capsule_id=newer.id,
                target_capsule_id=older.id,
                relation_type="supersedes",
                strength=0.9,
                confidence=0.9,
                created_by_tier="t2",
            )
        )
        await session.commit()

    async with session_factory() as session:
        report = await apply_lifecycle_transitions(
            session, domain=_DOMAIN, pack=pack, now=_NOW, dry_run=False
        )

    assert report.counts.get("superseded") == 1
    assert report.transitions[0].capsule_id == older.id
    async with session_factory() as session:
        refreshed = await session.get(SemanticCapsule, older.id)
        assert refreshed is not None
        assert refreshed.lifecycle_state == "superseded"


@pytest.mark.asyncio
async def test_superseded_by_heuristic(session_factory):
    pack = load_pack(_DOMAIN)
    assert pack.retention_policy.supersession_rules
    old_time = _NOW - timedelta(days=10)
    new_time = _NOW - timedelta(days=1)
    async with session_factory() as session:
        source, document = await _seed_source_document(session)
        older = await _seed_capsule(
            session,
            source_id=source.id,
            document_id=document.id,
            core_type="state_change",
            domain_object_type="pricing_change",
            facets={"orgs": ["OpenAI"]},
            created_at=old_time,
        )
        await _seed_capsule(
            session,
            source_id=source.id,
            document_id=document.id,
            core_type="state_change",
            domain_object_type="pricing_change",
            facets={"orgs": ["openai"]},
            created_at=new_time,
        )

    async with session_factory() as session:
        report = await apply_lifecycle_transitions(
            session, domain=_DOMAIN, pack=pack, now=_NOW, dry_run=False
        )

    assert report.counts.get("superseded") == 1
    assert report.transitions[0].capsule_id == older.id
    assert report.transitions[0].reason == "supersession_heuristic"


@pytest.mark.asyncio
async def test_heuristic_does_not_supersede_historical_events(session_factory):
    """A newer same-actor/same-type event must not supersede an older event —
    historical facts (e.g. a GA date) stay retrievable. Only state_change does."""
    pack = load_pack(_DOMAIN)
    old_time = _NOW - timedelta(days=10)
    new_time = _NOW - timedelta(days=1)
    async with session_factory() as session:
        source, document = await _seed_source_document(session)
        older = await _seed_capsule(
            session,
            source_id=source.id,
            document_id=document.id,
            core_type="event",
            facets={"orgs": ["Lumina"]},
            created_at=old_time,
        )
        await _seed_capsule(
            session,
            source_id=source.id,
            document_id=document.id,
            core_type="event",
            facets={"orgs": ["lumina"]},
            created_at=new_time,
        )

    async with session_factory() as session:
        report = await apply_lifecycle_transitions(
            session, domain=_DOMAIN, pack=pack, now=_NOW, dry_run=False
        )

    assert report.counts.get("superseded") is None
    async with session_factory() as session:
        refreshed = await session.get(SemanticCapsule, older.id)
        assert refreshed is not None
        assert refreshed.lifecycle_state == "active"


@pytest.mark.asyncio
async def test_contradicted_by_higher_authority(session_factory):
    pack = _minimal_pack()
    async with session_factory() as session:
        source, document = await _seed_source_document(session)
        low = await _seed_capsule(
            session,
            source_id=source.id,
            document_id=document.id,
            epistemic_state={"source_authority": "tertiary"},
        )
        high = await _seed_capsule(
            session,
            source_id=source.id,
            document_id=document.id,
            epistemic_state={"source_authority": "primary"},
        )
        session.add(
            SemanticRelation(
                source_capsule_id=high.id,
                target_capsule_id=low.id,
                relation_type="contradicts",
                strength=0.9,
                confidence=0.9,
                created_by_tier="t2",
            )
        )
        await session.commit()

    async with session_factory() as session:
        report = await apply_lifecycle_transitions(
            session, domain=_DOMAIN, pack=pack, now=_NOW, dry_run=False
        )

    assert report.counts.get("contradicted") == 1
    assert report.transitions[0].capsule_id == low.id


@pytest.mark.asyncio
async def test_qualified_by_incoming_relation(session_factory):
    pack = _minimal_pack()
    async with session_factory() as session:
        source, document = await _seed_source_document(session)
        target = await _seed_capsule(session, source_id=source.id, document_id=document.id)
        qualifier = await _seed_capsule(session, source_id=source.id, document_id=document.id)
        session.add(
            SemanticRelation(
                source_capsule_id=qualifier.id,
                target_capsule_id=target.id,
                relation_type="qualifies",
                strength=0.8,
                confidence=0.8,
                created_by_tier="t2",
            )
        )
        await session.commit()

    async with session_factory() as session:
        report = await apply_lifecycle_transitions(
            session, domain=_DOMAIN, pack=pack, now=_NOW, dry_run=False
        )

    assert report.counts.get("qualified") == 1
    assert report.transitions[0].capsule_id == target.id


@pytest.mark.asyncio
async def test_confirmed_by_multiple_supporting_relations(session_factory):
    pack = _minimal_pack()
    async with session_factory() as session:
        source, document = await _seed_source_document(session)
        target = await _seed_capsule(session, source_id=source.id, document_id=document.id)
        sup_a = await _seed_capsule(session, source_id=source.id, document_id=document.id)
        sup_b = await _seed_capsule(session, source_id=source.id, document_id=document.id)
        session.add_all(
            [
                SemanticRelation(
                    source_capsule_id=sup_a.id,
                    target_capsule_id=target.id,
                    relation_type="supports",
                    polarity="positive",
                    strength=0.8,
                    confidence=0.8,
                    created_by_tier="t2",
                ),
                SemanticRelation(
                    source_capsule_id=sup_b.id,
                    target_capsule_id=target.id,
                    relation_type="supports",
                    polarity="positive",
                    strength=0.7,
                    confidence=0.7,
                    created_by_tier="t2",
                ),
            ]
        )
        await session.commit()

    async with session_factory() as session:
        report = await apply_lifecycle_transitions(
            session, domain=_DOMAIN, pack=pack, now=_NOW, dry_run=False
        )

    assert report.counts.get("confirmed") == 1
    assert report.transitions[0].capsule_id == target.id


@pytest.mark.asyncio
async def test_stale_forecast_and_cold_capsule(session_factory):
    pack = load_pack(_DOMAIN)
    assert pack.retention_policy.stale_conditions
    warm_cutoff = _NOW - timedelta(days=pack.retention_policy.warm_window_days + 1)
    cold_cutoff = _NOW - timedelta(days=pack.retention_policy.cold_after_days + 1)
    async with session_factory() as session:
        source, document = await _seed_source_document(session)
        forecast = await _seed_capsule(
            session,
            source_id=source.id,
            document_id=document.id,
            domain_object_type="forecast",
            created_at=warm_cutoff,
        )
        await _seed_capsule(
            session,
            source_id=source.id,
            document_id=document.id,
            domain_object_type="model_release",
            created_at=cold_cutoff,
        )

    async with session_factory() as session:
        report = await apply_lifecycle_transitions(
            session, domain=_DOMAIN, pack=pack, now=_NOW, dry_run=False
        )

    assert report.counts.get("stale") == 2
    stale_ids = {t.capsule_id for t in report.transitions if t.to_state == "stale"}
    assert forecast.id in stale_ids


@pytest.mark.asyncio
async def test_archived_after_retention_days(session_factory):
    pack = _minimal_pack(archive_after_days=30, stale_conditions=[])
    old_time = _NOW - timedelta(days=31)
    async with session_factory() as session:
        source, document = await _seed_source_document(session)
        capsule = await _seed_capsule(
            session,
            source_id=source.id,
            document_id=document.id,
            created_at=old_time,
        )

    async with session_factory() as session:
        report = await apply_lifecycle_transitions(
            session, domain=_DOMAIN, pack=pack, now=_NOW, dry_run=False
        )

    assert report.counts.get("archived") == 1
    assert report.transitions[0].capsule_id == capsule.id


@pytest.mark.asyncio
async def test_precedence_superseded_over_contradicted(session_factory):
    pack = _minimal_pack(supersession_rules=["same actor supersedes"])
    old_time = _NOW - timedelta(days=5)
    new_time = _NOW - timedelta(days=1)
    async with session_factory() as session:
        source, document = await _seed_source_document(session)
        older = await _seed_capsule(
            session,
            source_id=source.id,
            document_id=document.id,
            core_type="state_change",
            domain_object_type="pricing_change",
            facets={"orgs": ["Acme"]},
            epistemic_state={"source_authority": "tertiary"},
            created_at=old_time,
        )
        newer = await _seed_capsule(
            session,
            source_id=source.id,
            document_id=document.id,
            core_type="state_change",
            domain_object_type="pricing_change",
            facets={"orgs": ["acme"]},
            epistemic_state={"source_authority": "primary"},
            created_at=new_time,
        )
        session.add(
            SemanticRelation(
                source_capsule_id=newer.id,
                target_capsule_id=older.id,
                relation_type="contradicts",
                strength=0.9,
                confidence=0.9,
                created_by_tier="t2",
            )
        )
        await session.commit()

    async with session_factory() as session:
        report = await apply_lifecycle_transitions(
            session, domain=_DOMAIN, pack=pack, now=_NOW, dry_run=False
        )

    assert len(report.transitions) == 1
    assert report.transitions[0].capsule_id == older.id
    assert report.transitions[0].to_state == "superseded"


@pytest.mark.asyncio
async def test_dry_run_rolls_back_transitions(session_factory):
    pack = _minimal_pack(archive_after_days=1, stale_conditions=[])
    old_time = _NOW - timedelta(days=10)
    async with session_factory() as session:
        source, document = await _seed_source_document(session)
        capsule = await _seed_capsule(
            session,
            source_id=source.id,
            document_id=document.id,
            created_at=old_time,
        )

    async with session_factory() as session:
        report = await apply_lifecycle_transitions(
            session, domain=_DOMAIN, pack=pack, now=_NOW, dry_run=True
        )

    assert report.counts.get("archived") == 1
    async with session_factory() as session:
        refreshed = await session.get(SemanticCapsule, capsule.id)
        assert refreshed is not None
        assert refreshed.lifecycle_state == "active"


@pytest.mark.asyncio
async def test_terminal_state_capsule_untouched(session_factory):
    pack = _minimal_pack(archive_after_days=1, stale_conditions=[])
    old_time = _NOW - timedelta(days=10)
    async with session_factory() as session:
        source, document = await _seed_source_document(session)
        capsule = await _seed_capsule(
            session,
            source_id=source.id,
            document_id=document.id,
            lifecycle_state="archived",
            created_at=old_time,
        )

    async with session_factory() as session:
        report = await apply_lifecycle_transitions(
            session, domain=_DOMAIN, pack=pack, now=_NOW, dry_run=False
        )

    assert report.transitions == []
    async with session_factory() as session:
        refreshed = await session.get(SemanticCapsule, capsule.id)
        assert refreshed is not None
        assert refreshed.lifecycle_state == "archived"
