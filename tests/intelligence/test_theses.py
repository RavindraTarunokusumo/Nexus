import uuid

import pytest

from app.db.models import Thesis
from app.intelligence.theses import build_thesis_row


def test_build_thesis_row_basic_shape():
    thesis_id = uuid.uuid4()
    cap_a, cap_b = uuid.uuid4(), uuid.uuid4()
    thesis = build_thesis_row(
        thesis_id=thesis_id,
        domain="personal_ai_tech",
        thesis_type="model_release_event",
        statement="GPT-5 outperforms GPT-4 on MMLU.",
        supporting_capsule_ids=[cap_a, cap_b],
        contradicting_capsule_ids=[],
        confidence=0.75,
        created_by_tier="t2",
    )
    assert isinstance(thesis, Thesis)
    assert thesis.id == thesis_id
    assert thesis.domain == "personal_ai_tech"
    assert thesis.thesis_type == "model_release_event"
    assert thesis.supporting_capsule_ids == [cap_a, cap_b]
    assert thesis.contradicting_capsule_ids == []
    assert thesis.confidence == 0.75
    assert thesis.created_by_tier == "t2"
    assert thesis.title is None


def test_build_thesis_row_rejects_invalid_tier():
    with pytest.raises(ValueError, match="created_by_tier"):
        build_thesis_row(
            thesis_id=uuid.uuid4(),
            domain="personal_ai_tech",
            thesis_type="model_release_event",
            statement="x",
            supporting_capsule_ids=[uuid.uuid4()],
            contradicting_capsule_ids=[],
            confidence=0.5,
            created_by_tier="t0",
        )


def test_build_thesis_row_rejects_confidence_out_of_range():
    with pytest.raises(ValueError, match="confidence"):
        build_thesis_row(
            thesis_id=uuid.uuid4(),
            domain="personal_ai_tech",
            thesis_type="model_release_event",
            statement="x",
            supporting_capsule_ids=[uuid.uuid4()],
            contradicting_capsule_ids=[],
            confidence=1.5,
            created_by_tier="t2",
        )


def test_synthesize_theses_from_relations_clusters_connected_capsules(monkeypatch):
    """Uses a fake AsyncSession whose execute() returns canned relation+capsule rows."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from app.intelligence.theses import synthesize_theses_from_relations

    cap_a, cap_b, cap_c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    def _capsule(id_, family="model_release_event", salience=0.5, text="t"):
        c = MagicMock()
        c.id, c.object_family, c.salience, c.text = id_, family, salience, text
        return c

    caps = {
        cap_a: _capsule(cap_a, salience=0.9, text="anchor"),
        cap_b: _capsule(cap_b),
        cap_c: _capsule(cap_c),
    }

    def _relation(
        src, tgt, strength=0.8, polarity="positive", relation_type="supports", confidence=0.8
    ):
        r = MagicMock()
        r.source_capsule_id, r.target_capsule_id = src, tgt
        r.strength, r.polarity, r.relation_type, r.confidence = (
            strength,
            polarity,
            relation_type,
            confidence,
        )
        return r

    relations = [_relation(cap_a, cap_b)]  # cap_c stays isolated — below min_cluster_size

    session = AsyncMock()
    domain_ids_result = MagicMock()
    domain_ids_result.scalars.return_value.all.return_value = list(caps.keys())
    rel_result = MagicMock()
    rel_result.scalars.return_value.all.return_value = relations
    cap_result = MagicMock()
    cap_result.scalars.return_value.all.return_value = list(caps.values())
    session.execute = AsyncMock(side_effect=[domain_ids_result, rel_result, cap_result])
    session.add_all = MagicMock()
    session.commit = AsyncMock()

    theses = asyncio.run(
        synthesize_theses_from_relations(session, domain="personal_ai_tech", min_strength=0.6)
    )
    assert len(theses) == 1
    assert set(theses[0].supporting_capsule_ids) == {cap_a, cap_b}
    assert theses[0].statement == "anchor"  # highest-salience member
    assert theses[0].thesis_type == "model_release_event"
