"""Unit tests for app.intelligence.capsules.build_capsule_row."""

import uuid

import pytest

from app.db.models import CapsuleSegment, SemanticCapsule
from app.intelligence.capsules import build_capsule_idempotency_key, build_capsule_row
from app.intelligence.llm_client import SemanticObject

_FAKE_EMBEDDING = [0.0] * 384


def _make_obj(*, needs_escalation: bool = False, n_refs: int = 2) -> SemanticObject:
    span_ids = [str(uuid.uuid4()) for _ in range(n_refs)]
    return SemanticObject.model_validate(
        {
            "core_type": "claim",
            "domain_family": "model_release_event",
            "domain_object_type": "model_release",
            "function": "announces",
            "text": "GPT-5 was released today.",
            "facets": {"model": ["GPT-5"], "vendor": ["OpenAI"]},
            "salience": 0.8,
            "source_refs": span_ids,
            "epistemic": {
                "status": "asserted_by_source",
                "source_authority": "primary",
                "confidence": 0.9,
                "evidence_quality": "high",
                "needs_escalation": needs_escalation,
            },
            "mvp_claim_type": "model_release",
        }
    )


def test_build_capsule_row_basic_shape():
    obj = _make_obj(n_refs=2)
    capsule_id = uuid.uuid4()
    document_id = uuid.uuid4()
    source_id = uuid.uuid4()
    claim_id = uuid.uuid4()

    capsule, segments = build_capsule_row(
        capsule_id=capsule_id,
        source_id=source_id,
        document_id=document_id,
        claim_id=claim_id,
        obj=obj,
        domain="personal_ai_tech",
        source_telos="Stay informed on AI",
        embedding=_FAKE_EMBEDDING,
        created_by_tier="t2",
        created_by_model="deepseek/deepseek-v4-flash",
    )

    assert isinstance(capsule, SemanticCapsule)
    assert capsule.id == capsule_id
    assert capsule.document_id == document_id
    assert capsule.claim_id == claim_id
    assert capsule.core_type == "claim"
    assert capsule.confidence == pytest.approx(0.9)
    assert len(segments) == 2
    assert all(isinstance(s, CapsuleSegment) for s in segments)


def test_build_capsule_row_idempotency_key():
    obj = _make_obj(n_refs=1)
    document_id = uuid.uuid4()

    capsule, _ = build_capsule_row(
        capsule_id=uuid.uuid4(),
        source_id=None,
        document_id=document_id,
        claim_id=uuid.uuid4(),
        obj=obj,
        domain="personal_ai_tech",
        source_telos=None,
        embedding=_FAKE_EMBEDDING,
        created_by_tier="t2",
        created_by_model=None,
    )

    expected_key = build_capsule_idempotency_key(
        document_id=document_id,
        source_refs=obj.source_refs,
        domain_object_type=obj.domain_object_type,
        text=obj.text,
    )
    assert capsule.idempotency_key == expected_key


def test_build_capsule_row_escalation_state_flagged():
    obj = _make_obj(needs_escalation=True)
    capsule, _ = build_capsule_row(
        capsule_id=uuid.uuid4(),
        source_id=None,
        document_id=uuid.uuid4(),
        claim_id=uuid.uuid4(),
        obj=obj,
        domain="personal_ai_tech",
        source_telos=None,
        embedding=_FAKE_EMBEDDING,
        created_by_tier="t2",
        created_by_model=None,
    )
    assert capsule.escalation_state == "flagged"


def test_build_capsule_row_escalation_state_none():
    obj = _make_obj(needs_escalation=False)
    capsule, _ = build_capsule_row(
        capsule_id=uuid.uuid4(),
        source_id=None,
        document_id=uuid.uuid4(),
        claim_id=uuid.uuid4(),
        obj=obj,
        domain="personal_ai_tech",
        source_telos=None,
        embedding=_FAKE_EMBEDDING,
        created_by_tier="t2",
        created_by_model=None,
    )
    assert capsule.escalation_state == "none"


def test_build_capsule_row_segment_roles_default():
    obj = _make_obj(n_refs=2)
    _, segments = build_capsule_row(
        capsule_id=uuid.uuid4(),
        source_id=None,
        document_id=uuid.uuid4(),
        claim_id=uuid.uuid4(),
        obj=obj,
        domain="personal_ai_tech",
        source_telos=None,
        embedding=_FAKE_EMBEDDING,
        created_by_tier="t2",
        created_by_model=None,
    )
    assert all(s.role == "support" for s in segments)


def test_build_capsule_row_segment_roles_custom():
    obj = _make_obj(n_refs=2)
    span_uuid = uuid.UUID(obj.source_refs[0])
    custom_roles = {span_uuid: "grounds"}

    _, segments = build_capsule_row(
        capsule_id=uuid.uuid4(),
        source_id=None,
        document_id=uuid.uuid4(),
        claim_id=uuid.uuid4(),
        obj=obj,
        domain="personal_ai_tech",
        source_telos=None,
        embedding=_FAKE_EMBEDDING,
        created_by_tier="t2",
        created_by_model=None,
        evidence_roles=custom_roles,
    )
    roles = {s.segment_id: s.role for s in segments}
    assert roles[span_uuid] == "grounds"


def test_build_capsule_row_created_at_passthrough():
    from datetime import datetime, timezone

    obj = _make_obj()
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)

    capsule, _ = build_capsule_row(
        capsule_id=uuid.uuid4(),
        source_id=None,
        document_id=uuid.uuid4(),
        claim_id=uuid.uuid4(),
        obj=obj,
        domain="personal_ai_tech",
        source_telos=None,
        embedding=_FAKE_EMBEDDING,
        created_by_tier="backfill",
        created_by_model=None,
        created_at=ts,
    )
    assert capsule.created_at == ts
