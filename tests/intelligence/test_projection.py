"""Tests for app/intelligence/projection.py — sync, no DB, --noconftest compatible."""

from __future__ import annotations

import hashlib
import uuid

import pytest

from app.domain_packs.loader import load_pack
from app.intelligence.capsules import build_capsule_idempotency_key
from app.intelligence.llm_client import EpistemicState, SemanticObject
from app.intelligence.projection import (
    ProjectedClaim,
    enforce_budgets,
    project,
    validate_object,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _epistemic(confidence: float = 0.85) -> EpistemicState:
    return EpistemicState(
        status="asserted_by_source",
        source_authority="primary",
        confidence=confidence,
        evidence_quality="high",
    )


def _make_obj(**kwargs) -> SemanticObject:
    defaults = dict(
        source_refs=["seg-001"],
        core_type="event",
        domain_family="model_system",
        domain_object_type="model_release",
        function="Announces a new model release.",
        text="OpenAI released GPT-5 on 2025-05-01.",
        facets={
            "orgs": ["OpenAI"],
            "models": ["GPT-5"],
            "dates": ["2025-05-01"],
            "domain_terms": ["large language model"],
            "unknown_salient_terms": ["frontier model"],
        },
        epistemic=_epistemic(),
        salience=0.9,
        mvp_claim_type="model_release",
    )
    defaults.update(kwargs)
    return SemanticObject(**defaults)


PACK = load_pack("personal_ai_tech")

# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------


def test_happy_path_validate_and_project():
    obj = _make_obj()
    accepted, reason = validate_object(obj, PACK)
    assert accepted is True
    assert reason is None

    pc = project(obj)
    assert isinstance(pc, ProjectedClaim)
    assert pc.claim_text == obj.text
    assert pc.claim_type == "model_release"
    assert "orgs" in pc.entities_json
    assert "models" in pc.entities_json
    assert "dates" in pc.entities_json
    assert "domain_terms" not in pc.entities_json
    assert "unknown_salient_terms" not in pc.entities_json
    assert "domain_terms" in pc.topics_json
    assert isinstance(pc.entities_json["_v0_7"], dict)
    assert pc.entities_json["_v0_7"] == obj.model_dump(mode="json")
    assert pc.entities_json["_function"] == obj.function
    assert pc.entities_json["_domain_family"] == "model_system"


# ---------------------------------------------------------------------------
# 2. Salience gate
# ---------------------------------------------------------------------------


def test_salience_gate_rejected():
    obj = _make_obj(salience=0.1)
    accepted, reason = validate_object(obj, PACK)
    assert accepted is False
    assert reason is not None
    assert "salience" in reason
    assert str(PACK.salience_policy.min_floor) in reason


# ---------------------------------------------------------------------------
# 3. Unknown family
# ---------------------------------------------------------------------------


def test_unknown_family_rejected():
    obj = _make_obj(domain_family="made_up_family")
    accepted, reason = validate_object(obj, PACK)
    assert accepted is False
    assert reason is not None
    assert "made_up_family" in reason


# ---------------------------------------------------------------------------
# 4. Unknown object_type
# ---------------------------------------------------------------------------


def test_unknown_object_type_rejected():
    obj = _make_obj(domain_object_type="fake_type")
    accepted, reason = validate_object(obj, PACK)
    assert accepted is False
    assert reason is not None
    assert "fake_type" in reason


# ---------------------------------------------------------------------------
# 5. mvp_claim_type mismatch
# ---------------------------------------------------------------------------


def test_mvp_claim_type_mismatch_rejected():
    obj = _make_obj(mvp_claim_type="regulation")
    accepted, reason = validate_object(obj, PACK)
    assert accepted is False
    assert reason is not None
    assert "model_release" in reason  # expected value
    assert "regulation" in reason  # got value


# ---------------------------------------------------------------------------
# 6. Facet split
# ---------------------------------------------------------------------------


def test_facet_split():
    obj = _make_obj(
        facets={
            "people": ["Sam Altman"],
            "orgs": ["OpenAI"],
            "models": ["GPT-5"],
            "hardware": ["H100"],
            "domain_terms": ["transformer", "autoregressive"],
            "unknown_salient_terms": ["hyperscaler"],
        }
    )
    pc = project(obj)
    # Entity-like facets in entities_json
    assert "people" in pc.entities_json
    assert "orgs" in pc.entities_json
    assert "models" in pc.entities_json
    assert "hardware" in pc.entities_json
    # Topic facets NOT in entities_json
    assert "domain_terms" not in pc.entities_json
    assert "unknown_salient_terms" not in pc.entities_json
    # Both topic facets merged into topics_json["domain_terms"]
    combined = pc.topics_json["domain_terms"]
    assert "transformer" in combined
    assert "autoregressive" in combined
    assert "hyperscaler" in combined


# ---------------------------------------------------------------------------
# 7. MVP-projection table samples (4 families)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "family,obj_type,expected_claim_type",
    [
        ("evaluation_evidence", "benchmark_result", "benchmark_result"),
        ("economics_pricing", "funding_round", "funding_event"),
        ("safety_security", "security_vulnerability", "security_issue"),
        ("forecast_outlook", "capability_forecast", "forecast"),
    ],
)
def test_mvp_projection_table(family, obj_type, expected_claim_type):
    # Derive the correct mvp_claim_type from the pack
    pack_family = PACK.semantic_object_families[family]
    mvp_ct = pack_family.mvp_claim_type[obj_type]
    assert mvp_ct == expected_claim_type, "YAML mismatch — test fixture is wrong"

    obj = _make_obj(
        domain_family=family,
        domain_object_type=obj_type,
        mvp_claim_type=mvp_ct,
    )
    accepted, reason = validate_object(obj, PACK)
    assert accepted is True, f"Unexpected rejection: {reason}"

    pc = project(obj)
    assert pc.claim_type == expected_claim_type


# ---------------------------------------------------------------------------
# 8. Budget enforcement
# ---------------------------------------------------------------------------


def _make_objects(n: int, base_salience: float = 0.5) -> list[SemanticObject]:
    """Create n objects with distinct saliences, all on seg-001."""
    objs = []
    for i in range(n):
        sal = min(1.0, base_salience + i * 0.01)
        objs.append(
            _make_obj(
                source_refs=["seg-001"],
                salience=round(sal, 4),
            )
        )
    return objs


def test_budget_per_source_cap():
    """50 objects, pack cap 80, but we patch down to 40 via a custom pack."""
    from app.domain_packs.loader import Budgets

    custom_pack = PACK.model_copy(
        update={
            "budgets": Budgets(
                max_semantic_objects_per_source=40, max_semantic_objects_per_segment=500
            )
        }
    )
    objs = _make_objects(50)
    result = enforce_budgets(objs, custom_pack, source_type=None)
    assert len(result) == 40
    # Top 40 by salience (highest saliences survive)
    saliences = [o.salience for o in result]
    all_saliences = sorted([o.salience for o in objs], reverse=True)
    assert saliences == sorted(saliences, reverse=True)
    assert saliences == all_saliences[:40]


def test_budget_per_source_type_override():
    """source_type='ai_news_article' has cap 12 in the real pack.

    Spread objects across unique segments so the per-segment cap (5 in the real
    pack) does not interfere — each segment contributes exactly 1 object.
    """
    objs = [
        _make_obj(source_refs=[f"seg-{i:03d}"], salience=round(min(1.0, 0.5 + i * 0.01), 4))
        for i in range(50)
    ]
    result = enforce_budgets(objs, PACK, source_type="ai_news_article")
    assert len(result) == 12


def test_budget_per_segment_cap():
    """10 objects all on the same segment, segment cap = 5 → 5 returned."""
    from app.domain_packs.loader import Budgets

    custom_pack = PACK.model_copy(
        update={
            "budgets": Budgets(
                max_semantic_objects_per_source=500,
                max_semantic_objects_per_segment=5,
            )
        }
    )
    objs = []
    for i in range(10):
        objs.append(_make_obj(source_refs=["same-seg"], salience=round(0.5 + i * 0.04, 4)))

    result = enforce_budgets(objs, custom_pack, source_type=None)
    assert len(result) == 5
    # Highest 5 saliences kept
    all_sal = sorted([o.salience for o in objs], reverse=True)
    result_sal = sorted([o.salience for o in result], reverse=True)
    assert result_sal == all_sal[:5]


# ---------------------------------------------------------------------------
# 9. build_capsule_idempotency_key
# ---------------------------------------------------------------------------


def test_build_capsule_idempotency_key_is_deterministic():
    """build_capsule_idempotency_key produces stable, correctly-shaped keys."""
    doc_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    source_refs = ["aaa", "bbb"]
    dot = "model_release"
    text = "GPT-5 was released."

    # Same inputs always produce the same key
    key1 = build_capsule_idempotency_key(
        document_id=doc_id, source_refs=source_refs, domain_object_type=dot, text=text
    )
    key2 = build_capsule_idempotency_key(
        document_id=doc_id, source_refs=source_refs, domain_object_type=dot, text=text
    )
    assert key1 == key2
    assert isinstance(key1, str)
    assert len(key1) > 0

    # Different text → different key
    key_diff_text = build_capsule_idempotency_key(
        document_id=doc_id, source_refs=source_refs, domain_object_type=dot, text="Different text."
    )
    assert key1 != key_diff_text

    # source_refs order must NOT matter (sorted internally)
    key_reversed = build_capsule_idempotency_key(
        document_id=doc_id, source_refs=["bbb", "aaa"], domain_object_type=dot, text=text
    )
    assert key1 == key_reversed

    # Different domain_object_type → different key
    key_diff_type = build_capsule_idempotency_key(
        document_id=doc_id,
        source_refs=source_refs,
        domain_object_type="benchmark_result",
        text=text,
    )
    assert key1 != key_diff_type

    # Output matches expected {doc_id}:{refs}:{type}:{hex} shape
    expected_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    expected = f"{doc_id}:aaa,bbb:{dot}:{expected_digest}"
    assert key1 == expected
