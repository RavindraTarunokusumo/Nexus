"""Unit tests for LLMClient — httpx mocked, no real OpenRouter calls."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from app.intelligence.llm_client import (
    LLMClient,
    LLMNetworkError,
    LLMSchemaError,
)


class _SimpleOutput(BaseModel):
    value: str


@pytest.fixture
def fake_session_factory():
    """Mimic SQLAlchemy async_sessionmaker: a sync callable that returns an
    AsyncSession (which is itself an async context manager)."""
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.add = MagicMock()
    session.commit = AsyncMock()

    factory = MagicMock(return_value=session)
    return factory


@pytest.fixture
def client(fake_session_factory):
    return LLMClient(api_key="test-key", session_factory=fake_session_factory)


@pytest.mark.asyncio
async def test_complete_json_happy_path(client):
    openrouter_response = {
        "choices": [{"message": {"content": '{"value": "hello"}'}}],
        "usage": {"total_tokens": 50},
    }
    with patch("httpx.AsyncClient.post", new=AsyncMock()) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: openrouter_response
        mock_post.return_value = mock_resp

        result, tokens = await client.complete_json(
            model="openai/gpt-4o-mini",
            system="system",
            user="user",
            response_model=_SimpleOutput,
        )
    assert result.value == "hello"
    assert tokens == 50


@pytest.mark.asyncio
async def test_complete_json_5xx_raises_network_error(client):
    with patch("httpx.AsyncClient.post", new=AsyncMock()) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 503
        mock_resp.text = "Service Unavailable"
        mock_post.return_value = mock_resp

        with pytest.raises(LLMNetworkError):
            await client.complete_json(
                model="openai/gpt-4o-mini",
                system="s",
                user="u",
                response_model=_SimpleOutput,
            )


@pytest.mark.asyncio
async def test_complete_json_4xx_raises_llm_error(client):
    from app.intelligence.llm_client import LLMError

    with patch("httpx.AsyncClient.post", new=AsyncMock()) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request"
        mock_post.return_value = mock_resp

        with pytest.raises(LLMError):
            await client.complete_json(
                model="openai/gpt-4o-mini",
                system="s",
                user="u",
                response_model=_SimpleOutput,
            )


@pytest.mark.asyncio
async def test_complete_json_invalid_json_raises_schema_error(client):
    openrouter_response = {
        "choices": [{"message": {"content": "not-json"}}],
        "usage": {"total_tokens": 10},
    }
    with patch("httpx.AsyncClient.post", new=AsyncMock()) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: openrouter_response
        mock_post.return_value = mock_resp

        with pytest.raises(LLMSchemaError):
            await client.complete_json(
                model="openai/gpt-4o-mini",
                system="s",
                user="u",
                response_model=_SimpleOutput,
            )


@pytest.mark.asyncio
async def test_complete_json_schema_mismatch_raises_schema_error(client):
    openrouter_response = {
        "choices": [{"message": {"content": '{"wrong_field": 123}'}}],
        "usage": {"total_tokens": 10},
    }
    with patch("httpx.AsyncClient.post", new=AsyncMock()) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: openrouter_response
        mock_post.return_value = mock_resp

        with pytest.raises(LLMSchemaError):
            await client.complete_json(
                model="openai/gpt-4o-mini",
                system="s",
                user="u",
                response_model=_SimpleOutput,
            )
