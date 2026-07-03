"""Tests for the conversation_v1 domain pack."""

from __future__ import annotations

from app.domain_packs.loader import load_pack
from app.intelligence.prompts.extract_semantic_objects import build_user_prompt

_SEGMENT_TEXT = "User: My car's GPS broke after its first service."


def test_conversation_v1_loads():
    pack = load_pack("conversation_v1")
    assert pack.metadata.pack_id == "conversation_v1"
    assert pack.metadata.domain == "conversation_v1"
    assert len(pack.semantic_object_families) == 7


def test_people_actor_facet_guidance_in_extraction_prompt():
    pack = load_pack("conversation_v1")
    prompt = build_user_prompt(
        _SEGMENT_TEXT,
        {"segment_id": "seg-1"},
        pack,
        "chat_session",
    )
    assert "personal_state" in prompt
    assert "people facet must include 'user'" in prompt


def test_models_use_qwen_not_deepseek():
    pack = load_pack("conversation_v1")
    extra = getattr(pack, "model_extra", {}) or {}
    models = extra.get("models") or {}
    assert models["t2"] == "qwen3.6-flash"
    assert models["t3"] == "qwen3.7-max"
    assert "deepseek" not in str(models).lower()
    assert pack.model_routing_policy.models["T2"] == "qwen3.6-flash"
    assert pack.model_routing_policy.models["T3"] == "qwen3.7-max"


def test_core_relations_match_personal_ai_tech():
    conversation = load_pack("conversation_v1")
    personal_ai_tech = load_pack("personal_ai_tech")
    assert (
        conversation.relation_grammar.core_relations
        == personal_ai_tech.relation_grammar.core_relations
    )
