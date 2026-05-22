"""CLI database readers — short-lived asyncpg connections per call."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.db.models import AgentRun, Claim, Document, Source, Span, SpanExtraction
from app.db.session import make_engine, make_session_factory


async def _with_session(database_url: str, fn):
    """Run `fn(session)` against a fresh engine and dispose afterwards."""
    engine = make_engine(database_url)
    try:
        factory = make_session_factory(engine)
        async with factory() as session:
            return await fn(session)
    finally:
        await engine.dispose()


async def count_documents_by_status(database_url: str) -> dict[str, int]:
    async def _q(session):
        stmt = select(Document.status, func.count(Document.id)).group_by(Document.status)
        return {row[0]: row[1] for row in (await session.execute(stmt)).all()}

    return await _with_session(database_url, _q)


async def list_sources(database_url: str, enabled: bool | None) -> list[dict[str, Any]]:
    async def _q(session):
        stmt = select(Source).order_by(Source.created_at.desc())
        if enabled is not None:
            stmt = stmt.where(Source.enabled == enabled)
        rows = (await session.execute(stmt)).scalars().all()
        return [
            {
                "id": s.id,
                "name": s.name,
                "source_type": s.source_type,
                "url": s.url,
                "domain_pack": s.domain_pack,
                "enabled": s.enabled,
                "credibility_score": s.credibility_score,
            }
            for s in rows
        ]

    return await _with_session(database_url, _q)


async def list_documents(
    database_url: str,
    *,
    status: str | None,
    source_id: uuid.UUID | None,
    since: datetime | None,
    limit: int,
) -> list[dict[str, Any]]:
    async def _q(session):
        stmt = select(Document, Source.name.label("source_name")).join(
            Source, Document.source_id == Source.id
        )
        if status is not None:
            stmt = stmt.where(Document.status == status)
        if source_id is not None:
            stmt = stmt.where(Document.source_id == source_id)
        if since is not None:
            stmt = stmt.where(Document.fetched_at >= since)
        stmt = stmt.order_by(Document.fetched_at.desc()).limit(limit)
        rows = (await session.execute(stmt)).all()
        return [
            {
                "id": doc.id,
                "title": doc.title,
                "url": doc.url,
                "status": doc.status,
                "content_hash": doc.content_hash,
                "source_name": source_name,
                "fetched_at": doc.fetched_at,
                "published_at": doc.published_at,
            }
            for doc, source_name in rows
        ]

    return await _with_session(database_url, _q)


async def get_document_with_spans(
    database_url: str, document_id: uuid.UUID
) -> dict[str, Any] | None:
    async def _q(session):
        stmt = (
            select(Document, Source.name.label("source_name"))
            .join(Source, Document.source_id == Source.id)
            .where(Document.id == document_id)
            .options(selectinload(Document.spans))
        )
        row = (await session.execute(stmt)).first()
        if row is None:
            return None
        doc, source_name = row
        spans_sorted = sorted(doc.spans, key=lambda s: s.span_index)
        return {
            "id": doc.id,
            "title": doc.title,
            "url": doc.url,
            "status": doc.status,
            "content_hash": doc.content_hash,
            "source_name": source_name,
            "fetched_at": doc.fetched_at,
            "published_at": doc.published_at,
            "spans": [
                {
                    "id": s.id,
                    "span_index": s.span_index,
                    "text": s.text,
                    "token_count": s.token_count,
                    "has_embedding": s.embedding is not None,
                }
                for s in spans_sorted
            ],
        }

    return await _with_session(database_url, _q)


async def get_claims_for_document(
    database_url: str, document_id: uuid.UUID
) -> list[dict[str, Any]]:
    async def _q(session):
        stmt = (
            select(Claim).where(Claim.document_id == document_id).order_by(Claim.created_at.desc())
        )
        rows = (await session.execute(stmt)).scalars().all()
        return [
            {
                "id": c.id,
                "claim_text": c.claim_text,
                "claim_type": c.claim_type,
                "entities_json": c.entities_json or [],
                "topics_json": c.topics_json or [],
                "confidence": c.confidence,
                "status": c.status,
                "created_at": c.created_at,
            }
            for c in rows
        ]

    return await _with_session(database_url, _q)


async def get_status_snapshot(database_url: str) -> dict[str, Any]:
    async def _q(session):
        status_rows = (
            await session.execute(
                select(Document.status, func.count(Document.id)).group_by(Document.status)
            )
        ).all()
        docs_by_status = {row[0]: row[1] for row in status_rows}

        total_documents = sum(docs_by_status.values())
        total_spans = await session.scalar(select(func.count(Span.id))) or 0
        total_sources = await session.scalar(select(func.count(Source.id))) or 0
        enabled_sources = (
            await session.scalar(select(func.count(Source.id)).where(Source.enabled))
        ) or 0
        last_ingest_at = await session.scalar(select(func.max(Document.fetched_at)))

        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        stuck = (
            await session.scalar(
                select(func.count(Document.id)).where(
                    Document.status.in_(["fetched", "chunked"]),
                    Document.fetched_at < cutoff,
                )
            )
            or 0
        )

        return {
            "docs_by_status": docs_by_status,
            "total_documents": total_documents,
            "total_spans": total_spans,
            "total_sources": total_sources,
            "enabled_sources": enabled_sources,
            "last_ingest_at": last_ingest_at,
            "stuck_count": stuck,
        }

    return await _with_session(database_url, _q)


async def list_runs(database_url: str, limit: int = 50) -> list[dict[str, Any]]:
    """Return recent distinct runs with summary metrics, ordered by first LLM call."""

    async def _q(session):
        stmt = (
            select(
                AgentRun.run_id,
                AgentRun.document_id,
                AgentRun.model,
                func.count(AgentRun.id).label("llm_calls"),
                func.sum(AgentRun.cost_estimate).label("total_cost"),
                func.min(AgentRun.created_at).label("started_at"),
                func.bool_and(AgentRun.status == "success").label("all_success"),
            )
            .where(AgentRun.run_id.isnot(None))
            .group_by(AgentRun.run_id, AgentRun.document_id, AgentRun.model)
            .order_by(func.min(AgentRun.created_at).desc())
            .limit(limit)
        )
        rows = (await session.execute(stmt)).all()
        return [
            {
                "run_id": row.run_id,
                "document_id": row.document_id,
                "model": row.model,
                "llm_calls": row.llm_calls,
                "total_cost": float(row.total_cost) if row.total_cost is not None else 0.0,
                "started_at": row.started_at,
                "all_success": row.all_success,
            }
            for row in rows
        ]

    return await _with_session(database_url, _q)


async def show_run(database_url: str, run_id: str) -> dict[str, Any] | None:
    """Return full trace for a run_id: agent_runs, span_extractions, and document summary."""
    run_uuid = uuid.UUID(run_id)

    async def _q(session):
        ar_rows = (
            await session.execute(
                select(AgentRun)
                .where(AgentRun.run_id == run_uuid)
                .order_by(AgentRun.created_at)
            )
        ).scalars().all()

        if not ar_rows:
            return None

        se_rows = (
            await session.execute(
                select(SpanExtraction)
                .where(SpanExtraction.run_id == run_uuid)
                .order_by(SpanExtraction.created_at)
            )
        ).scalars().all()

        doc_id = ar_rows[0].document_id
        doc_info = None
        if doc_id:
            doc = await session.get(Document, doc_id)
            if doc:
                doc_info = {
                    "id": doc.id,
                    "status": doc.status,
                    "extraction_started_at": doc.extraction_started_at,
                    "extraction_completed_at": doc.extraction_completed_at,
                }

        return {
            "run_id": run_id,
            "document": doc_info,
            "agent_runs": [
                {
                    "id": ar.id,
                    "run_type": ar.run_type,
                    "span_id": ar.span_id,
                    "status": ar.status,
                    "model": ar.model,
                    "prompt_tokens": ar.prompt_tokens,
                    "completion_tokens": ar.completion_tokens,
                    "cost_estimate": ar.cost_estimate,
                    "created_at": ar.created_at,
                }
                for ar in ar_rows
            ],
            "span_extractions": [
                {
                    "id": se.id,
                    "span_id": se.span_id,
                    "status": se.status,
                    "attempts": se.attempts,
                    "error": se.error,
                    "created_at": se.created_at,
                }
                for se in se_rows
            ],
        }

    return await _with_session(database_url, _q)
