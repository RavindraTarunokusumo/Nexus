"""Tests for classify_relations prompt builder and RelationClassification schema.

Pure unit tests — no DB required.
Node tests for classify_relations are added in Task 8.
"""

from unittest.mock import MagicMock

import pytest

from app.domain_packs.loader import load_pack
from app.intelligence.prompts.classify_relations import (
    RelationClassification,
    build_relation_prompt,
)


def _make_capsule(text: str, family: str = "model_release_event") -> MagicMock:
    cap = MagicMock()
    cap.object_family = family
    cap.domain_object_type = "model_release"
    cap.text = text
    cap.facets = {"model": ["GPT-5"]}
    return cap


def _pack():
    return load_pack("personal_ai_tech")


def test_build_relation_prompt_includes_both_texts():
    pack = _pack()
    cap_a = _make_capsule("GPT-5 scored 90% on MMLU.")
    cap_b = _make_capsule("GPT-4 scored 86% on MMLU.")
    prompt = build_relation_prompt(cap_a, cap_b, pack)
    assert "GPT-5 scored 90% on MMLU." in prompt
    assert "GPT-4 scored 86% on MMLU." in prompt


def test_build_relation_prompt_includes_core_relations():
    pack = _pack()
    prompt = build_relation_prompt(_make_capsule("A"), _make_capsule("B"), pack)
    for rel in pack.relation_grammar.core_relations:
        assert rel in prompt


def test_build_relation_prompt_includes_domain_relations():
    pack = _pack()
    prompt = build_relation_prompt(_make_capsule("A"), _make_capsule("B"), pack)
    for rel in pack.relation_grammar.domain_relations:
        assert rel in prompt


def test_build_relation_prompt_includes_none_sentinel():
    pack = _pack()
    prompt = build_relation_prompt(_make_capsule("A"), _make_capsule("B"), pack)
    assert "none" in prompt


def test_build_relation_prompt_labels_a_and_b():
    pack = _pack()
    prompt = build_relation_prompt(_make_capsule("A text"), _make_capsule("B text"), pack)
    assert "Object A" in prompt
    assert "Object B" in prompt


def test_relation_classification_schema_validates():
    rc = RelationClassification.model_validate(
        {
            "relation_type": "supports",
            "polarity": "positive",
            "strength": 0.75,
            "rationale": "A directly supports B.",
        }
    )
    assert rc.relation_type == "supports"
    assert rc.polarity == "positive"
    assert rc.strength == pytest.approx(0.75)


def test_relation_classification_none_polarity():
    rc = RelationClassification.model_validate(
        {
            "relation_type": "none",
            "polarity": None,
            "strength": 0.0,
            "rationale": "No relation.",
        }
    )
    assert rc.polarity is None
