"""DB-bound integration tests for judge_capsules, classify_relations, and the
C3a thesis-clustering round trip. Real Postgres via tests/conftest.py fixtures;
LLM client mocked.

Run: pytest tests/intelligence/test_reasoning_layer_db.py -v -m slow
"""

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.db.models import Document, SemanticCapsule, SemanticRelation, Source
from app.domain_packs.loader import load_pack
from app.intelligence.extraction import _run_classify_relations
from app.intelligence.prompts.classify_relations import RelationClassification
from app.intelligence.prompts.judge_semantic_object import JudgeVerdict
from app.intelligence.theses import synthesize_theses_from_relations

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
    escalation_state="none",
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
        salience=0.8,
        confidence=0.8,
        escalation_state=escalation_state,
        created_by_tier="t2",
    )
    session.add(capsule)
    await session.commit()
    return capsule


@pytest.mark.asyncio
async def test_judge_capsules_writes_real_relation_row(session_factory):
    async with session_factory() as session:
        source, document = await _seed_source_document(session)
        capsule = await _seed_capsule(
            session,
            source_id=source.id,
            document_id=document.id,
            escalation_state="flagged",
        )

    from app.intelligence.extraction import make_extraction_graph

    mock_client = AsyncMock()
    mock_client.complete_json.return_value = (
        JudgeVerdict(
            evidence_sufficient=False,
            escalate=True,
            rationale="needs review",
            recommended_confidence=0.4,
        ),
        10,
    )
    graph = make_extraction_graph(session_factory, mock_client)
    judge_capsules_node = graph.nodes["judge_capsules"].bound

    pack = load_pack("personal_ai_tech")
    state = {
        "error": None,
        "pack": pack,
        "model": "test-model",
        "stored_capsule_ids": [capsule.id],
        "t2_calls_used": 0,
    }
    result = await judge_capsules_node.ainvoke(state)

    assert len(result["judge_results"]) == 1
    async with session_factory() as session:
        rel = (
            await session.execute(
                select(SemanticRelation).where(SemanticRelation.source_capsule_id == capsule.id)
            )
        ).scalar_one()
        assert rel.target_capsule_id == capsule.id  # unary self-reference
        assert rel.domain_relation_type == "judge_escalated"

        refreshed = await session.get(SemanticCapsule, capsule.id)
        assert refreshed is not None
        assert refreshed.escalation_state == "escalated"


@pytest.mark.asyncio
async def test_classify_relations_writes_real_binary_relation(session_factory):
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

    mock_client = AsyncMock()
    mock_client.complete_json.return_value = (
        RelationClassification(
            relation_type="supports",
            polarity="positive",
            strength=0.8,
            rationale="both benchmark MMLU",
        ),
        10,
    )
    pack = load_pack("personal_ai_tech")
    state = {
        "error": None,
        "pack": pack,
        "model": "test-model",
        "stored_capsule_ids": [cap_a.id, cap_b.id],
        "t2_calls_used": 0,
    }
    result = await _run_classify_relations(state, session_factory, mock_client)

    assert len(result["relation_ids"]) == 1
    async with session_factory() as session:
        rel = (
            await session.execute(
                select(SemanticRelation).where(SemanticRelation.id == result["relation_ids"][0])
            )
        ).scalar_one()
        assert {rel.source_capsule_id, rel.target_capsule_id} == {cap_a.id, cap_b.id}
        assert rel.relation_type == "supports"


@pytest.mark.asyncio
async def test_classify_relations_to_thesis_round_trip(session_factory):
    """C1(implicit)->C2->C3a: real relation rows cluster into a real Thesis row."""
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

    mock_client = AsyncMock()
    mock_client.complete_json.return_value = (
        RelationClassification(
            relation_type="supports",
            polarity="positive",
            strength=0.8,
            rationale="r",
        ),
        10,
    )
    pack = load_pack("personal_ai_tech")
    state = {
        "error": None,
        "pack": pack,
        "model": "test-model",
        "stored_capsule_ids": [cap_a.id, cap_b.id],
        "t2_calls_used": 0,
    }
    await _run_classify_relations(state, session_factory, mock_client)

    async with session_factory() as session:
        theses = await synthesize_theses_from_relations(
            session, domain="personal_ai_tech", min_strength=0.6
        )

    assert len(theses) == 1
    assert set(theses[0].supporting_capsule_ids) == {cap_a.id, cap_b.id}
