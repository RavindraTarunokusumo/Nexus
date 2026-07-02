import uuid

import pytest

from app.db.models import DecisionArtefact
from app.intelligence.decision_artefacts import build_decision_artefact_row


def test_build_decision_artefact_row_basic_shape():
    artefact_id = uuid.uuid4()
    cap_id = uuid.uuid4()
    artefact = build_decision_artefact_row(
        artefact_id=artefact_id,
        artefact_type="memo",
        domain="personal_ai_tech",
        question="Is GPT-5 better than GPT-4?",
        answer="Yes, per benchmark X.",
        linked_thesis_ids=[],
        linked_capsule_ids=[cap_id],
        source_refs=[],
        created_by_tier="t2",
    )
    assert isinstance(artefact, DecisionArtefact)
    assert artefact.id == artefact_id
    assert artefact.artefact_type == "memo"
    assert artefact.linked_capsule_ids == [cap_id]
    assert artefact.created_by_tier == "t2"


def test_build_decision_artefact_row_rejects_invalid_tier():
    with pytest.raises(ValueError, match="created_by_tier"):
        build_decision_artefact_row(
            artefact_id=uuid.uuid4(),
            artefact_type="memo",
            domain="personal_ai_tech",
            question="q",
            answer="a",
            linked_thesis_ids=[],
            linked_capsule_ids=[],
            source_refs=[],
            created_by_tier="t1",
        )
