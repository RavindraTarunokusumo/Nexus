from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.intelligence.llm_client import LLMNetworkError


def _make_pack(intent_keys: list[str]) -> MagicMock:
    pack = MagicMock()
    pack.retrieval_policy.query_intents = {k: {} for k in intent_keys}
    return pack


@pytest.mark.asyncio
async def test_classify_intent_matched() -> None:
    from app.intelligence.chat import _run_classify_intent

    client = AsyncMock()
    client.complete_json.return_value = (MagicMock(intent="technical_deep_dive"), 50)
    pack = _make_pack(["technical_deep_dive", "landscape_scan"])
    state = {"question": "How does GPT-5 work?", "model": "deepseek/test", "pack": pack}

    result = await _run_classify_intent(state, client)

    assert result == {"query_intent": "technical_deep_dive"}


@pytest.mark.asyncio
async def test_classify_intent_unknown_falls_back_to_general() -> None:
    from app.intelligence.chat import _run_classify_intent

    client = AsyncMock()
    client.complete_json.return_value = (MagicMock(intent="made_up_intent"), 50)
    pack = _make_pack(["technical_deep_dive"])
    state = {"question": "...", "model": "deepseek/test", "pack": pack}

    result = await _run_classify_intent(state, client)

    assert result == {"query_intent": "general"}


@pytest.mark.asyncio
async def test_classify_intent_empty_pack_intents_skips_llm() -> None:
    from app.intelligence.chat import _run_classify_intent

    client = AsyncMock()
    pack = _make_pack([])
    state = {"question": "...", "model": "deepseek/test", "pack": pack}

    result = await _run_classify_intent(state, client)

    assert result == {"query_intent": "general"}
    client.complete_json.assert_not_called()


@pytest.mark.asyncio
async def test_classify_intent_llm_error_falls_back_to_general() -> None:
    from app.intelligence.chat import _run_classify_intent

    client = AsyncMock()
    client.complete_json.side_effect = LLMNetworkError("timeout")
    pack = _make_pack(["technical_deep_dive"])
    state = {"question": "...", "model": "deepseek/test", "pack": pack}

    result = await _run_classify_intent(state, client)

    assert result == {"query_intent": "general"}
