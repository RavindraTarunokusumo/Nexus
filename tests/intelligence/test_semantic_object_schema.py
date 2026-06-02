"""Unit tests for v0.7 semantic-object extraction schema (A3).

Run with --noconftest to avoid the broken langgraph.checkpoint.postgres chain:
  python -m pytest tests/intelligence/test_semantic_object_schema.py -v --noconftest
"""

import pytest
from pydantic import ValidationError

from app.intelligence.llm_client import (
    EpistemicState,
    ExtractedClaim,
    ExtractionOutput,
    SemanticExtractionOutput,
    SemanticObject,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_EPISTEMIC = {
    "status": "asserted_by_source",
    "confidence": 0.9,
}

_VALID_OBJECT = {
    "source_refs": ["seg-1"],
    "core_type": "claim",
    "domain_family": "model_system",
    "domain_object_type": "model_release",
    "function": "Documents a new model release",
    "text": "Mistral AI released Mistral Large 2.",
    "epistemic": _VALID_EPISTEMIC,
    "salience": 0.8,
    "mvp_claim_type": "model_release",
}


# ---------------------------------------------------------------------------
# 1. Valid minimal SemanticObject — defaults apply
# ---------------------------------------------------------------------------


def test_valid_minimal_semantic_object() -> None:
    obj = SemanticObject(**_VALID_OBJECT)
    assert obj.facets == {}
    assert obj.original_text is None
    assert obj.epistemic.needs_escalation is False
    assert obj.epistemic.source_authority == "unknown"
    assert obj.epistemic.evidence_quality == "unknown"
    assert obj.epistemic.uncertainty is None


# ---------------------------------------------------------------------------
# 2. source_refs empty list is rejected
# ---------------------------------------------------------------------------


def test_source_refs_empty_rejected() -> None:
    payload = {**_VALID_OBJECT, "source_refs": []}
    with pytest.raises(ValidationError) as exc_info:
        SemanticObject(**payload)
    assert "source_refs" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 3. core_type outside the 15-entry vocabulary is rejected
# ---------------------------------------------------------------------------


def test_invalid_core_type_rejected() -> None:
    payload = {**_VALID_OBJECT, "core_type": "banana"}
    with pytest.raises(ValidationError):
        SemanticObject(**payload)


# ---------------------------------------------------------------------------
# 4. mvp_claim_type outside the 11 ClaimType literals is rejected
# ---------------------------------------------------------------------------


def test_invalid_mvp_claim_type_rejected() -> None:
    payload = {**_VALID_OBJECT, "mvp_claim_type": "banana"}
    with pytest.raises(ValidationError):
        SemanticObject(**payload)


# ---------------------------------------------------------------------------
# 5. confidence and salience out of [0, 1] are rejected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("confidence", [-0.1, 1.5])
def test_confidence_out_of_range(confidence: float) -> None:
    payload = {**_VALID_EPISTEMIC, "confidence": confidence}
    with pytest.raises(ValidationError):
        EpistemicState(**payload)


@pytest.mark.parametrize("salience", [-0.1, 1.5])
def test_salience_out_of_range(salience: float) -> None:
    payload = {**_VALID_OBJECT, "salience": salience}
    with pytest.raises(ValidationError):
        SemanticObject(**payload)


# ---------------------------------------------------------------------------
# 6. EpistemicState defaults apply when only status + confidence provided
# ---------------------------------------------------------------------------


def test_epistemic_state_defaults() -> None:
    ep = EpistemicState(status="asserted_by_source", confidence=0.75)
    assert ep.source_authority == "unknown"
    assert ep.evidence_quality == "unknown"
    assert ep.uncertainty is None
    assert ep.needs_escalation is False


# ---------------------------------------------------------------------------
# 7. SemanticExtractionOutput JSON round-trip
# ---------------------------------------------------------------------------


def test_semantic_extraction_output_round_trip() -> None:
    obj1 = SemanticObject(**_VALID_OBJECT)
    obj2 = SemanticObject(
        **{
            **_VALID_OBJECT,
            "source_refs": ["seg-2", "seg-3"],
            "core_type": "event",
            "text": "GPT-5 was announced.",
            "salience": 0.5,
            "mvp_claim_type": "product_launch",
        }
    )
    output = SemanticExtractionOutput(objects=[obj1, obj2])
    json_str = output.model_dump_json()
    restored = SemanticExtractionOutput.model_validate_json(json_str)
    assert len(restored.objects) == 2
    assert restored.objects[0].text == obj1.text
    assert restored.objects[1].core_type == "event"


# ---------------------------------------------------------------------------
# 8. Legacy ExtractedClaim / ExtractionOutput still parse (back-compat smoke)
# ---------------------------------------------------------------------------


def test_legacy_extraction_output_still_parses() -> None:
    payload = {
        "claims": [
            {
                "claim_text": "OpenAI released GPT-4.",
                "claim_type": "model_release",
                "entities": ["OpenAI", "GPT-4"],
                "topics": ["AI", "language models"],
                "confidence": 0.95,
                "rationale": "Direct statement in article.",
            }
        ]
    }
    output = ExtractionOutput(**payload)
    assert len(output.claims) == 1
    claim = output.claims[0]
    assert isinstance(claim, ExtractedClaim)
    assert claim.claim_type == "model_release"
    assert claim.confidence == 0.95
