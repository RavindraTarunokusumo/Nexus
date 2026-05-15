import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Source
from app.db.session import get_session

router = APIRouter(prefix="/sources", tags=["sources"])

SUPPORTED_SOURCE_TYPES = {"rss", "manual", "api"}


class SourceCreate(BaseModel):
    name: str
    source_type: str
    url: str | None = None
    domain_pack: str = "personal_ai_tech"
    enabled: bool = True
    credibility_score: float = Field(default=0.8, ge=0.0, le=1.0)


class SourceResponse(BaseModel):
    id: uuid.UUID
    name: str
    source_type: str
    url: str | None
    domain_pack: str
    enabled: bool
    credibility_score: float
    created_at: datetime

    model_config = {"from_attributes": True}


def _get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    return request.app.state.session_factory


async def _db_session(
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(_get_session_factory)],
) -> AsyncSession:
    async with factory() as session:
        yield session


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(
    payload: SourceCreate,
    session: Annotated[AsyncSession, Depends(_db_session)],
) -> SourceResponse:
    if payload.source_type not in SUPPORTED_SOURCE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported source_type '{payload.source_type}'. "
            f"Allowed: {sorted(SUPPORTED_SOURCE_TYPES)}",
        )

    if payload.url:
        existing = await session.scalar(select(Source).where(Source.url == payload.url))
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Source with URL '{payload.url}' already exists.",
            )

    source = Source(
        name=payload.name,
        source_type=payload.source_type,
        url=payload.url,
        domain_pack=payload.domain_pack,
        enabled=payload.enabled,
        credibility_score=payload.credibility_score,
    )
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return SourceResponse.model_validate(source)


@router.get("", response_model=list[SourceResponse])
async def list_sources(
    session: Annotated[AsyncSession, Depends(_db_session)],
) -> list[SourceResponse]:
    result = await session.execute(select(Source).order_by(Source.created_at.desc()))
    sources = result.scalars().all()
    return [SourceResponse.model_validate(s) for s in sources]


@router.get("/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(_db_session)],
) -> SourceResponse:
    source = await session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found.")
    return SourceResponse.model_validate(source)
