"""Integration tests for GET /capsules/{capsule_id}/provenance and chat metadata."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import (
    CapsuleSegment,
    Document,
    SemanticCapsule,
    SemanticRelation,
    Source,
    Span,
    Thesis,
)
from app.intelligence.chat import INSUFFICIENT_EVIDENCE_ANSWER


async def _seed_provenance_graph(
    session_factory: async_sessionmaker,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    async with session_factory() as session:
        source = Source(
            name="Src",
            source_type="rss",
            url=f"https://prov-{uuid.uuid4()}.example/feed",
        )
        session.add(source)
        await session.flush()

        doc = Document(
            source_id=source.id,
            title="Provenance doc",
            url=f"https://prov-{uuid.uuid4()}.example/article",
            clean_text="body",
            content_hash=f"h-{uuid.uuid4()}",
            status="embedded",
        )
        session.add(doc)
        await session.flush()

        span = Span(
            document_id=doc.id,
            span_index=1,
            text="A" * 250,
            token_count=50,
        )
        session.add(span)
        await session.flush()

        capsule = SemanticCapsule(
            source_id=source.id,
            document_id=doc.id,
            idempotency_key=f"k-{uuid.uuid4()}",
            core_type="claim",
            text="B" * 250,
            domain="personal_ai_tech",
            object_family="model_release_event",
            domain_object_type="model_release",
            lifecycle_state="active",
            salience=0.7,
            confidence=0.9,
            created_by_tier="t2",
        )
        other_capsule = SemanticCapsule(
            source_id=source.id,
            document_id=doc.id,
            idempotency_key=f"k-{uuid.uuid4()}",
            core_type="claim",
            text="C" * 250,
            domain="personal_ai_tech",
            object_family="model_release_event",
            domain_object_type="model_release",
            lifecycle_state="confirmed",
            created_by_tier="t2",
        )
        session.add_all([capsule, other_capsule])
        await session.flush()

        session.add(CapsuleSegment(capsule_id=capsule.id, segment_id=span.id))
        session.add(
            SemanticRelation(
                source_capsule_id=capsule.id,
                target_capsule_id=other_capsule.id,
                relation_type="supports",
                polarity="positive",
                strength=0.75,
                created_by_tier="t2",
            )
        )
        session.add(
            SemanticRelation(
                source_capsule_id=other_capsule.id,
                target_capsule_id=capsule.id,
                relation_type="contradicts",
                polarity="negative",
                strength=0.6,
                created_by_tier="t2",
            )
        )
        session.add(
            Thesis(
                domain="personal_ai_tech",
                thesis_type="cluster",
                statement="D" * 250,
                supporting_capsule_ids=[capsule.id],
                created_by_tier="t2",
            )
        )
        await session.commit()
        return capsule.id, other_capsule.id, doc.id


@pytest.mark.asyncio
async def test_provenance_not_found(client: AsyncClient):
    resp = await client.get(f"/capsules/{uuid.uuid4()}/provenance")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_provenance_happy_path(client: AsyncClient, session_factory: async_sessionmaker):
    capsule_id, other_id, doc_id = await _seed_provenance_graph(session_factory)

    resp = await client.get(f"/capsules/{capsule_id}/provenance")
    assert resp.status_code == 200
    data = resp.json()

    assert data["capsule"]["id"] == str(capsule_id)
    assert data["capsule"]["text"] == "B" * 250
    assert data["capsule"]["lifecycle_state"] == "active"
    assert data["capsule"]["salience"] == pytest.approx(0.7)
    assert data["capsule"]["confidence"] == pytest.approx(0.9)

    assert data["document"]["id"] == str(doc_id)
    assert data["document"]["title"] == "Provenance doc"

    assert len(data["spans"]) == 1
    assert data["spans"][0]["span_index"] == 1
    assert len(data["spans"][0]["text_excerpt"]) == 200

    directions = {r["direction"] for r in data["relations"]}
    assert directions == {"in", "out"}
    relation_types = {r["relation_type"] for r in data["relations"]}
    assert relation_types == {"supports", "contradicts"}
    for rel in data["relations"]:
        assert len(rel["other_capsule"]["text_excerpt"]) == 200
        assert rel["other_capsule"]["id"] in {str(capsule_id), str(other_id)}

    assert len(data["theses"]) == 1
    assert len(data["theses"][0]["statement_excerpt"]) == 200


@pytest.mark.asyncio
async def test_provenance_no_relations_or_theses(
    client: AsyncClient, session_factory: async_sessionmaker
):
    async with session_factory() as session:
        source = Source(
            name="Lonely",
            source_type="rss",
            url=f"https://lonely-{uuid.uuid4()}.example/feed",
        )
        session.add(source)
        await session.flush()
        doc = Document(
            source_id=source.id,
            content_hash=f"h-{uuid.uuid4()}",
            status="embedded",
        )
        session.add(doc)
        await session.flush()
        capsule = SemanticCapsule(
            source_id=source.id,
            document_id=doc.id,
            idempotency_key=f"k-{uuid.uuid4()}",
            core_type="claim",
            text="solo",
            domain="personal_ai_tech",
            object_family="model_release_event",
            domain_object_type="model_release",
            created_by_tier="t2",
        )
        session.add(capsule)
        await session.commit()
        capsule_id = capsule.id

    resp = await client.get(f"/capsules/{capsule_id}/provenance")
    assert resp.status_code == 200
    data = resp.json()
    assert data["relations"] == []
    assert data["theses"] == []
    assert data["spans"] == []


@pytest.mark.asyncio
async def test_chat_answer_includes_question_shape_and_query_intent(
    monkeypatch, client_with_embedder: AsyncClient
):
    async def fake_run_chat_with_context(graph, question, model, *, top_k):
        return {
            "answer": INSUFFICIENT_EVIDENCE_ANSWER,
            "citations": [],
            "run_id": uuid.uuid4(),
            "tokens_used": 42,
            "error": None,
            "question_shape": "timeline",
            "query_intent": "what_changed",
        }

    monkeypatch.setattr("app.api.routes_chat.run_chat_with_context", fake_run_chat_with_context)
    resp = await client_with_embedder.post("/chat/answer", json={"question": "What changed?"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["question_shape"] == "timeline"
    assert data["query_intent"] == "what_changed"


@pytest.mark.asyncio
async def test_chat_answer_defaults_shape_and_intent_when_absent(
    monkeypatch, client_with_embedder: AsyncClient
):
    async def fake_run_chat_with_context(graph, question, model, *, top_k):
        return {
            "answer": INSUFFICIENT_EVIDENCE_ANSWER,
            "citations": [],
            "run_id": uuid.uuid4(),
            "tokens_used": 0,
            "error": None,
        }

    monkeypatch.setattr("app.api.routes_chat.run_chat_with_context", fake_run_chat_with_context)
    resp = await client_with_embedder.post("/chat/answer", json={"question": "Hello?"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["question_shape"] == "general"
    assert data["query_intent"] == "general"


@pytest.mark.asyncio
async def test_session_message_includes_question_shape_and_query_intent(
    monkeypatch, client_with_embedder: AsyncClient
):
    async def fake_run_session_turn(**kwargs):
        return {
            "answer": "Grounded.",
            "citations": [],
            "run_id": uuid.uuid4(),
            "tokens_used": 10,
            "retrieved_context_count": 0,
            "error": None,
            "question_shape": "comparison",
            "query_intent": "compare_models",
        }

    # Relies on chat_router registering first; patching the shared intelligence
    # boundary is the tracked follow-up.
    monkeypatch.setattr("app.api.routes_chat.run_session_turn", fake_run_session_turn)

    r = await client_with_embedder.post("/chat/sessions", json={})
    session_id = r.json()["id"]

    resp = await client_with_embedder.post(
        f"/chat/sessions/{session_id}/messages",
        json={"content": "Compare GPT and Claude"},
    )
    assert resp.status_code == 200
    assistant = resp.json()["assistant_message"]
    assert assistant["question_shape"] == "comparison"
    assert assistant["query_intent"] == "compare_models"
