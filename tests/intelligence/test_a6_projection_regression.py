"""A8 regression smoke test — A6 projection pipeline contract.

Verifies that hand-authored SemanticObjects covering the 5 representative MVP
claim types (model_release, benchmark_result, funding_event, security_issue,
forecast) pass through the full validate_object → enforce_budgets → project
chain against the real personal_ai_tech pack and produce correct ProjectedClaims
with the forward-compat stash keys preserved.

Fast, no DB, no LLM, --noconftest-safe.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domain_packs.loader import Budgets, load_pack
from app.intelligence.llm_client import SemanticObject
from app.intelligence.projection import (
    ProjectedClaim,
    enforce_budgets,
    project,
    validate_object,
)

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

PACK = load_pack("personal_ai_tech")

_FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "a8_projection_input.json"


def _load_fixture() -> list[SemanticObject]:
    raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    return [SemanticObject.model_validate(item) for item in raw]


# ---------------------------------------------------------------------------
# 1. Schema validity — every fixture object round-trips through SemanticObject
# ---------------------------------------------------------------------------


def test_fixture_objects_validate_against_schema():
    """Re-parse each fixture item via SemanticObject.model_validate to catch schema drift."""
    raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    for i, item in enumerate(raw):
        # Must not raise
        obj = SemanticObject.model_validate(item)
        assert isinstance(obj, SemanticObject), f"Item {i} did not parse to SemanticObject"


# ---------------------------------------------------------------------------
# 2. All 5 objects validate and project successfully
# ---------------------------------------------------------------------------

_EXPECTED_CLAIM_TYPES = [
    "model_release",
    "benchmark_result",
    "funding_event",
    "security_issue",
    "forecast",
]


def test_all_five_objects_accepted_by_validator():
    objects = _load_fixture()
    assert len(objects) == 5, "Fixture must contain exactly 5 objects"
    for obj in objects:
        accepted, reason = validate_object(obj, PACK)
        assert (
            accepted is True
        ), f"Object with mvp_claim_type={obj.mvp_claim_type!r} rejected: {reason}"


def test_all_five_objects_project_to_correct_claim_types():
    objects = _load_fixture()
    projected_types = []
    for obj in objects:
        accepted, _ = validate_object(obj, PACK)
        assert accepted
        pc = project(obj)
        assert isinstance(pc, ProjectedClaim)
        projected_types.append(pc.claim_type)

    assert (
        projected_types == _EXPECTED_CLAIM_TYPES
    ), f"Projected claim types mismatch.\n  Expected: {_EXPECTED_CLAIM_TYPES}\n  Got:      {projected_types}"


# ---------------------------------------------------------------------------
# 3. claim_type matches the pack's mvp_claim_type table for each family
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fixture_index,domain_family,domain_object_type,expected_claim_type",
    [
        (0, "model_system", "model_release", "model_release"),
        (1, "evaluation_evidence", "benchmark_result", "benchmark_result"),
        (2, "economics_pricing", "funding_round", "funding_event"),
        (3, "safety_security", "prompt_injection_issue", "security_issue"),
        (4, "forecast_outlook", "capability_forecast", "forecast"),
    ],
)
def test_claim_type_matches_pack_mvp_table(
    fixture_index, domain_family, domain_object_type, expected_claim_type
):
    """Cross-check fixture claim type against the YAML pack table to catch pack drift."""
    pack_family = PACK.semantic_object_families[domain_family]
    pack_claim_type = pack_family.mvp_claim_type[domain_object_type]
    assert pack_claim_type == expected_claim_type, (
        f"Pack YAML mismatch for {domain_family}/{domain_object_type}: "
        f"expected {expected_claim_type!r}, pack says {pack_claim_type!r}"
    )

    objects = _load_fixture()
    obj = objects[fixture_index]
    pc = project(obj)
    assert pc.claim_type == expected_claim_type


# ---------------------------------------------------------------------------
# 4. Forward-compat stash keys present on every projected claim
# ---------------------------------------------------------------------------


def test_forward_compat_stash_keys_present():
    """Every projected claim must carry _v0_7, _function, _domain_family in entities_json."""
    objects = _load_fixture()
    for obj in objects:
        accepted, reason = validate_object(obj, PACK)
        assert accepted, f"Unexpected rejection: {reason}"
        pc = project(obj)

        assert (
            "_v0_7" in pc.entities_json
        ), f"Missing _v0_7 stash key for claim_type={pc.claim_type!r}"
        assert (
            "_function" in pc.entities_json
        ), f"Missing _function stash key for claim_type={pc.claim_type!r}"
        assert (
            "_domain_family" in pc.entities_json
        ), f"Missing _domain_family stash key for claim_type={pc.claim_type!r}"


def test_forward_compat_stash_values_correct():
    """Stash values must match source object fields exactly."""
    objects = _load_fixture()
    for obj in objects:
        pc = project(obj)
        assert pc.entities_json["_v0_7"] == obj.model_dump(
            mode="json"
        ), "_v0_7 must be the full SemanticObject serialised to a dict"
        assert pc.entities_json["_function"] == obj.function
        assert pc.entities_json["_domain_family"] == obj.domain_family


# ---------------------------------------------------------------------------
# 5. Budget enforcement caps output
# ---------------------------------------------------------------------------


def _make_funding_objects(n: int) -> list[SemanticObject]:
    """Build n funding_round objects with distinct saliences for budget testing."""
    return [
        SemanticObject(
            source_refs=["seg-budget-001"],
            core_type="event",
            domain_family="economics_pricing",
            domain_object_type="funding_round",
            function="Announces a funding round.",
            text=f"Company {i} raised $10M Series A.",
            facets={
                "orgs": [f"Company {i}"],
                "money": ["$10M"],
                "domain_terms": ["Series A"],
            },
            epistemic={
                "status": "asserted_by_source",
                "source_authority": "secondary",
                "confidence": 0.8,
                "evidence_quality": "medium",
            },
            salience=round(min(1.0, 0.5 + i * 0.01), 4),
            mvp_claim_type="funding_event",
        )
        for i in range(n)
    ]


def test_budget_caps_output():
    """50 funding objects through a pack patched to cap at 10 — expect 10 returned."""
    custom_pack = PACK.model_copy(
        update={
            "budgets": Budgets(
                max_semantic_objects_per_source=10,
                max_semantic_objects_per_segment=500,
            )
        }
    )
    objects = _make_funding_objects(50)
    result = enforce_budgets(objects, custom_pack, source_type=None)
    assert len(result) == 10, f"Expected 10 after budget cap, got {len(result)}"

    # Highest-salience objects must survive
    result_saliences = sorted([o.salience for o in result], reverse=True)
    all_saliences = sorted([o.salience for o in objects], reverse=True)
    assert result_saliences == all_saliences[:10], "Budget must keep the top-salience objects"
