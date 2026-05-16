"""CLI database readers — short-lived asyncpg connections per call."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.db.models import Document, Source, Span


async def _with_session(database_url: str, fn):
    """Run `fn(session)` against a fresh engine and dispose afterwards."""
    engine = create_async_engine(database_url, echo=False)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
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


async def get_status_snapshot(database_url: str) -> dict[str, Any]:
    async def _q(session):
        status_rows = (
            await session.execute(
                select(Document.status, func.count(Document.id)).group_by(Document.status)
            )
        ).all()
        docs_by_status = {row[0]: row[1] for row in status_rows}

        total_documents = await session.scalar(select(func.count(Document.id))) or 0
        total_spans = await session.scalar(select(func.count(Span.id))) or 0
        total_sources = await session.scalar(select(func.count(Source.id))) or 0
        enabled_sources = (
            await session.scalar(select(func.count(Source.id)).where(Source.enabled))
        ) or 0
        last_ingest_at = await session.scalar(select(func.max(Document.fetched_at)))

        from datetime import timedelta, timezone as tz
        cutoff = datetime.now(tz.utc) - timedelta(hours=1)
        stuck = await session.scalar(
            select(func.count(Document.id)).where(
                Document.status.in_(["fetched", "chunked"]),
                Document.fetched_at < cutoff,
            )
        ) or 0

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
