import uuid

import pytest
from httpx import AsyncClient

from app.intelligence.chat import INSUFFICIENT_EVIDENCE_ANSWER
from app.intelligence.llm_client import LLMError


@pytest.mark.asyncio
async def test_chat_answer_requires_embedder(client: AsyncClient):
    response = await client.post("/chat/answer", json={"question": "What changed?"})
    assert response.status_code == 503
    assert "Embedder" in response.json()["detail"]


@pytest.mark.asyncio
async def test_chat_answer_rejects_whitespace_question(client_with_embedder: AsyncClient):
    response = await client_with_embedder.post("/chat/answer", json={"question": "   "})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_answer_returns_insufficient_evidence(client_with_embedder: AsyncClient):
    response = await client_with_embedder.post("/chat/answer", json={"question": "What changed?"})
    assert response.status_code == 200
    data = response.json()
    assert data["answer"].startswith("I do not have enough evidence")
    assert data["citations"] == []
    assert data["tokens_used"] == 0
    assert data["cost_estimate_usd"] == 0.0
    assert uuid.UUID(data["run_id"])


@pytest.mark.asyncio
async def test_chat_answer_success_shape(monkeypatch, client_with_embedder: AsyncClient):
    async def fake_run_chat_with_context(graph, question, model, *, top_k):
        return {
            "answer": INSUFFICIENT_EVIDENCE_ANSWER,
            "citations": [],
            "run_id": uuid.uuid4(),
            "tokens_used": 0,
            "error": None,
        }

    monkeypatch.setattr("app.api.routes_chat.run_chat_with_context", fake_run_chat_with_context)
    response = await client_with_embedder.post("/chat/answer", json={"question": "What changed?"})
    assert response.status_code == 200
    assert response.json()["answer"] == INSUFFICIENT_EVIDENCE_ANSWER


@pytest.mark.asyncio
async def test_chat_answer_llm_error_returns_service_unavailable(
    monkeypatch, client_with_embedder: AsyncClient
):
    async def fake_run_chat_with_context(graph, question, model, *, top_k):
        raise LLMError("bad model")

    monkeypatch.setattr("app.api.routes_chat.run_chat_with_context", fake_run_chat_with_context)
    response = await client_with_embedder.post("/chat/answer", json={"question": "What changed?"})
    assert response.status_code == 503
    assert "Chat answer failed" in response.json()["detail"]


@pytest.mark.asyncio
async def test_chat_answer_graph_error_state_returns_service_unavailable(
    monkeypatch, client_with_embedder: AsyncClient
):
    async def fake_run_chat_with_context(graph, question, model, *, top_k):
        return {
            "answer": "",
            "citations": [],
            "run_id": uuid.uuid4(),
            "tokens_used": 0,
            "error": "OpenRouter 503",
        }

    monkeypatch.setattr("app.api.routes_chat.run_chat_with_context", fake_run_chat_with_context)
    response = await client_with_embedder.post("/chat/answer", json={"question": "What changed?"})
    assert response.status_code == 503
    assert "OpenRouter 503" in response.json()["detail"]
