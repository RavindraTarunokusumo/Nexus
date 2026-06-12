"""Tests for classify_relations prompt builder and RelationClassification schema.

Pure unit tests — no DB required.
Node tests for classify_relations are added in Task 8.
"""

import uuid as _uuid
from unittest.mock import AsyncMock, MagicMock

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


# ---------------------------------------------------------------------------
# classify_relations node — short-circuit and "none" skipping
# ---------------------------------------------------------------------------


def _make_db_capsule(cap_id: _uuid.UUID, family: str, text: str) -> MagicMock:
    cap = MagicMock()
    cap.id = cap_id
    cap.object_family = family
    cap.domain_object_type = "model_release"
    cap.text = text
    cap.facets = {}
    cap.escalation_state = "none"
    cap.epistemic_state = {}
    cap.salience = 0.5
    cap.confidence = 0.7
    return cap


@pytest.mark.asyncio
async def test_classify_relations_skips_when_fewer_than_2_capsules():
    """_run_classify_relations returns {} without LLM call when < 2 capsule IDs in state."""

    from app.intelligence.extraction import _run_classify_relations

    mock_sf = MagicMock()
    mock_client = AsyncMock()
    pack = _pack()

    state: dict = {
        "document_id": _uuid.uuid4(),
        "run_id": None,
        "model": "test-model",
        "pack": pack,
        "source_type": "ai_news_article",
        "source_id": _uuid.uuid4(),
        "spans": [],
        "results": [],
        "projected_claims": [],
        "semantic_objects": [],
        "stored_claim_ids": [],
        "stored_capsule_ids": [_uuid.uuid4()],  # only 1 — triggers < 2 short-circuit
        "judge_results": [],
        "relation_ids": [],
        "t2_calls_used": 0,
        "total_tokens": 0,
        "error": None,
    }

    result = await _run_classify_relations(state, mock_sf, mock_client)

    assert result == {}
    mock_client.complete_json.assert_not_called()


@pytest.mark.asyncio
async def test_classify_relations_skips_none_relation_type():
    """_run_classify_relations: 'none' classification is not written to DB."""
    from app.intelligence.extraction import _run_classify_relations

    cap_id_a = _uuid.uuid4()
    cap_id_b = _uuid.uuid4()
    # Ensure deterministic A < B ordering
    if cap_id_a > cap_id_b:
        cap_id_a, cap_id_b = cap_id_b, cap_id_a

    cap_a = _make_db_capsule(cap_id_a, "model_release_event", "Text A")
    cap_b = _make_db_capsule(cap_id_b, "model_release_event", "Text B")

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    # execute is awaited; its result is a sync MagicMock so .scalars().all() is not a coroutine.
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [cap_a, cap_b]
    mock_session.execute = AsyncMock(return_value=execute_result)

    mock_sf = MagicMock()
    mock_sf.return_value = mock_session

    mock_client = AsyncMock()
    mock_client.complete_json.return_value = (
        RelationClassification(
            relation_type="none", polarity=None, strength=0.0, rationale="No relation."
        ),
        10,
    )

    pack = _pack()

    state: dict = {
        "document_id": _uuid.uuid4(),
        "run_id": None,
        "model": "test-model",
        "pack": pack,
        "source_type": "ai_news_article",
        "source_id": _uuid.uuid4(),
        "spans": [],
        "results": [],
        "projected_claims": [],
        "semantic_objects": [],
        "stored_claim_ids": [],
        "stored_capsule_ids": [cap_id_a, cap_id_b],
        "judge_results": [],
        "relation_ids": [],
        "t2_calls_used": 0,
        "total_tokens": 0,
        "error": None,
    }

    result = await _run_classify_relations(state, mock_sf, mock_client)

    assert result == {"relation_ids": []}
    mock_session.add.assert_not_called()
