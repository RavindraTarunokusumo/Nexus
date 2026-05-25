from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession
from app.db.models import ChatMessage, ChatSession
from app.intelligence.chat import ChatCitation
from app.intelligence.llm_client import _COST_PER_TOKEN_USD, LLMError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat-sessions"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class PatchSessionRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    status: str | None = Field(default=None, pattern="^(active|archived)$")


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2048)
    top_k: int = Field(default=8, ge=1, le=20)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be blank")
        return v


class ChatSessionSummary(BaseModel):
    id: uuid.UUID
    title: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    last_message_preview: str | None


class ChatMessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime
    run_id: uuid.UUID | None = None
    citations: list[ChatCitation] | None = None
    retrieved_context_count: int | None = None
    tokens_used: int | None = None
    cost_estimate_usd: float | None = None


class ChatSessionDetail(ChatSessionSummary):
    messages: list[ChatMessageOut]


class SendMessageResponse(BaseModel):
    session: ChatSessionSummary
    user_message: ChatMessageOut
    assistant_message: ChatMessageOut


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TITLE_MAX = 60


def _derive_title(content: str) -> str:
    collapsed = " ".join(content.split())
    if len(collapsed) <= _TITLE_MAX:
        return collapsed
    return collapsed[:_TITLE_MAX] + "..."


async def _session_summary(session: ChatSession, db: AsyncSession) -> ChatSessionSummary:
    count_result = await db.execute(
        select(func.count()).where(ChatMessage.session_id == session.id)
    )
    message_count = count_result.scalar_one()

    last_result = await db.execute(
        select(ChatMessage.content)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(1)
    )
    last_row = last_result.scalar_one_or_none()
    preview: str | None = last_row[:100] if last_row else None

    return ChatSessionSummary(
        id=session.id,
        title=session.title,
        status=session.status,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=message_count,
        last_message_preview=preview,
    )


def _message_out(msg: ChatMessage) -> ChatMessageOut:
    citations: list[ChatCitation] | None = None
    if msg.citations_json is not None:
        citations = [ChatCitation.model_validate(c) for c in msg.citations_json]
    return ChatMessageOut(
        id=msg.id,
        role=msg.role,
        content=msg.content,
        created_at=msg.created_at,
        run_id=msg.run_id,
        citations=citations,
        retrieved_context_count=msg.retrieved_context_count,
        tokens_used=msg.tokens_used,
        cost_estimate_usd=msg.cost_estimate_usd,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/sessions", response_model=ChatSessionSummary, status_code=status.HTTP_201_CREATED)
async def create_session(payload: CreateSessionRequest, db: DbSession) -> ChatSessionSummary:
    session = ChatSession(title=payload.title)
    db.add(session)
    await db.flush()
    await db.commit()
    await db.refresh(session)
    logger.info("chat_session.created", extra={"session_id": str(session.id)})
    return ChatSessionSummary(
        id=session.id,
        title=session.title,
        status=session.status,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=0,
        last_message_preview=None,
    )


@router.get("/sessions", response_model=list[ChatSessionSummary])
async def list_sessions(
    db: DbSession,
    session_status: str = Query(default="active", alias="status", pattern="^(active|archived)$"),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[ChatSessionSummary]:
    rows = (
        await db.execute(
            select(ChatSession)
            .where(ChatSession.status == session_status)
            .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return [await _session_summary(row, db) for row in rows]


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
async def get_session(session_id: uuid.UUID, db: DbSession) -> ChatSessionDetail:
    row = await db.get(ChatSession, session_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    summary = await _session_summary(row, db)
    messages_rows = (
        await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at, ChatMessage.id)
        )
    ).scalars().all()
    return ChatSessionDetail(**summary.model_dump(), messages=[_message_out(m) for m in messages_rows])


@router.post("/sessions/{session_id}/messages", response_model=SendMessageResponse)
async def send_message(  # noqa: C901
    session_id: uuid.UUID,
    payload: SendMessageRequest,
    request: Request,
    db: DbSession,
) -> SendMessageResponse:
    from app.config import settings

    row = await db.get(ChatSession, session_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    if row.status == "archived":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot append messages to an archived session.",
        )

    embedder = getattr(request.app.state, "embedder", None)
    if embedder is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedder not initialised.",
        )

    memory_graph = getattr(request.app.state, "memory_graph", None)
    if memory_graph is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Session memory not initialised.",
        )

    logger.info(
        "chat_session.message_start",
        extra={"session_id": str(session_id)},
    )

    from app.intelligence.session_memory import invoke_with_memory

    try:
        result = await invoke_with_memory(
            memory_graph=memory_graph,
            thread_id=session_id,
            user_message=payload.content,
            model=settings.t2_model,
            top_k=payload.top_k,
        )
    except LLMError as exc:
        logger.error("chat_session.message_failed", extra={"session_id": str(session_id)})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Chat failed: {exc}",
        ) from exc
    except Exception as exc:
        logger.error(
            "chat_session.message_failed",
            extra={"session_id": str(session_id)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Chat failed: {exc}",
        ) from exc

    if result.get("error"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Chat failed: {result['error']}",
        )

    now = datetime.now(timezone.utc)

    # Derive title from first user message if session has none
    if row.title is None:
        row.title = _derive_title(payload.content)

    # Persist user message
    user_msg = ChatMessage(
        session_id=session_id,
        role="user",
        content=payload.content,
        created_at=now,
    )
    db.add(user_msg)
    await db.flush()

    # Persist assistant message
    tokens = int(result.get("tokens_used") or 0)
    citations_raw = result.get("citations", []) or []
    assistant_msg = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=result.get("answer", ""),
        run_id=result.get("run_id"),
        citations_json=[c if isinstance(c, dict) else c.model_dump() for c in citations_raw],
        retrieved_context_count=len(result.get("context_blocks") or []),
        tokens_used=tokens,
        cost_estimate_usd=round(tokens * _COST_PER_TOKEN_USD, 6),
    )
    db.add(assistant_msg)

    # Update session timestamp
    row.updated_at = now
    await db.commit()
    await db.refresh(user_msg)
    await db.refresh(assistant_msg)
    await db.refresh(row)

    logger.info(
        "chat_session.message_done",
        extra={"session_id": str(session_id), "run_id": str(result.get("run_id"))},
    )

    summary = await _session_summary(row, db)
    return SendMessageResponse(
        session=summary,
        user_message=_message_out(user_msg),
        assistant_message=_message_out(assistant_msg),
    )


@router.patch("/sessions/{session_id}", response_model=ChatSessionSummary)
async def patch_session(
    session_id: uuid.UUID, payload: PatchSessionRequest, db: DbSession
) -> ChatSessionSummary:
    row = await db.get(ChatSession, session_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    if payload.title is not None:
        row.title = payload.title
    if payload.status is not None and payload.status != row.status:
        row.status = payload.status
        if payload.status == "archived":
            row.archived_at = datetime.now(timezone.utc)
        else:
            row.archived_at = None
    row.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(row)
    return await _session_summary(row, db)
