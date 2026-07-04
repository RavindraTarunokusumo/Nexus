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
async def test_complete_json_happy_path(client, fake_session_factory):
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
            model="deepseek/deepseek-v4-flash",
            system="system",
            user="user",
            response_model=_SimpleOutput,
        )
    assert result.value == "hello"
    assert tokens == 50
    # AC4: every call must write an AgentRun row.
    session = fake_session_factory.return_value
    assert session.add.called
    agent_run = session.add.call_args[0][0]
    assert agent_run.run_type == "claim_extraction"
    assert agent_run.model == "deepseek/deepseek-v4-flash"
    assert agent_run.status == "success"


@pytest.mark.asyncio
async def test_complete_json_defaults_to_claim_extraction_run_type(client, fake_session_factory):
    openrouter_response = {
        "choices": [{"message": {"content": '{"value": "hello"}'}}],
        "usage": {"total_tokens": 50},
    }
    with patch("httpx.AsyncClient.post", new=AsyncMock()) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: openrouter_response
        mock_post.return_value = mock_resp

        await client.complete_json(model="m", system="s", user="u", response_model=_SimpleOutput)

    agent_run = fake_session_factory.return_value.add.call_args[0][0]
    assert agent_run.run_type == "claim_extraction"


@pytest.mark.asyncio
async def test_complete_json_accepts_chat_answer_run_type(client, fake_session_factory):
    openrouter_response = {
        "choices": [{"message": {"content": '{"value": "hello"}'}}],
        "usage": {"total_tokens": 50},
    }
    with patch("httpx.AsyncClient.post", new=AsyncMock()) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: openrouter_response
        mock_post.return_value = mock_resp

        await client.complete_json(
            model="m",
            system="s",
            user="u",
            response_model=_SimpleOutput,
            run_type="chat_answer",
        )

    agent_run = fake_session_factory.return_value.add.call_args[0][0]
    assert agent_run.run_type == "chat_answer"


@pytest.mark.asyncio
async def test_complete_json_retries_on_429_then_succeeds(client, fake_session_factory):
    openrouter_response = {
        "choices": [{"message": {"content": '{"value": "hello"}'}}],
        "usage": {"total_tokens": 50},
    }
    rate_limited = AsyncMock()
    rate_limited.status_code = 429
    rate_limited.text = "Rate limited"
    success = AsyncMock()
    success.status_code = 200
    success.json = lambda: openrouter_response

    with (
        patch(
            "httpx.AsyncClient.post", new=AsyncMock(side_effect=[rate_limited, success])
        ) as mock_post,
        patch("app.intelligence.llm_client._retry_backoff", new=AsyncMock()),
    ):
        result, tokens = await client.complete_json(
            model="deepseek/deepseek-v4-flash",
            system="s",
            user="u",
            response_model=_SimpleOutput,
        )

    assert result.value == "hello"
    assert tokens == 50
    assert mock_post.await_count == 2
    agent_run = fake_session_factory.return_value.add.call_args[0][0]
    assert agent_run.status == "success"


@pytest.mark.asyncio
async def test_complete_json_schema_error_does_not_retry(client, fake_session_factory):
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
                model="deepseek/deepseek-v4-flash",
                system="s",
                user="u",
                response_model=_SimpleOutput,
            )

    assert mock_post.await_count == 1
    agent_run = fake_session_factory.return_value.add.call_args[0][0]
    assert agent_run.status == "schema_error"


@pytest.mark.asyncio
async def test_complete_json_5xx_raises_network_error(client):
    with patch("httpx.AsyncClient.post", new=AsyncMock()) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 503
        mock_resp.text = "Service Unavailable"
        mock_post.return_value = mock_resp

        with pytest.raises(LLMNetworkError):
            await client.complete_json(
                model="deepseek/deepseek-v4-flash",
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
                model="deepseek/deepseek-v4-flash",
                system="s",
                user="u",
                response_model=_SimpleOutput,
            )


@pytest.mark.asyncio
async def test_complete_json_invalid_json_raises_schema_error(client, fake_session_factory):
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
                model="deepseek/deepseek-v4-flash",
                system="s",
                user="u",
                response_model=_SimpleOutput,
            )

    agent_run = fake_session_factory.return_value.add.call_args[0][0]
    assert agent_run.status == "schema_error"


@pytest.mark.asyncio
async def test_complete_json_schema_mismatch_raises_schema_error(client, fake_session_factory):
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
                model="deepseek/deepseek-v4-flash",
                system="s",
                user="u",
                response_model=_SimpleOutput,
            )

    agent_run = fake_session_factory.return_value.add.call_args[0][0]
    assert agent_run.status == "schema_error"


# ---------------------------------------------------------------------------
# Tracer-based tests — require real DB session_factory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_run_stores_full_payload_without_truncation(session_factory):
    """After the tracer switch, input/output must not be truncated to 300/500 chars."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.intelligence.llm_client import LLMClient, SemanticExtractionOutput

    long_prompt = "A" * 2000
    fake_response = {
        "choices": [{"message": {"content": '{"objects": []}'}}],
        "usage": {"total_tokens": 10, "prompt_tokens": 6, "completion_tokens": 4},
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_response

    client = LLMClient(api_key="test-key", session_factory=session_factory)
    with patch("httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__ = AsyncMock(return_value=mock_http.return_value)
        mock_http.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.return_value.post = AsyncMock(return_value=mock_resp)
        await client.complete_json(
            model="m",
            system=long_prompt,
            user=long_prompt,
            response_model=SemanticExtractionOutput,
        )

    async with session_factory() as session:
        from sqlalchemy import select

        from app.db.models import AgentRun

        row = (await session.execute(select(AgentRun))).scalar_one()

    assert row.input_json["system"] == long_prompt
    assert row.prompt_tokens == 6
    assert row.completion_tokens == 4


@pytest.mark.asyncio
async def test_agent_run_split_tokens_populated(session_factory):
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.intelligence.llm_client import LLMClient, SemanticExtractionOutput

    fake_response = {
        "choices": [{"message": {"content": '{"objects": []}'}}],
        "usage": {"total_tokens": 15, "prompt_tokens": 10, "completion_tokens": 5},
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_response

    client = LLMClient(api_key="test-key", session_factory=session_factory)
    with patch("httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__ = AsyncMock(return_value=mock_http.return_value)
        mock_http.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.return_value.post = AsyncMock(return_value=mock_resp)
        await client.complete_json(
            model="m",
            system="s",
            user="u",
            response_model=SemanticExtractionOutput,
        )

    async with session_factory() as session:
        from sqlalchemy import select

        from app.db.models import AgentRun

        row = (await session.execute(select(AgentRun))).scalar_one()

    assert row.prompt_tokens == 10
    assert row.completion_tokens == 5
