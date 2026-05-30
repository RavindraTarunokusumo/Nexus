"""Unit tests for the T2 semantic-object judge prompt module (A7).

Run with:
    python -m pytest tests/intelligence/test_judge_semantic_object_prompt.py \
        -v --no-header --noconftest
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

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
    Telos,
)
from app.intelligence.llm_client import EpistemicState, SemanticObject
from app.intelligence.prompts.judge_semantic_object import (
    SYSTEM_PROMPT,
    JudgeVerdict,
    build_judge_prompt,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FAMILY = SemanticObjectFamily(
    purpose="Preserve durable facts about AI models.",
    object_types=["model_release", "capability_claim"],
    core_type_mapping={"model_release": "event", "capability_claim": "claim"},
    mvp_claim_type={"model_release": "model_release", "capability_claim": "research_finding"},
)


def _make_pack(
    *, status_rules: dict | None = None, escalation_policy: dict | None = None
) -> DomainPack:
    ep_kwargs: dict = {}
    if status_rules is not None:
        ep_kwargs["status_rules"] = status_rules
    if escalation_policy is not None:
        ep_kwargs["escalation_policy"] = escalation_policy

    return DomainPack(
        metadata=Metadata(
            pack_id="test_pack",
            domain="test_domain",
            version="1.0.0",
            supported_source_types=["test_article"],
        ),
        telos=Telos(primary_purposes=["Report AI changes."]),
        semantic_object_families={"model_system": _FAMILY},
        salience_policy=SaliencePolicy(),
        facet_policy=FacetPolicy(),
        relation_grammar=RelationGrammar(core_relations=["supports"]),
        epistemic_policy=EpistemicPolicy(**ep_kwargs),
        model_routing_policy=ModelRoutingPolicy(default_route={"model": "gpt-4o"}),
        budgets=Budgets(),
        retention_policy=RetentionPolicy(),
        retrieval_policy=RetrievalPolicy(),
        evaluation_contract=EvaluationContract(),
    )


def _make_object(**overrides) -> SemanticObject:
    base = dict(
        source_refs=["seg-001"],
        core_type="claim",
        domain_family="model_system",
        domain_object_type="model_release",
        function="Documents a new model release.",
        text="Mistral AI released Mistral Large 2 with 128k context.",
        facets={"orgs": ["Mistral AI"], "models": ["Mistral Large 2"]},
        epistemic=EpistemicState(
            status="reported",
            confidence=0.85,
            evidence_quality="medium",
        ),
        salience=0.9,
        mvp_claim_type="model_release",
    )
    base.update(overrides)
    return SemanticObject(**base)


# ---------------------------------------------------------------------------
# 1. SYSTEM_PROMPT sanity
# ---------------------------------------------------------------------------


def test_system_prompt_is_nonempty():
    assert isinstance(SYSTEM_PROMPT, str)
    assert len(SYSTEM_PROMPT) > 0


def test_system_prompt_mentions_evidence():
    assert "evidence" in SYSTEM_PROMPT.lower()


def test_system_prompt_mentions_json():
    assert "JSON" in SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# 2. JudgeVerdict schema
# ---------------------------------------------------------------------------


def test_judge_verdict_valid_payload():
    v = JudgeVerdict(
        evidence_sufficient=True,
        recommended_confidence=0.75,
        escalate=False,
        rationale="Evidence quality matches stated confidence.",
    )
    assert v.evidence_sufficient is True
    assert v.recommended_confidence == 0.75
    assert v.escalate is False


def test_judge_verdict_rejects_confidence_above_one():
    with pytest.raises(ValidationError):
        JudgeVerdict(
            evidence_sufficient=True,
            recommended_confidence=1.5,
            escalate=False,
            rationale="Out of range.",
        )


def test_judge_verdict_rejects_confidence_below_zero():
    with pytest.raises(ValidationError):
        JudgeVerdict(
            evidence_sufficient=False,
            recommended_confidence=-0.1,
            escalate=True,
            rationale="Out of range.",
        )


# ---------------------------------------------------------------------------
# 3. build_judge_prompt content checks
# ---------------------------------------------------------------------------


def test_prompt_includes_object_text():
    obj = _make_object()
    pack = _make_pack()
    prompt = build_judge_prompt(obj, pack)
    assert obj.text in prompt


def test_prompt_includes_object_function():
    obj = _make_object()
    pack = _make_pack()
    prompt = build_judge_prompt(obj, pack)
    assert obj.function in prompt


def test_prompt_includes_pack_id():
    obj = _make_object()
    pack = _make_pack()
    prompt = build_judge_prompt(obj, pack)
    assert pack.metadata.pack_id in prompt


def test_prompt_includes_family_status_rules_when_present():
    obj = _make_object(domain_family="model_system")
    pack = _make_pack(status_rules={"model_system": "treat unverified releases as speculative"})
    prompt = build_judge_prompt(obj, pack)
    assert "treat unverified releases as speculative" in prompt


def test_prompt_includes_family_escalation_policy_when_present():
    obj = _make_object(domain_family="model_system")
    pack = _make_pack(escalation_policy={"model_system": "escalate numeric contradictions"})
    prompt = build_judge_prompt(obj, pack)
    assert "escalate numeric contradictions" in prompt


def test_prompt_omits_epistemic_rules_section_when_absent():
    obj = _make_object(domain_family="model_system")
    pack = _make_pack()  # no rules for model_system
    prompt = build_judge_prompt(obj, pack)
    assert "Family-Specific Epistemic Rules" not in prompt


# ---------------------------------------------------------------------------
# 4. Determinism
# ---------------------------------------------------------------------------


def test_build_judge_prompt_is_deterministic():
    obj = _make_object()
    pack = _make_pack(
        status_rules={"model_system": "treat unverified releases as speculative"},
        escalation_policy={"model_system": "escalate numeric contradictions"},
    )
    p1 = build_judge_prompt(obj, pack)
    p2 = build_judge_prompt(obj, pack)
    assert p1 == p2
