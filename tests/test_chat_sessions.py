"""Integration tests for chat session memory API endpoints."""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.routes_chat_sessions import router as chat_sessions_router

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

INSUFFICIENT = "I do not have enough evidence to answer that from the current corpus."


class _FakeMemoryGraph:
    """Minimal stub for app.state.memory_graph in tests."""

    def __init__(self, result: dict | None = None, raise_exc: Exception | None = None) -> None:
        self._result = result or {
            "answer": "Test answer.",
            "citations": [],
            "context_blocks": [],
            "run_id": uuid.uuid4(),
            "tokens_used": 50,
            "error": None,
        }
        self._raise = raise_exc
        self.calls: list[dict] = []

    async def ainvoke(self, state: dict, config: dict) -> dict:
        self.calls.append({"state": state, "config": config})
        if self._raise:
            raise self._raise
        return {**state, "chat_result": self._result, "messages": state["messages"]}


def _build_sessions_app(
    async_engine,
    session_factory,
    memory_graph=None,
) -> FastAPI:
    app = FastAPI()
    app.state.engine = async_engine
    app.state.session_factory = session_factory
    app.state.embedder = object()  # truthy non-None sentinel
    app.state.memory_graph = memory_graph
    app.include_router(chat_sessions_router)
    return app


@pytest.fixture
def fake_graph():
    return _FakeMemoryGraph()


@pytest.fixture
def fake_graph_insufficient():
    return _FakeMemoryGraph(
        result={
            "answer": INSUFFICIENT,
            "citations": [],
            "context_blocks": [],
            "run_id": uuid.uuid4(),
            "tokens_used": 0,
            "error": None,
        }
    )


# ---------------------------------------------------------------------------
# Session CRUD tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_session_returns_201(async_engine, session_factory):
    app = _build_sessions_app(async_engine, session_factory)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/chat/sessions", json={})
    assert resp.status_code == 201
    data = resp.json()
    assert uuid.UUID(data["id"])
    assert data["status"] == "active"
    assert data["message_count"] == 0
    assert data["last_message_preview"] is None


@pytest.mark.asyncio
async def test_create_session_with_title(async_engine, session_factory):
    app = _build_sessions_app(async_engine, session_factory)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/chat/sessions", json={"title": "My Session"})
    assert resp.status_code == 201
    assert resp.json()["title"] == "My Session"


@pytest.mark.asyncio
async def test_list_sessions_empty(async_engine, session_factory):
    app = _build_sessions_app(async_engine, session_factory)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/chat/sessions")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_sessions_filters_by_status(async_engine, session_factory):
    app = _build_sessions_app(async_engine, session_factory)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        s1 = (await c.post("/chat/sessions", json={"title": "Active"})).json()
        # Archive it
        await c.patch(f"/chat/sessions/{s1['id']}", json={"status": "archived"})

        active = await c.get("/chat/sessions?status=active")
        archived = await c.get("/chat/sessions?status=archived")

    assert active.json() == []
    assert len(archived.json()) == 1
    assert archived.json()[0]["id"] == s1["id"]


@pytest.mark.asyncio
async def test_get_session_404(async_engine, session_factory):
    app = _build_sessions_app(async_engine, session_factory)
    missing = str(uuid.uuid4())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/chat/sessions/{missing}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_session_returns_empty_messages(async_engine, session_factory):
    app = _build_sessions_app(async_engine, session_factory)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        session_id = (await c.post("/chat/sessions", json={})).json()["id"]
        resp = await c.get(f"/chat/sessions/{session_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == session_id
    assert data["messages"] == []


@pytest.mark.asyncio
async def test_patch_session_title_and_status(async_engine, session_factory):
    app = _build_sessions_app(async_engine, session_factory)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        session_id = (await c.post("/chat/sessions", json={})).json()["id"]
        resp = await c.patch(
            f"/chat/sessions/{session_id}", json={"title": "Renamed", "status": "archived"}
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Renamed"
    assert data["status"] == "archived"


# ---------------------------------------------------------------------------
# Send message tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_message_creates_user_and_assistant_rows(
    async_engine, session_factory, fake_graph
):
    app = _build_sessions_app(async_engine, session_factory, memory_graph=fake_graph)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        session_id = (await c.post("/chat/sessions", json={})).json()["id"]
        resp = await c.post(
            f"/chat/sessions/{session_id}/messages", json={"content": "What changed?"}
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_message"]["role"] == "user"
    assert data["user_message"]["content"] == "What changed?"
    assert data["assistant_message"]["role"] == "assistant"
    assert data["assistant_message"]["content"] == "Test answer."


@pytest.mark.asyncio
async def test_send_message_derives_title_from_first_message(
    async_engine, session_factory, fake_graph
):
    app = _build_sessions_app(async_engine, session_factory, memory_graph=fake_graph)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        session_id = (await c.post("/chat/sessions", json={})).json()["id"]
        await c.post(
            f"/chat/sessions/{session_id}/messages",
            json={"content": "What changed in LLM releases?"},
        )
        detail = await c.get(f"/chat/sessions/{session_id}")
    assert detail.json()["title"] == "What changed in LLM releases?"


@pytest.mark.asyncio
async def test_send_message_title_truncated_at_60_chars(async_engine, session_factory, fake_graph):
    app = _build_sessions_app(async_engine, session_factory, memory_graph=fake_graph)
    long_q = "A" * 80
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        session_id = (await c.post("/chat/sessions", json={})).json()["id"]
        await c.post(f"/chat/sessions/{session_id}/messages", json={"content": long_q})
        detail = await c.get(f"/chat/sessions/{session_id}")
    title = detail.json()["title"]
    assert title.endswith("...")
    assert len(title) == 63  # 60 chars + "..."


@pytest.mark.asyncio
async def test_send_message_to_archived_session_returns_409(async_engine, session_factory):
    app = _build_sessions_app(async_engine, session_factory)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        session_id = (await c.post("/chat/sessions", json={})).json()["id"]
        await c.patch(f"/chat/sessions/{session_id}", json={"status": "archived"})
        resp = await c.post(f"/chat/sessions/{session_id}/messages", json={"content": "Hello?"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_send_message_no_memory_graph_returns_503(async_engine, session_factory):
    app = _build_sessions_app(async_engine, session_factory, memory_graph=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        session_id = (await c.post("/chat/sessions", json={})).json()["id"]
        resp = await c.post(f"/chat/sessions/{session_id}/messages", json={"content": "Hello?"})
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_send_message_updates_message_count(async_engine, session_factory, fake_graph):
    app = _build_sessions_app(async_engine, session_factory, memory_graph=fake_graph)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        session_id = (await c.post("/chat/sessions", json={})).json()["id"]
        await c.post(f"/chat/sessions/{session_id}/messages", json={"content": "Q1"})
        resp = await c.get(f"/chat/sessions/{session_id}")
    assert resp.json()["message_count"] == 2  # user + assistant


@pytest.mark.asyncio
async def test_session_detail_shows_transcript(async_engine, session_factory, fake_graph):
    app = _build_sessions_app(async_engine, session_factory, memory_graph=fake_graph)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        session_id = (await c.post("/chat/sessions", json={})).json()["id"]
        await c.post(f"/chat/sessions/{session_id}/messages", json={"content": "Question"})
        detail = await c.get(f"/chat/sessions/{session_id}")
    msgs = detail.json()["messages"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_insufficient_evidence_persisted_with_empty_citations(
    async_engine, session_factory, fake_graph_insufficient
):
    app = _build_sessions_app(async_engine, session_factory, memory_graph=fake_graph_insufficient)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        session_id = (await c.post("/chat/sessions", json={})).json()["id"]
        resp = await c.post(
            f"/chat/sessions/{session_id}/messages", json={"content": "Unknown topic"}
        )
    assert resp.status_code == 200
    asst = resp.json()["assistant_message"]
    assert INSUFFICIENT in asst["content"]
    assert asst["citations"] == []
    assert asst["tokens_used"] == 0
