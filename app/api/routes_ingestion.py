import re
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import DbSession
from app.db.models import Document, Source, Span
from app.ingestion.cleaner import content_hash, normalize_url
from app.ingestion.rss import fetch_rss_entries
from app.ingestion.url_fetcher import fetch_and_clean

# Allowlist for user-supplied identifier fields stored to the database.
_IDENTIFIER_RE = re.compile(r"^[a-z0-9_\-]{1,64}$")
_MAX_TEXT_BYTES = 512 * 1024  # 512 KB


def _validate_identifier(value: str, field_name: str) -> str:
    if not _IDENTIFIER_RE.match(value):
        raise ValueError(
            f"'{field_name}' must be 1–64 lowercase alphanumeric characters, hyphens, or underscores."
        )
    return value


router = APIRouter(tags=["ingestion"])


# ---------------------------------------------------------------------------
# Background task: chunk and embed a persisted document
# ---------------------------------------------------------------------------


async def _chunk_and_embed(
    doc_id: uuid.UUID,
    session_factory: async_sessionmaker,
    embedder: Any,
) -> None:
    """Chunk a document's clean_text into spans and embed them; updates document status.

    This task is scheduled via FastAPI BackgroundTasks, which guarantees it runs
    after the response (and therefore after the route's session.commit()) has been
    sent.  Do not call this synchronously before the outer session commits — the
    document row won't exist yet and the early-exit on line 'if doc is None' will
    silently skip processing.
    """
    from app.ingestion.chunker import chunk_document

    async with session_factory() as session:
        doc = await session.get(Document, doc_id)
        if doc is None:
            return

        # Idempotency: skip if already processed.
        if doc.status == "embedded":
            return

        spans_data = chunk_document(doc.clean_text or "")

        doc.status = "chunked"
        for s in spans_data:
            session.add(
                Span(
                    document_id=doc_id,
                    span_index=s["span_index"],
                    text=s["text"],
                    token_count=s["token_count"],
                    metadata_json=s["metadata_json"],
                )
            )
        await session.commit()

    if not spans_data or embedder is None:
        return

    async with session_factory() as session:
        spans = (
            (
                await session.execute(
                    select(Span).where(Span.document_id == doc_id).order_by(Span.span_index)
                )
            )
            .scalars()
            .all()
        )

        vectors = embedder.embed([s.text for s in spans])
        for span, vec in zip(spans, vectors, strict=True):
            span.embedding = vec

        doc = await session.get(Document, doc_id)
        if doc:
            doc.status = "embedded"

        await session.commit()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class DocumentResponse(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    title: str | None
    url: str | None
    content_hash: str
    status: str
    fetched_at: datetime

    model_config = {"from_attributes": True}


class IngestResult(BaseModel):
    ingested: int
    skipped: int
    documents: list[DocumentResponse]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _persist_document(
    session: AsyncSession,
    *,
    source_id: uuid.UUID,
    title: str | None,
    url: str | None,
    raw_text: str,
    clean_text: str,
    published_at: datetime | None,
) -> Document | None:
    """Persist a document; return None if it is a duplicate (URL or content hash).

    Uses select-before-insert rather than savepoints: asyncpg 0.29+ marks the
    outer transaction as deactive when a savepoint rolls back on a constraint
    violation, making subsequent commits fail with PendingRollbackError.
    """
    from sqlalchemy import or_

    norm_url = normalize_url(url) if url else None
    chash = content_hash(clean_text)

    where_clauses = [Document.content_hash == chash]
    if norm_url:
        where_clauses.append(Document.url == norm_url)

    existing = await session.scalar(select(Document.id).where(or_(*where_clauses)))
    if existing is not None:
        return None

    doc = Document(
        source_id=source_id,
        title=title,
        url=norm_url,
        raw_text=raw_text,
        clean_text=clean_text,
        content_hash=chash,
        published_at=published_at,
        status="fetched",
    )
    session.add(doc)
    return doc


async def _get_or_create_manual_source(
    session: AsyncSession, *, name: str, domain_pack: str
) -> Source:
    """Return an existing manual source matching (name, domain_pack), or create one."""
    source = await session.scalar(
        select(Source).where(
            Source.source_type == "manual",
            Source.name == name,
            Source.domain_pack == domain_pack,
        )
    )
    if source is None:
        source = Source(name=name, source_type="manual", url=None, domain_pack=domain_pack)
        session.add(source)
        # Flush immediately so source.id is available for document foreign keys.
        # Manual sources have no unique URL, so no IntegrityError risk here.
        await session.flush()
    return source


# ---------------------------------------------------------------------------
# POST /ingest/rss/{source_id}
# ---------------------------------------------------------------------------


@router.post("/ingest/rss/{source_id}", response_model=IngestResult)
async def ingest_rss(
    source_id: uuid.UUID,
    session: DbSession,
    request: Request,
    background_tasks: BackgroundTasks,
) -> IngestResult:
    source = await session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found.")
    if source.source_type != "rss":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Source '{source_id}' has type '{source.source_type}', not 'rss'.",
        )
    if not source.url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="RSS source has no feed URL configured.",
        )

    entries = await fetch_rss_entries(source.url)

    ingested: list[Document] = []
    skipped = 0
    for entry in entries:
        doc = await _persist_document(
            session,
            source_id=source.id,
            title=entry["title"],
            url=entry["url"],
            raw_text=entry["raw_text"],
            clean_text=entry["clean_text"],
            published_at=entry["published_at"],
        )
        if doc:
            ingested.append(doc)
        else:
            skipped += 1

    await session.commit()
    for doc in ingested:
        await session.refresh(doc)

    session_factory = request.app.state.session_factory
    embedder = getattr(request.app.state, "embedder", None)
    for doc in ingested:
        background_tasks.add_task(_chunk_and_embed, doc.id, session_factory, embedder)

    return IngestResult(
        ingested=len(ingested),
        skipped=skipped,
        documents=[DocumentResponse.model_validate(d) for d in ingested],
    )


# ---------------------------------------------------------------------------
# POST /ingest/url
# ---------------------------------------------------------------------------


class IngestURLPayload(BaseModel):
    url: str = Field(max_length=2048)
    domain_pack: str = "personal_ai_tech"
    source_name: str = "manual"

    @field_validator("domain_pack", "source_name")
    @classmethod
    def _check_identifier(cls, v: str, info) -> str:
        return _validate_identifier(v, info.field_name)


@router.post("/ingest/url", response_model=IngestResult)
async def ingest_url(
    payload: IngestURLPayload,
    session: DbSession,
    request: Request,
    background_tasks: BackgroundTasks,
) -> IngestResult:
    source = await _get_or_create_manual_source(
        session, name=payload.source_name, domain_pack=payload.domain_pack
    )

    try:
        raw_text, clean_text = await fetch_and_clean(payload.url)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch URL: {exc}",
        ) from exc

    doc = await _persist_document(
        session,
        source_id=source.id,
        title=None,
        url=payload.url,
        raw_text=raw_text,
        clean_text=clean_text,
        published_at=None,
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return IngestResult(ingested=0, skipped=1, documents=[])
    if doc is None:
        return IngestResult(ingested=0, skipped=1, documents=[])
    await session.refresh(doc)

    session_factory = request.app.state.session_factory
    embedder = getattr(request.app.state, "embedder", None)
    background_tasks.add_task(_chunk_and_embed, doc.id, session_factory, embedder)

    return IngestResult(ingested=1, skipped=0, documents=[DocumentResponse.model_validate(doc)])


# ---------------------------------------------------------------------------
# POST /ingest/text
# ---------------------------------------------------------------------------


class IngestTextPayload(BaseModel):
    title: str = Field(max_length=1024)
    text: str = Field(max_length=_MAX_TEXT_BYTES)
    source_name: str = "manual"
    domain_pack: str = "personal_ai_tech"

    @field_validator("domain_pack", "source_name")
    @classmethod
    def _check_identifier(cls, v: str, info) -> str:
        return _validate_identifier(v, info.field_name)


@router.post("/ingest/text", response_model=IngestResult)
async def ingest_text(
    payload: IngestTextPayload,
    session: DbSession,
    request: Request,
    background_tasks: BackgroundTasks,
) -> IngestResult:
    if not payload.text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Text payload is empty.",
        )

    source = await _get_or_create_manual_source(
        session, name=payload.source_name, domain_pack=payload.domain_pack
    )

    doc = await _persist_document(
        session,
        source_id=source.id,
        title=payload.title,
        url=None,
        raw_text=payload.text,
        clean_text=payload.text,
        published_at=None,
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return IngestResult(ingested=0, skipped=1, documents=[])
    if doc is None:
        return IngestResult(ingested=0, skipped=1, documents=[])
    await session.refresh(doc)

    session_factory = request.app.state.session_factory
    embedder = getattr(request.app.state, "embedder", None)
    background_tasks.add_task(_chunk_and_embed, doc.id, session_factory, embedder)

    return IngestResult(ingested=1, skipped=0, documents=[DocumentResponse.model_validate(doc)])
