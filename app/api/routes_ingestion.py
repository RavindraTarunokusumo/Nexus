import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Document, Source
from app.db.session import get_session
from app.ingestion.cleaner import content_hash, normalize_url
from app.ingestion.rss import fetch_rss_entries
from app.ingestion.url_fetcher import fetch_and_clean

router = APIRouter(tags=["ingestion"])


# ---------------------------------------------------------------------------
# Dependency helpers (shared with routes_sources)
# ---------------------------------------------------------------------------

def _get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    return request.app.state.session_factory


async def _db_session(
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(_get_session_factory)],
) -> AsyncSession:
    async with factory() as session:
        yield session


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
# Shared document persistence helper
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
    """Persist a document, returning None if it is a duplicate."""
    norm_url = normalize_url(url) if url else None
    chash = content_hash(clean_text)

    # URL dedup
    if norm_url:
        existing = await session.scalar(select(Document).where(Document.url == norm_url))
        if existing:
            return None

    # Content hash dedup
    existing = await session.scalar(select(Document).where(Document.content_hash == chash))
    if existing:
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
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return None
    await session.refresh(doc)
    return doc


# ---------------------------------------------------------------------------
# POST /ingest/rss/{source_id}
# ---------------------------------------------------------------------------

@router.post("/ingest/rss/{source_id}", response_model=IngestResult)
async def ingest_rss(
    source_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(_db_session)],
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

    return IngestResult(
        ingested=len(ingested),
        skipped=skipped,
        documents=[DocumentResponse.model_validate(d) for d in ingested],
    )


# ---------------------------------------------------------------------------
# POST /ingest/url
# ---------------------------------------------------------------------------

class IngestURLPayload(BaseModel):
    url: str
    domain_pack: str = "personal_ai_tech"
    source_name: str = "manual"


@router.post("/ingest/url", response_model=IngestResult)
async def ingest_url(
    payload: IngestURLPayload,
    session: Annotated[AsyncSession, Depends(_db_session)],
) -> IngestResult:
    # Find or create a manual source for this domain_pack
    source = await session.scalar(
        select(Source).where(
            Source.source_type == "manual",
            Source.name == payload.source_name,
            Source.domain_pack == payload.domain_pack,
        )
    )
    if source is None:
        source = Source(
            name=payload.source_name,
            source_type="manual",
            url=None,
            domain_pack=payload.domain_pack,
        )
        session.add(source)
        await session.flush()

    try:
        raw_text, clean_text = await fetch_and_clean(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch URL: {exc}",
        )

    doc = await _persist_document(
        session,
        source_id=source.id,
        title=None,
        url=payload.url,
        raw_text=raw_text,
        clean_text=clean_text,
        published_at=None,
    )

    if doc is None:
        return IngestResult(ingested=0, skipped=1, documents=[])

    return IngestResult(
        ingested=1,
        skipped=0,
        documents=[DocumentResponse.model_validate(doc)],
    )


# ---------------------------------------------------------------------------
# POST /ingest/text
# ---------------------------------------------------------------------------

class IngestTextPayload(BaseModel):
    title: str
    text: str
    source_name: str = "manual"
    domain_pack: str = "personal_ai_tech"


@router.post("/ingest/text", response_model=IngestResult)
async def ingest_text(
    payload: IngestTextPayload,
    session: Annotated[AsyncSession, Depends(_db_session)],
) -> IngestResult:
    if not payload.text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Text payload is empty.",
        )

    source = await session.scalar(
        select(Source).where(
            Source.source_type == "manual",
            Source.name == payload.source_name,
            Source.domain_pack == payload.domain_pack,
        )
    )
    if source is None:
        source = Source(
            name=payload.source_name,
            source_type="manual",
            url=None,
            domain_pack=payload.domain_pack,
        )
        session.add(source)
        await session.flush()

    doc = await _persist_document(
        session,
        source_id=source.id,
        title=payload.title,
        url=None,
        raw_text=payload.text,
        clean_text=payload.text,
        published_at=None,
    )

    if doc is None:
        return IngestResult(ingested=0, skipped=1, documents=[])

    return IngestResult(
        ingested=1,
        skipped=0,
        documents=[DocumentResponse.model_validate(doc)],
    )
