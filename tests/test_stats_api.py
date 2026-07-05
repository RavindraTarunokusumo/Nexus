"""Integration tests for GET /stats/overview."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import (
    AgentRun,
    Document,
    SemanticCapsule,
    SemanticRelation,
    Source,
    Span,
    Thesis,
)


async def _seed_overview_data(session_factory: async_sessionmaker) -> None:
    async with session_factory() as session:
        source = Source(
            name="Src",
            source_type="rss",
            url=f"https://stats-{uuid.uuid4()}.example/feed",
        )
        session.add(source)
        await session.flush()

        doc = Document(
            source_id=source.id,
            title="Article",
            clean_text="body",
            content_hash=f"h-{uuid.uuid4()}",
            status="embedded",
        )
        session.add(doc)
        await session.flush()

        span = Span(document_id=doc.id, span_index=0, text="Span text.", token_count=3)
        session.add(span)
        await session.flush()

        cap_active = SemanticCapsule(
            source_id=source.id,
            document_id=doc.id,
            idempotency_key=f"k-{uuid.uuid4()}",
            core_type="claim",
            text="Active capsule.",
            domain="personal_ai_tech",
            object_family="model_release_event",
            domain_object_type="model_release",
            lifecycle_state="active",
            created_by_tier="t2",
        )
        cap_confirmed = SemanticCapsule(
            source_id=source.id,
            document_id=doc.id,
            idempotency_key=f"k-{uuid.uuid4()}",
            core_type="claim",
            text="Confirmed capsule.",
            domain="personal_ai_tech",
            object_family="model_release_event",
            domain_object_type="model_release",
            lifecycle_state="confirmed",
            created_by_tier="t2",
        )
        session.add_all([cap_active, cap_confirmed])
        await session.flush()

        relation = SemanticRelation(
            source_capsule_id=cap_active.id,
            target_capsule_id=cap_confirmed.id,
            relation_type="supports",
            polarity="positive",
            strength=0.8,
            created_by_tier="t2",
        )
        session.add(relation)
        await session.flush()

        thesis = Thesis(
            domain="personal_ai_tech",
            thesis_type="cluster",
            statement="Models are advancing rapidly.",
            supporting_capsule_ids=[cap_active.id],
            created_by_tier="t2",
        )
        session.add(thesis)
        await session.flush()

        session.add_all(
            [
                AgentRun(
                    run_type="chat_answer",
                    model="deepseek/deepseek-v4-flash",
                    prompt_tokens=100,
                    completion_tokens=50,
                    cost_estimate=0.001,
                    status="ok",
                ),
                AgentRun(
                    run_type="chat_answer",
                    model="deepseek/deepseek-v4-flash",
                    prompt_tokens=200,
                    completion_tokens=80,
                    cost_estimate=0.002,
                    status="ok",
                ),
                AgentRun(
                    run_type="extract_claims",
                    model="deepseek/deepseek-v4-flash",
                    prompt_tokens=300,
                    completion_tokens=0,
                    cost_estimate=0.0005,
                    status="ok",
                ),
            ]
        )
        await session.commit()


@pytest.mark.asyncio
async def test_stats_overview_empty_db(client: AsyncClient):
    resp = await client.get("/stats/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["counts"] == {
        "documents": 0,
        "spans": 0,
        "capsules": 0,
        "relations": 0,
        "theses": 0,
    }
    assert data["lifecycle"] == {}
    assert data["model_usage"] == []


@pytest.mark.asyncio
async def test_stats_overview_seeded_db(client: AsyncClient, session_factory: async_sessionmaker):
    await _seed_overview_data(session_factory)

    resp = await client.get("/stats/overview")
    assert resp.status_code == 200
    data = resp.json()

    assert data["counts"]["documents"] == 1
    assert data["counts"]["spans"] == 1
    assert data["counts"]["capsules"] == 2
    assert data["counts"]["relations"] == 1
    assert data["counts"]["theses"] == 1

    assert data["lifecycle"]["active"] == 1
    assert data["lifecycle"]["confirmed"] == 1

    assert len(data["model_usage"]) == 2
    chat_row = next(r for r in data["model_usage"] if r["run_type"] == "chat_answer")
    assert chat_row["model"] == "deepseek/deepseek-v4-flash"
    assert chat_row["calls"] == 2
    assert chat_row["prompt_tokens"] == 300
    assert chat_row["completion_tokens"] == 130
    assert chat_row["cost_estimate_usd"] == pytest.approx(0.003)

    extract_row = next(r for r in data["model_usage"] if r["run_type"] == "extract_claims")
    assert extract_row["calls"] == 1
    assert extract_row["prompt_tokens"] == 300
