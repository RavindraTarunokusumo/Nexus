"""Unit tests for the judge_capsules node helpers.

Tests use mock LLM client — no real DB required.
Run with --noconftest to skip the DB fixture chain.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.db.models import SemanticCapsule
from app.domain_packs.loader import load_pack
from app.intelligence.extraction import _capsule_to_obj_for_judge, _resolve_t2_model
from app.intelligence.llm_client import SemanticObject

# ---------------------------------------------------------------------------
# _resolve_t2_model
# ---------------------------------------------------------------------------


def test_resolve_t2_model_reads_top_level_models_key():
    pack = load_pack("personal_ai_tech")
    model = _resolve_t2_model(pack, fallback="fallback-model")
    assert model == "qwen3.6-flash"


def test_resolve_t2_model_uses_fallback_when_absent():
    pack = MagicMock()
    pack.model_extra = {}
    result = _resolve_t2_model(pack, fallback="fallback-model")
    assert result == "fallback-model"


def test_resolve_t2_model_force_overrides_pack():
    pack = load_pack("personal_ai_tech")
    with patch("app.intelligence.extraction.settings") as mock_settings:
        mock_settings.t2_model_force = "qwen-flash"
        result = _resolve_t2_model(pack, fallback="fallback-model")
    assert result == "qwen-flash"


def test_resolve_t2_model_empty_force_uses_pack():
    pack = load_pack("personal_ai_tech")
    with patch("app.intelligence.extraction.settings") as mock_settings:
        mock_settings.t2_model_force = ""
        result = _resolve_t2_model(pack, fallback="fallback-model")
    assert result == "qwen3.6-flash"


# ---------------------------------------------------------------------------
# _capsule_to_obj_for_judge
# ---------------------------------------------------------------------------


def _make_capsule(*, needs_escalation: bool = True) -> MagicMock:
    cap = MagicMock(spec=SemanticCapsule)
    cap.id = uuid.uuid4()
    cap.core_type = "claim"
    cap.object_family = "model_release_event"
    cap.domain_object_type = "model_release"
    cap.function = "announces"
    cap.text = "GPT-5 was released."
    cap.facets = {"model": ["GPT-5"]}
    cap.salience = 0.8
    cap.confidence = 0.9
    cap.escalation_state = "flagged" if needs_escalation else "none"
    cap.epistemic_state = {
        "status": "asserted_by_source",
        "source_authority": "primary",
        "confidence": 0.9,
        "evidence_quality": "high",
        "needs_escalation": needs_escalation,
    }
    return cap


def test_capsule_to_obj_for_judge_returns_semantic_object():
    cap = _make_capsule()
    obj = _capsule_to_obj_for_judge(cap)
    assert isinstance(obj, SemanticObject)
    assert obj.core_type == "claim"
    assert obj.domain_family == "model_release_event"
    assert obj.text == "GPT-5 was released."
    assert len(obj.source_refs) == 1


def test_capsule_to_obj_for_judge_escalation_true():
    cap = _make_capsule(needs_escalation=True)
    obj = _capsule_to_obj_for_judge(cap)
    assert obj.epistemic.needs_escalation is True


def test_capsule_to_obj_for_judge_escalation_false():
    cap = _make_capsule(needs_escalation=False)
    obj = _capsule_to_obj_for_judge(cap)
    assert obj.epistemic.needs_escalation is False


def test_capsule_to_obj_for_judge_tolerates_empty_epistemic():
    cap = _make_capsule()
    cap.epistemic_state = {}
    obj = _capsule_to_obj_for_judge(cap)
    assert obj.epistemic.status == "asserted_by_source"
    assert obj.epistemic.confidence == pytest.approx(0.9)
