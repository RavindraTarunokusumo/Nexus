"""Tests for LLM settings wiring and LLMClient base_url configuration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.intelligence.llm_client import _BASE_URL, LLMClient


@pytest.fixture
def settings_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/nexus")
    monkeypatch.setenv("APP_SECRET", "unused-in-these-tests")


@pytest.fixture
def fake_session_factory():
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=session)


def test_llm_api_key_prefers_qwen_when_set(settings_env):
    s = Settings(
        qwen_cloud_api_key="qwen-key",
        openrouter_api_key="openrouter-key",
    )
    assert s.llm_api_key == "qwen-key"


def test_llm_api_key_falls_back_to_openrouter(settings_env):
    s = Settings(
        qwen_cloud_api_key="",
        openrouter_api_key="openrouter-key",
    )
    assert s.llm_api_key == "openrouter-key"


def test_llm_api_key_empty_when_neither_set(settings_env):
    s = Settings(
        qwen_cloud_api_key="",
        openrouter_api_key="",
    )
    assert s.llm_api_key == ""


def test_settings_ignores_unknown_env(settings_env, monkeypatch):
    # extra="ignore": an unrecognised env var (e.g. the reserved EMBEDDING_MODEL,
    # not yet wired — T1 embeddings are local) must not crash startup.
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-v4")
    Settings()  # does not raise


def test_llm_client_stores_custom_base_url(fake_session_factory):
    custom_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    client = LLMClient("test-key", fake_session_factory, base_url=custom_url)
    assert client._base_url == custom_url


@pytest.mark.asyncio
async def test_llm_client_uses_passed_base_url_in_httpx_client(fake_session_factory):
    from pydantic import BaseModel

    class _SimpleOutput(BaseModel):
        value: str

    custom_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    client = LLMClient("test-key", fake_session_factory, base_url=custom_url)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(
            return_value=AsyncMock(
                status_code=200,
                json=lambda: {
                    "choices": [{"message": {"content": '{"value": "ok"}'}}],
                    "usage": {"total_tokens": 1},
                },
            )
        )
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_http

        with patch(
            "app.intelligence.llm_client.record_agent_run",
            new=AsyncMock(),
        ):
            await client.complete_json(
                model="qwen3.6-flash",
                system="s",
                user="u",
                response_model=_SimpleOutput,
            )

    mock_client_cls.assert_called_once()
    assert mock_client_cls.call_args.kwargs["base_url"] == custom_url


def test_llm_client_default_base_url_is_openrouter(fake_session_factory):
    client = LLMClient("test-key", fake_session_factory)
    assert client._base_url == _BASE_URL
