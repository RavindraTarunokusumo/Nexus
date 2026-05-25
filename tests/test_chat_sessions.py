"""Tests for chat session memory API: session CRUD and message flow."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session_payload(title: str | None = None) -> dict:
    payload: dict = {}
    if title is not None:
        payload["title"] = title
    return payload


# ---------------------------------------------------------------------------
# Session creation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_session_returns_201(client_with_embedder: AsyncClient):
    resp = await client_with_embedder.post("/chat/sessions", json={})
    assert resp.status_code == 201
    data = resp.json()
    assert uuid.UUID(data["id"])
    assert data["status"] == "active"
    assert data["message_count"] == 0
    assert data["last_message_preview"] is None


@pytest.mark.asyncio
async def test_create_session_with_title(client_with_embedder: AsyncClient):
    resp = await client_with_embedder.post("/chat/sessions", json={"title": "My session"})
    assert resp.status_code == 201
    assert resp.json()["title"] == "My session"


# ---------------------------------------------------------------------------
# Session listing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_sessions_empty(client_with_embedder: AsyncClient):
    resp = await client_with_embedder.get("/chat/sessions")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_sessions_returns_active_by_default(client_with_embedder: AsyncClient):
    await client_with_embedder.post("/chat/sessions", json={"title": "A"})
    await client_with_embedder.post("/chat/sessions", json={"title": "B"})

    resp = await client_with_embedder.get("/chat/sessions")
    assert resp.status_code == 200
    titles = [s["title"] for s in resp.json()]
    assert "A" in titles
    assert "B" in titles


@pytest.mark.asyncio
async def test_list_sessions_archived_filter(client_with_embedder: AsyncClient):
    r = await client_with_embedder.post("/chat/sessions", json={"title": "To archive"})
    session_id = r.json()["id"]
    await client_with_embedder.patch(f"/chat/sessions/{session_id}", json={"status": "archived"})

    active = await client_with_embedder.get("/chat/sessions?status=active")
    archived = await client_with_embedder.get("/chat/sessions?status=archived")

    assert not any(s["id"] == session_id for s in active.json())
    assert any(s["id"] == session_id for s in archived.json())


# ---------------------------------------------------------------------------
# Session detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_session_not_found(client_with_embedder: AsyncClient):
    resp = await client_with_embedder.get(f"/chat/sessions/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_session_returns_messages(client_with_embedder: AsyncClient):
    r = await client_with_embedder.post("/chat/sessions", json={})
    session_id = r.json()["id"]

    resp = await client_with_embedder.get(f"/chat/sessions/{session_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == session_id
    assert data["messages"] == []


# ---------------------------------------------------------------------------
# Session update (rename / archive)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_session_rename(client_with_embedder: AsyncClient):
    r = await client_with_embedder.post("/chat/sessions", json={})
    session_id = r.json()["id"]

    resp = await client_with_embedder.patch(
        f"/chat/sessions/{session_id}", json={"title": "New name"}
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "New name"


@pytest.mark.asyncio
async def test_patch_session_archive(client_with_embedder: AsyncClient):
    r = await client_with_embedder.post("/chat/sessions", json={})
    session_id = r.json()["id"]

    resp = await client_with_embedder.patch(
        f"/chat/sessions/{session_id}", json={"status": "archived"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"
    assert resp.json()["archived_at"] is not None


@pytest.mark.asyncio
async def test_patch_session_not_found(client_with_embedder: AsyncClient):
    resp = await client_with_embedder.patch(f"/chat/sessions/{uuid.uuid4()}", json={"title": "x"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_message_archived_session_returns_409(client_with_embedder: AsyncClient):
    r = await client_with_embedder.post("/chat/sessions", json={})
    session_id = r.json()["id"]
    await client_with_embedder.patch(f"/chat/sessions/{session_id}", json={"status": "archived"})

    resp = await client_with_embedder.post(
        f"/chat/sessions/{session_id}/messages",
        json={"content": "Hello?"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_send_message_session_not_found(client_with_embedder: AsyncClient):
    resp = await client_with_embedder.post(
        f"/chat/sessions/{uuid.uuid4()}/messages",
        json={"content": "Hello?"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_send_message_persists_user_and_assistant(
    monkeypatch, client_with_embedder: AsyncClient
):
    fake_result = {
        "answer": "Grounded answer.",
        "citations": [],
        "run_id": uuid.uuid4(),
        "tokens_used": 10,
        "prompt_tokens": 5,
        "completion_tokens": 5,
        "retrieved_context_count": 0,
        "error": None,
    }

    async def fake_run_session_turn(**kwargs):
        return fake_result

    monkeypatch.setattr(
        "app.api.routes_chat.run_session_turn",
        fake_run_session_turn,
    )

    r = await client_with_embedder.post("/chat/sessions", json={})
    session_id = r.json()["id"]

    resp = await client_with_embedder.post(
        f"/chat/sessions/{session_id}/messages",
        json={"content": "What changed?"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["user_message"]["role"] == "user"
    assert data["user_message"]["content"] == "What changed?"
    assert data["assistant_message"]["role"] == "assistant"
    assert data["assistant_message"]["content"] == "Grounded answer."
    assert uuid.UUID(data["assistant_message"]["run_id"])


@pytest.mark.asyncio
async def test_send_first_message_derives_session_title(
    monkeypatch, client_with_embedder: AsyncClient
):
    fake_result = {
        "answer": "Answer.",
        "citations": [],
        "run_id": uuid.uuid4(),
        "tokens_used": 5,
        "prompt_tokens": 3,
        "completion_tokens": 2,
        "retrieved_context_count": 0,
        "error": None,
    }

    async def fake_run_session_turn(**kwargs):
        return fake_result

    monkeypatch.setattr("app.api.routes_chat.run_session_turn", fake_run_session_turn)

    r = await client_with_embedder.post("/chat/sessions", json={})
    session_id = r.json()["id"]

    await client_with_embedder.post(
        f"/chat/sessions/{session_id}/messages",
        json={"content": "What did the latest sources say?"},
    )

    detail = await client_with_embedder.get(f"/chat/sessions/{session_id}")
    assert detail.json()["title"] == "What did the latest sources say?"


@pytest.mark.asyncio
async def test_send_message_memory_failure_returns_503(
    monkeypatch, client_with_embedder: AsyncClient
):
    async def fake_run_session_turn(**kwargs):
        raise RuntimeError("checkpointer unavailable")

    monkeypatch.setattr("app.api.routes_chat.run_session_turn", fake_run_session_turn)

    r = await client_with_embedder.post("/chat/sessions", json={})
    session_id = r.json()["id"]

    resp = await client_with_embedder.post(
        f"/chat/sessions/{session_id}/messages",
        json={"content": "What changed?"},
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_send_message_failure_does_not_persist_messages(
    monkeypatch, client_with_embedder: AsyncClient
):
    async def fake_run_session_turn(**kwargs):
        raise RuntimeError("checkpointer unavailable")

    monkeypatch.setattr("app.api.routes_chat.run_session_turn", fake_run_session_turn)

    r = await client_with_embedder.post("/chat/sessions", json={})
    session_id = r.json()["id"]

    await client_with_embedder.post(
        f"/chat/sessions/{session_id}/messages",
        json={"content": "What changed?"},
    )

    detail = await client_with_embedder.get(f"/chat/sessions/{session_id}")
    assert detail.json()["messages"] == []


@pytest.mark.asyncio
async def test_session_message_count_updates(monkeypatch, client_with_embedder: AsyncClient):
    fake_result = {
        "answer": "A.",
        "citations": [],
        "run_id": uuid.uuid4(),
        "tokens_used": 5,
        "prompt_tokens": 3,
        "completion_tokens": 2,
        "retrieved_context_count": 0,
        "error": None,
    }

    async def fake_run_session_turn(**kwargs):
        return fake_result

    monkeypatch.setattr("app.api.routes_chat.run_session_turn", fake_run_session_turn)

    r = await client_with_embedder.post("/chat/sessions", json={})
    session_id = r.json()["id"]

    await client_with_embedder.post(f"/chat/sessions/{session_id}/messages", json={"content": "Q1"})
    await client_with_embedder.post(f"/chat/sessions/{session_id}/messages", json={"content": "Q2"})

    sessions = await client_with_embedder.get("/chat/sessions")
    session = next(s for s in sessions.json() if s["id"] == session_id)
    assert session["message_count"] == 4  # 2 user + 2 assistant


@pytest.mark.asyncio
async def test_existing_single_turn_endpoint_unchanged(client_with_embedder: AsyncClient):
    """POST /chat/answer must still work unchanged."""
    resp = await client_with_embedder.post("/chat/answer", json={"question": "What changed?"})
    # No spans → insufficient evidence, but 200 (not 404 or 500)
    assert resp.status_code == 200
    assert "evidence" in resp.json()["answer"].lower()
