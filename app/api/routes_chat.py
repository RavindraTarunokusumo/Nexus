from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from app.intelligence.chat import ChatCitation, make_chat_graph, run_chat_with_context
from app.intelligence.llm_client import _COST_PER_TOKEN_USD, LLMClient, LLMError

router = APIRouter(tags=["chat"])


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


@router.post("/chat/answer", response_model=ChatAnswerResponse)
async def answer_chat(payload: ChatAnswerRequest, request: Request) -> ChatAnswerResponse:
    from app.config import settings

    embedder = getattr(request.app.state, "embedder", None)
    if embedder is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedder not initialised.",
        )

    client = LLMClient(settings.openrouter_api_key, request.app.state.session_factory)
    graph = make_chat_graph(request.app.state.session_factory, client, embedder)
    try:
        final = await run_chat_with_context(
            graph,
            payload.question,
            settings.t2_model,
            top_k=payload.top_k,
        )
    except LLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Chat answer failed: {exc}",
        ) from exc

    if final.get("error"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Chat answer failed: {final['error']}",
        )

    tokens = int(final.get("tokens_used") or 0)
    return ChatAnswerResponse(
        answer=final["answer"],
        citations=[ChatCitation.model_validate(c) for c in final.get("citations", [])],
        retrieved_context_count=len(final.get("context_blocks") or []),
        run_id=final["run_id"],
        tokens_used=tokens,
        cost_estimate_usd=round(tokens * _COST_PER_TOKEN_USD, 6),
    )
