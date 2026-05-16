"""Document listing, detail, and vector search endpoints."""
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession
from app.db.models import Document, Span

router = APIRouter(tags=["documents"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class SpanResponse(BaseModel):
    id: uuid.UUID
    span_index: int
    text: str
    token_count: int | None
    metadata_json: dict | None

    model_config = {"from_attributes": True}


class DocumentListItem(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    title: str | None
    url: str | None
    status: str
    fetched_at: datetime

    model_config = {"from_attributes": True}


class DocumentDetail(DocumentListItem):
    content_hash: str
    raw_text: str | None
    clean_text: str | None
    published_at: datetime | None
    spans: list[SpanResponse]


class SearchQuery(BaseModel):
    query: str = Field(min_length=1, max_length=2048)
    top_k: int = Field(default=10, ge=1, le=100)


class SpanSearchResult(BaseModel):
    span_id: uuid.UUID
    document_id: uuid.UUID
    span_index: int
    text: str
    score: float
    document_title: str | None
    document_status: str


# ---------------------------------------------------------------------------
# GET /documents
# ---------------------------------------------------------------------------


@router.get("/documents", response_model=list[DocumentListItem])
async def list_documents(
    session: DbSession,
    doc_status: str | None = None,
    source_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[DocumentListItem]:
    q = select(Document)
    if doc_status is not None:
        q = q.where(Document.status == doc_status)
    if source_id is not None:
        q = q.where(Document.source_id == source_id)
    q = q.order_by(Document.fetched_at.desc()).limit(limit).offset(offset)
    docs = (await session.execute(q)).scalars().all()
    return [DocumentListItem.model_validate(d) for d in docs]


# ---------------------------------------------------------------------------
# GET /documents/{document_id}
# ---------------------------------------------------------------------------


@router.get("/documents/{document_id}", response_model=DocumentDetail)
async def get_document(document_id: uuid.UUID, session: DbSession) -> DocumentDetail:
    doc = await session.scalar(
        select(Document)
        .where(Document.id == document_id)
        .options(selectinload(Document.spans))
    )
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return DocumentDetail.model_validate(doc)


# ---------------------------------------------------------------------------
# POST /search/spans
# ---------------------------------------------------------------------------


@router.post("/search/spans", response_model=list[SpanSearchResult])
async def search_spans(
    payload: SearchQuery,
    request: Request,
    session: DbSession,
) -> list[SpanSearchResult]:
    embedder = getattr(request.app.state, "embedder", None)
    if embedder is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedder not initialised.",
        )

    # Return empty results when the index has no embedded spans yet.
    sentinel = await session.scalar(
        select(Span).where(Span.embedding.isnot(None)).limit(1)
    )
    if sentinel is None:
        return []

    query_vec = embedder.embed_one(payload.query)

    rows = (
        await session.execute(
            select(
                Span.id,
                Span.document_id,
                Span.span_index,
                Span.text,
                (1 - Span.embedding.cosine_distance(query_vec)).label("score"),
                Document.title.label("title"),
                Document.status.label("doc_status"),
            )
            .join(Document, Span.document_id == Document.id)
            .where(Span.embedding.isnot(None))
            .order_by(Span.embedding.cosine_distance(query_vec))
            .limit(payload.top_k)
        )
    ).all()

    return [
        SpanSearchResult(
            span_id=row.id,
            document_id=row.document_id,
            span_index=row.span_index,
            text=row.text,
            score=float(row.score),
            document_title=row.title,
            document_status=row.doc_status,
        )
        for row in rows
    ]
