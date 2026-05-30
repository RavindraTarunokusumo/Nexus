"""Tests for the telos-aware semantic-object extraction prompt module (A4).

Run with:
    python -m pytest tests/intelligence/test_extract_semantic_objects_prompt.py \
        -v --no-header --noconftest
"""

from __future__ import annotations

import pytest

from app.domain_packs.loader import (
    Budgets,
    DomainPack,
    EpistemicPolicy,
    EvaluationContract,
    FacetPolicy,
    Metadata,
    ModelRoutingPolicy,
    RelationGrammar,
    RetentionPolicy,
    RetrievalPolicy,
    SaliencePolicy,
    SemanticObjectFamily,
    SourceTypeProfile,
    Telos,
)
from app.intelligence.prompts.extract_semantic_objects import (
    SYSTEM_PROMPT,
    build_correction_prompt,
    build_user_prompt,
)

# ---------------------------------------------------------------------------
# Minimal fixture pack
# ---------------------------------------------------------------------------

_FAMILY_MODEL = SemanticObjectFamily(
    purpose="Preserve durable facts about AI models.",
    object_types=["model_release", "capability_claim"],
    core_type_mapping={"model_release": "event", "capability_claim": "claim"},
    mvp_claim_type={"model_release": "model_release", "capability_claim": "research_finding"},
    required_fields=["provider", "model name"],
)

_FAMILY_EVAL = SemanticObjectFamily(
    purpose="Preserve evaluation evidence.",
    object_types=["benchmark_result"],
    core_type_mapping={"benchmark_result": "result"},
    mvp_claim_type={"benchmark_result": "benchmark_result"},
    required_fields=["metric", "score"],
)

_FAMILY_POLICY = SemanticObjectFamily(
    purpose="Preserve policy and governance updates.",
    object_types=["regulatory_obligation"],
    core_type_mapping={"regulatory_obligation": "constraint"},
    mvp_claim_type={"regulatory_obligation": "regulation"},
    required_fields=["jurisdiction"],
)


def _make_pack(*, source_type_families: list[str] | None = None) -> DomainPack:
    """Build a minimal DomainPack for tests."""
    profiles: dict = {}
    if source_type_families is not None:
        profiles["test_article"] = SourceTypeProfile(
            expected_semantic_families=source_type_families
        )

    return DomainPack(
        metadata=Metadata(
            pack_id="test_pack",
            domain="test_domain",
            version="1.0.0",
            supported_source_types=["test_article"],
        ),
        telos=Telos(
            primary_purposes=["Report AI changes.", "Explain technical capabilities."],
            anti_purposes=["Not all benchmarks are verified.", "Not all launches are final."],
        ),
        source_type_profiles=profiles,
        semantic_object_families={
            "model_system": _FAMILY_MODEL,
            "evaluation_evidence": _FAMILY_EVAL,
            "policy_governance": _FAMILY_POLICY,
        },
        salience_policy=SaliencePolicy(
            preserve_if=["Reports a concrete change.", "States a measurable result."],
            ignore_if=["Generic background with no new information."],
            downgrade_if=["Claim is abstract-only."],
            escalate_if=["Numeric values conflict within the source."],
        ),
        facet_policy=FacetPolicy(
            generic_facets=["people", "orgs"],
            domain_facets=["models", "benchmarks"],
        ),
        relation_grammar=RelationGrammar(core_relations=["supports", "contradicts"]),
        epistemic_policy=EpistemicPolicy(),
        model_routing_policy=ModelRoutingPolicy(default_route={"model": "gpt-4o"}),
        budgets=Budgets(max_semantic_objects_per_segment=4),
        retention_policy=RetentionPolicy(),
        retrieval_policy=RetrievalPolicy(),
        evaluation_contract=EvaluationContract(),
    )


_SEGMENT_TEXT = "GPT-4o scores 90% on MMLU, up from 85% on the prior version."
_METADATA_FULL = {
    "segment_id": "seg-001",
    "title": "AI Benchmark Update",
    "source_name": "TechCrunch",
    "published_at": "2024-06-01",
    "url": "https://example.com/article",
}


# ---------------------------------------------------------------------------
# 1. SYSTEM_PROMPT basic checks
# ---------------------------------------------------------------------------


def test_system_prompt_is_nonempty_string():
    assert isinstance(SYSTEM_PROMPT, str)
    assert len(SYSTEM_PROMPT) > 0


def test_system_prompt_mentions_semantic():
    assert "semantic" in SYSTEM_PROMPT.lower()


def test_system_prompt_mentions_json():
    assert "JSON" in SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# 2. build_user_prompt — content checks
# ---------------------------------------------------------------------------


def test_prompt_contains_primary_purposes():
    pack = _make_pack()
    prompt = build_user_prompt(_SEGMENT_TEXT, {"segment_id": "seg-1"}, pack, "other")
    for purpose in pack.telos.primary_purposes:
        assert purpose in prompt


def test_prompt_contains_anti_purposes():
    pack = _make_pack()
    prompt = build_user_prompt(_SEGMENT_TEXT, {"segment_id": "seg-1"}, pack, "other")
    for ap in pack.telos.anti_purposes:
        assert ap in prompt


def test_prompt_contains_segment_text():
    pack = _make_pack()
    prompt = build_user_prompt(_SEGMENT_TEXT, {"segment_id": "seg-1"}, pack, "other")
    assert _SEGMENT_TEXT in prompt


def test_prompt_contains_segment_id():
    pack = _make_pack()
    prompt = build_user_prompt(_SEGMENT_TEXT, {"segment_id": "seg-42"}, pack, "other")
    assert "seg-42" in prompt


def test_prompt_contains_budget_number():
    pack = _make_pack()
    prompt = build_user_prompt(_SEGMENT_TEXT, {"segment_id": "seg-1"}, pack, "other")
    n = str(pack.budgets.max_semantic_objects_per_segment)
    assert f"more than {n} objects" in prompt


def test_prompt_contains_applicable_family_names_when_profile_set():
    pack = _make_pack(source_type_families=["model_system", "evaluation_evidence"])
    prompt = build_user_prompt(_SEGMENT_TEXT, {"segment_id": "seg-1"}, pack, "test_article")
    assert "model_system" in prompt
    assert "evaluation_evidence" in prompt


def test_prompt_excludes_non_applicable_family():
    pack = _make_pack(source_type_families=["model_system", "evaluation_evidence"])
    prompt = build_user_prompt(_SEGMENT_TEXT, {"segment_id": "seg-1"}, pack, "test_article")
    assert "policy_governance" not in prompt


def test_prompt_contains_all_families_when_no_profile():
    # No profile for "unknown_type" — should fall back to all families.
    pack = _make_pack()  # no source_type_profiles at all
    prompt = build_user_prompt(_SEGMENT_TEXT, {"segment_id": "seg-1"}, pack, "unknown_type")
    assert "model_system" in prompt
    assert "evaluation_evidence" in prompt
    assert "policy_governance" in prompt


def test_prompt_contains_salience_preserve_if():
    pack = _make_pack()
    prompt = build_user_prompt(_SEGMENT_TEXT, {"segment_id": "seg-1"}, pack, "other")
    for rule in pack.salience_policy.preserve_if:
        assert rule in prompt


def test_prompt_contains_salience_ignore_if():
    pack = _make_pack()
    prompt = build_user_prompt(_SEGMENT_TEXT, {"segment_id": "seg-1"}, pack, "other")
    for rule in pack.salience_policy.ignore_if:
        assert rule in prompt


def test_prompt_contains_metadata_title_and_source():
    pack = _make_pack()
    prompt = build_user_prompt(_SEGMENT_TEXT, _METADATA_FULL, pack, "test_article")
    assert "AI Benchmark Update" in prompt
    assert "TechCrunch" in prompt


def test_prompt_omits_absent_optional_metadata():
    pack = _make_pack()
    prompt = build_user_prompt(_SEGMENT_TEXT, {"segment_id": "seg-1"}, pack, "other")
    # None of the optional fields were supplied; their labels should be absent.
    assert "Article title:" not in prompt
    assert "Source:" not in prompt
    assert "Published:" not in prompt


# ---------------------------------------------------------------------------
# 3. Missing segment_id raises ValueError
# ---------------------------------------------------------------------------


def test_missing_segment_id_raises_value_error():
    pack = _make_pack()
    with pytest.raises(ValueError, match="segment_id"):
        build_user_prompt(_SEGMENT_TEXT, {"title": "No ID here"}, pack, "other")


# ---------------------------------------------------------------------------
# 4. build_correction_prompt mirrors extract_claims pattern
# ---------------------------------------------------------------------------


def test_correction_prompt_includes_original_user():
    original = "Extract objects from: hello world"
    corrected = build_correction_prompt(original, '{"bad": true}', "missing field 'text'")
    assert original in corrected


def test_correction_prompt_includes_invalid_response():
    corrected = build_correction_prompt("original", '{"bad": true}', "some error")
    assert '{"bad": true}' in corrected


def test_correction_prompt_includes_error():
    corrected = build_correction_prompt("original", "bad json", "missing field 'text'")
    assert "missing field 'text'" in corrected


# ---------------------------------------------------------------------------
# 5. Determinism
# ---------------------------------------------------------------------------


def test_build_user_prompt_is_deterministic():
    pack = _make_pack(source_type_families=["model_system"])
    p1 = build_user_prompt(_SEGMENT_TEXT, _METADATA_FULL, pack, "test_article")
    p2 = build_user_prompt(_SEGMENT_TEXT, _METADATA_FULL, pack, "test_article")
    assert p1 == p2
