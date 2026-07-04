from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select

from app.db.models import ChatMessage, ChatSession
from app.intelligence.chat import ChatCitation, make_chat_graph, run_chat_with_context
from app.intelligence.llm_client import _COST_PER_TOKEN_USD, LLMClient, LLMError
from app.intelligence.session_memory import _derive_title, run_session_turn

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

_MAX_TITLE_LEN = 120


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _get_session_or_404(session_factory, session_id: uuid.UUID) -> ChatSession:
    async with session_factory() as db:
        row = await db.get(ChatSession, session_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    return row


# ---------------------------------------------------------------------------
# Pydantic schemas — single-turn (unchanged)
# ---------------------------------------------------------------------------


class ChatAnswerRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2048)
    top_k: int = Field(default=8, ge=1, le=20)

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question must not be blank.")
        return value


class ChatAnswerResponse(BaseModel):
    answer: str
    citations: list[ChatCitation]
    retrieved_context_count: int
    run_id: uuid.UUID
    tokens_used: int
    cost_estimate_usd: float
    question_shape: str = "general"
    query_intent: str = "general"


# ---------------------------------------------------------------------------
# Pydantic schemas — sessions
# ---------------------------------------------------------------------------


class SessionCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=_MAX_TITLE_LEN)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Title must not be blank.")
        return v


class SessionSummary(BaseModel):
    id: uuid.UUID
    title: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    message_count: int
    last_message_preview: str | None


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime
    run_id: uuid.UUID | None = None
    citations: list[dict] | None = None
    retrieved_context_count: int | None = None
    tokens_used: int | None = None
    cost_estimate_usd: float | None = None
    question_shape: str | None = None
    query_intent: str | None = None


class SessionDetail(SessionSummary):
    messages: list[MessageOut]


class SessionPatchRequest(BaseModel):
    title: str | None = Field(default=None, max_length=_MAX_TITLE_LEN)
    status: str | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Title must not be blank.")
        return v

    @field_validator("status")
    @classmethod
    def status_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in ("active", "archived"):
            raise ValueError("status must be 'active' or 'archived'.")
        return v


class MessageCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2048)
    top_k: int = Field(default=8, ge=1, le=20)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Content must not be blank.")
        return v


class SendMessageResponse(BaseModel):
    session: SessionSummary
    user_message: MessageOut
    assistant_message: MessageOut


# ---------------------------------------------------------------------------
# Helper: build SessionSummary from a ChatSession ORM row
# ---------------------------------------------------------------------------


async def _build_session_summary(session: ChatSession, db_session_factory) -> SessionSummary:
    async with db_session_factory() as db:
        count_result = await db.execute(
            select(func.count()).where(ChatMessage.session_id == session.id)
        )
        message_count = count_result.scalar_one()

        preview_result = await db.execute(
            select(ChatMessage.content)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(1)
        )
        raw_preview = preview_result.scalar_one_or_none()
        last_preview_row = raw_preview[:150] if raw_preview else None

    return SessionSummary(
        id=session.id,
        title=session.title,
        status=session.status,
        created_at=session.created_at,
        updated_at=session.updated_at,
        archived_at=session.archived_at,
        message_count=message_count,
        last_message_preview=last_preview_row,
    )


# ---------------------------------------------------------------------------
# Single-turn endpoint (unchanged)
# ---------------------------------------------------------------------------


@router.post("/chat/answer", response_model=ChatAnswerResponse)
async def answer_chat(payload: ChatAnswerRequest, request: Request) -> ChatAnswerResponse:
    from app.config import settings

    embedder = getattr(request.app.state, "embedder", None)
    if embedder is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedder not initialised.",
        )

    client = LLMClient(
        settings.llm_api_key, request.app.state.session_factory, base_url=settings.llm_base_url
    )
    graph = make_chat_graph(request.app.state.session_factory, client, embedder)
    try:
        final = await run_chat_with_context(
            graph,
            payload.question,
            settings.t2_model,
            top_k=payload.top_k,
        )
    except LLMError as exc:
        logger.error("answer_chat.llm_error error=%s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat answer failed. Please try again later.",
        ) from exc

    if final.get("error"):
        logger.error("answer_chat.graph_error error=%s", final["error"])
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat answer failed. Please try again later.",
        )

    tokens = int(final.get("tokens_used") or 0)
    return ChatAnswerResponse(
        answer=final["answer"],
        citations=[ChatCitation.model_validate(c) for c in final.get("citations", [])],
        retrieved_context_count=len(final.get("context_blocks") or []),
        run_id=final["run_id"],
        tokens_used=tokens,
        cost_estimate_usd=round(tokens * _COST_PER_TOKEN_USD, 6),
        question_shape=final.get("question_shape") or "general",
        query_intent=final.get("query_intent") or "general",
    )


# ---------------------------------------------------------------------------
# Session endpoints
# ---------------------------------------------------------------------------


@router.post("/chat/sessions", status_code=status.HTTP_201_CREATED, response_model=SessionSummary)
async def create_session(payload: SessionCreateRequest, request: Request) -> SessionSummary:
    session = ChatSession(title=payload.title)
    async with request.app.state.session_factory() as db:
        db.add(session)
        await db.commit()
        await db.refresh(session)
    return SessionSummary(
        id=session.id,
        title=session.title,
        status=session.status,
        created_at=session.created_at,
        updated_at=session.updated_at,
        archived_at=session.archived_at,
        message_count=0,
        last_message_preview=None,
    )


@router.get("/chat/sessions", response_model=list[SessionSummary])
async def list_sessions(
    request: Request,
    status_filter: str = Query(default="active", alias="status", pattern="^(active|archived)$"),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[SessionSummary]:
    count_sq = (
        select(func.count())
        .where(ChatMessage.session_id == ChatSession.id)
        .correlate(ChatSession)
        .scalar_subquery()
    )
    preview_sq = (
        select(ChatMessage.content)
        .where(ChatMessage.session_id == ChatSession.id)
        .correlate(ChatSession)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    stmt = (
        select(
            ChatSession,
            count_sq.label("message_count"),
            preview_sq.label("last_preview"),
        )
        .where(ChatSession.status == status_filter)
        .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
        .limit(limit)
        .offset(offset)
    )
    async with request.app.state.session_factory() as db:
        rows = (await db.execute(stmt)).all()

    return [
        SessionSummary(
            id=row.ChatSession.id,
            title=row.ChatSession.title,
            status=row.ChatSession.status,
            created_at=row.ChatSession.created_at,
            updated_at=row.ChatSession.updated_at,
            archived_at=row.ChatSession.archived_at,
            message_count=row.message_count,
            last_message_preview=row.last_preview[:150] if row.last_preview else None,
        )
        for row in rows
    ]


@router.get("/chat/sessions/{session_id}", response_model=SessionDetail)
async def get_session(session_id: uuid.UUID, request: Request) -> SessionDetail:
    session = await _get_session_or_404(request.app.state.session_factory, session_id)

    async with request.app.state.session_factory() as db:
        msg_rows = (
            (
                await db.execute(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == session_id)
                    .order_by(ChatMessage.created_at, ChatMessage.id)
                )
            )
            .scalars()
            .all()
        )

    messages = [
        MessageOut(
            id=m.id,
            role=m.role,
            content=m.content,
            created_at=m.created_at,
            run_id=m.run_id,
            citations=m.citations_json,
            retrieved_context_count=m.retrieved_context_count,
            tokens_used=m.tokens_used,
            cost_estimate_usd=m.cost_estimate_usd,
        )
        for m in msg_rows
    ]

    summary = await _build_session_summary(session, request.app.state.session_factory)
    return SessionDetail(**summary.model_dump(), messages=messages)


@router.patch("/chat/sessions/{session_id}", response_model=SessionSummary)
async def patch_session(
    session_id: uuid.UUID, payload: SessionPatchRequest, request: Request
) -> SessionSummary:
    async with request.app.state.session_factory() as db:
        session = await db.get(ChatSession, session_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
        if payload.title is not None:
            session.title = payload.title
        if payload.status is not None:
            session.status = payload.status
            if payload.status == "archived":
                session.archived_at = _utcnow()
            else:
                session.archived_at = None
        session.updated_at = _utcnow()
        await db.commit()
        await db.refresh(session)

    return await _build_session_summary(session, request.app.state.session_factory)


@router.post("/chat/sessions/{session_id}/messages", response_model=SendMessageResponse)
async def send_message(
    session_id: uuid.UUID, payload: MessageCreateRequest, request: Request
) -> SendMessageResponse:
    from app.config import settings

    embedder = getattr(request.app.state, "embedder", None)
    if embedder is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedder not initialised.",
        )

    session = await _get_session_or_404(request.app.state.session_factory, session_id)
    if session.status == "archived":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot send messages to an archived session.",
        )

    logger.info("session_message.start session_id=%s", session_id)

    try:
        result = await run_session_turn(
            session_id=session_id,
            question=payload.content,
            top_k=payload.top_k,
            model=settings.t2_model,
            db_url=settings.database_url,
            session_factory=request.app.state.session_factory,
            embedder=embedder,
        )
    except Exception as exc:
        logger.error("session_message.failed session_id=%s error=%s", session_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Session turn failed. Please try again later.",
        ) from exc

    if result.get("error"):
        logger.error(
            "session_message.graph_error session_id=%s error=%s", session_id, result["error"]
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat answer failed. Please try again later.",
        )

    tokens = int(result.get("tokens_used") or 0)
    cost = round(tokens * _COST_PER_TOKEN_USD, 6)
    now = _utcnow()

    async with request.app.state.session_factory() as db:
        # Reload inside transaction — re-check archived status to close the race
        # between the pre-flight check above and this write.
        session = await db.get(ChatSession, session_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
        if session.status == "archived":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot send messages to an archived session.",
            )

        user_msg = ChatMessage(
            session_id=session_id,
            role="user",
            content=payload.content,
            created_at=now,
        )
        db.add(user_msg)

        assistant_msg = ChatMessage(
            session_id=session_id,
            role="assistant",
            content=result.get("answer", ""),
            run_id=result.get("run_id"),
            citations_json=result.get("citations") or [],
            retrieved_context_count=result.get("retrieved_context_count"),
            prompt_tokens=result.get("prompt_tokens"),
            completion_tokens=result.get("completion_tokens"),
            tokens_used=tokens,
            cost_estimate_usd=cost,
        )
        db.add(assistant_msg)

        # Derive title from first user message if session has no title
        if session.title is None:
            session.title = _derive_title(payload.content)

        session.updated_at = _utcnow()
        await db.commit()
        await db.refresh(user_msg)
        await db.refresh(assistant_msg)
        await db.refresh(session)

    session_summary = await _build_session_summary(session, request.app.state.session_factory)

    return SendMessageResponse(
        session=session_summary,
        user_message=MessageOut(
            id=user_msg.id,
            role=user_msg.role,
            content=user_msg.content,
            created_at=user_msg.created_at,
        ),
        assistant_message=MessageOut(
            id=assistant_msg.id,
            role=assistant_msg.role,
            content=assistant_msg.content,
            created_at=assistant_msg.created_at,
            run_id=assistant_msg.run_id,
            citations=assistant_msg.citations_json,
            retrieved_context_count=assistant_msg.retrieved_context_count,
            tokens_used=assistant_msg.tokens_used,
            cost_estimate_usd=assistant_msg.cost_estimate_usd,
            question_shape=result.get("question_shape") or "general",
            query_intent=result.get("query_intent") or "general",
        ),
    )
