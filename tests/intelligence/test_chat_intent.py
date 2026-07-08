from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.intelligence.llm_client import LLMNetworkError, LLMSchemaError


def _make_pack(intent_keys: list[str]) -> MagicMock:
    pack = MagicMock()
    pack.retrieval_policy.query_intents = {k: {} for k in intent_keys}
    return pack


def _intent_result(
    intent: str,
    shape: str = "general",
    sub_queries: list[str] | None = None,
) -> MagicMock:
    result = MagicMock()
    result.intent = intent
    result.shape = shape
    result.sub_queries = sub_queries if sub_queries is not None else []
    return result


@pytest.mark.asyncio
async def test_classify_intent_matched() -> None:
    from app.intelligence.chat import _run_classify_intent

    client = AsyncMock()
    client.complete_json.return_value = (_intent_result("technical_deep_dive", "factoid"), 50)
    pack = _make_pack(["technical_deep_dive", "landscape_scan"])
    state = {"question": "How does GPT-5 work?", "model": "deepseek/test", "pack": pack}

    result = await _run_classify_intent(state, client)

    assert result == {
        "query_intent": "technical_deep_dive",
        "question_shape": "factoid",
        "sub_queries": [],
    }


@pytest.mark.asyncio
async def test_classify_intent_unknown_falls_back_to_general() -> None:
    from app.intelligence.chat import _run_classify_intent

    client = AsyncMock()
    client.complete_json.return_value = (_intent_result("made_up_intent", "multi_doc"), 50)
    pack = _make_pack(["technical_deep_dive"])
    state = {"question": "...", "model": "deepseek/test", "pack": pack}

    result = await _run_classify_intent(state, client)

    assert result == {"query_intent": "general", "question_shape": "multi_doc", "sub_queries": []}


@pytest.mark.asyncio
async def test_classify_intent_empty_pack_intents_still_classifies_shape() -> None:
    from app.intelligence.chat import _run_classify_intent

    client = AsyncMock()
    client.complete_json.return_value = (_intent_result("general", "factoid"), 50)
    pack = _make_pack([])
    state = {"question": "When did X GA?", "model": "deepseek/test", "pack": pack}

    result = await _run_classify_intent(state, client)

    assert result == {"query_intent": "general", "question_shape": "factoid", "sub_queries": []}
    client.complete_json.assert_called_once()


@pytest.mark.asyncio
async def test_classify_intent_llm_error_falls_back_to_general() -> None:
    from app.intelligence.chat import _run_classify_intent

    client = AsyncMock()
    client.complete_json.side_effect = LLMNetworkError("timeout")
    pack = _make_pack(["technical_deep_dive"])
    state = {"question": "...", "model": "deepseek/test", "pack": pack}

    result = await _run_classify_intent(state, client)

    assert result == {"query_intent": "general", "question_shape": "general", "sub_queries": []}


@pytest.mark.asyncio
async def test_classify_intent_schema_error_falls_back_to_general() -> None:
    from app.intelligence.chat import _run_classify_intent

    client = AsyncMock()
    client.complete_json.side_effect = LLMSchemaError("bad json")
    pack = _make_pack(["technical_deep_dive"])
    state = {"question": "...", "model": "deepseek/test", "pack": pack}

    result = await _run_classify_intent(state, client)

    assert result == {"query_intent": "general", "question_shape": "general", "sub_queries": []}


@pytest.mark.asyncio
async def test_classify_intent_sanitizes_sub_queries() -> None:
    from app.intelligence.chat import _run_classify_intent

    client = AsyncMock()
    client.complete_json.return_value = (
        _intent_result(
            "general",
            "temporal",
            ["  event A  ", "", "event B", "event C", "event D"],
        ),
        50,
    )
    pack = _make_pack(["general"])
    state = {"question": "Which happened first?", "model": "deepseek/test", "pack": pack}

    result = await _run_classify_intent(state, client)

    assert result["sub_queries"] == ["event A", "event B", "event C"]
