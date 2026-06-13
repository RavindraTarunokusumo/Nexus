from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import Claim, ClaimEvidence, Document, Span
from app.intelligence.llm_client import LLMNetworkError
from app.intelligence.prompts.chat_answer import SYSTEM_PROMPT, build_user_prompt
from app.intelligence.prompts.classify_intent import (
    SYSTEM_PROMPT as _INTENT_SYSTEM_PROMPT,
)
from app.intelligence.prompts.classify_intent import (
    IntentClassification,
    build_classify_prompt,
)
from app.observability.run_context import chat_run


class ChatAnswerOutput(BaseModel):
    answer: str
    citations: list[str]


class ChatCitation(BaseModel):
    document_id: uuid.UUID
    span_id: uuid.UUID
    document_title: str | None
    url: str | None
    score: float
    claim_ids: list[uuid.UUID]


class ChatState(TypedDict):
    question: str
    top_k: int
    model: str
    run_id: uuid.UUID | None
    context_blocks: list[dict[str, Any]]
    answer: str
    citation_labels: list[str]
    citations: list[dict[str, Any]]
    tokens_used: int
    error: str | None


INSUFFICIENT_EVIDENCE_ANSWER = (
    "I do not have enough evidence to answer that from the current corpus."
)


def _normalize_citation_label(label: str) -> str:
    return label.strip().removeprefix("[").removesuffix("]").strip()


_PRIORITY_SCORES = [1.0, 0.5, 0.25, 0.1]


def compute_hybrid_score(
    candidate: dict,
    weights: dict[str, float],
    retrieval_priorities: list[str],
    recency_min: datetime,
    recency_max: datetime,
) -> float:
    """Telos-aware hybrid score. relation_relevance and evidence_quality are stubbed at 0."""
    # semantic_similarity
    sem = candidate["semantic_sim"] * weights.get("semantic_similarity", 0.0)

    # domain_object_type_match — boost by position in retrieval_priorities
    if not retrieval_priorities:
        dom_score = 0.5
    else:
        family = candidate["object_family"]
        try:
            rank = retrieval_priorities.index(family)
            dom_score = _PRIORITY_SCORES[rank] if rank < len(_PRIORITY_SCORES) else 0.1
        except ValueError:
            dom_score = 0.0
    dom = dom_score * weights.get("domain_object_type_match", 0.0)

    # source_authority — stubbed uniformly at 0.5 (no authority field yet)
    auth = 0.5 * weights.get("source_authority", 0.0)

    # recency — min-max normalize created_at over candidate set
    created_at = candidate["created_at"]
    if recency_min == recency_max:
        rec_score = 0.5
    else:
        span = (recency_max - recency_min).total_seconds()
        rec_score = (created_at - recency_min).total_seconds() / span
        rec_score = max(0.0, min(1.0, rec_score))
    rec = rec_score * weights.get("recency", 0.0)

    # salience — direct field
    sal = candidate["salience"] * weights.get("salience", 0.0)

    # relation_relevance (0.07) and evidence_quality (0.03) — stubbed at 0.0
    return sem + dom + auth + rec + sal


async def _run_classify_intent(state: dict, client: Any) -> dict:
    pack = state.get("pack")
    if pack is None:
        return {"query_intent": "general"}
    intent_names = list(pack.retrieval_policy.query_intents.keys())
    if not intent_names:
        return {"query_intent": "general"}
    try:
        result, _ = await client.complete_json(
            model=state["model"],
            system=_INTENT_SYSTEM_PROMPT,
            user=build_classify_prompt(state["question"], intent_names),
            response_model=IntentClassification,
            run_type="chat_classify_intent",
        )
        intent = result.intent if result.intent in intent_names else "general"
    except LLMNetworkError:
        intent = "general"
    return {"query_intent": intent}


def make_chat_graph(session_factory: async_sessionmaker, client: Any, embedder: Any):  # noqa: C901
    async def retrieve_spans(state: ChatState) -> dict:
        async with session_factory() as session:
            sentinel = await session.scalar(select(Span).where(Span.embedding.isnot(None)).limit(1))
            if sentinel is None:
                return {"context_blocks": []}

            query_vec = embedder.embed_one(state["question"])
            distance = Span.embedding.cosine_distance(query_vec)
            rows = (
                await session.execute(
                    select(
                        Span.id,
                        Span.document_id,
                        Span.text,
                        (1 - distance).label("score"),
                        Document.title.label("title"),
                        Document.url.label("url"),
                    )
                    .join(Document, Span.document_id == Document.id)
                    .where(Span.embedding.isnot(None))
                    .order_by(distance, Document.id, Span.span_index, Span.id)
                    .limit(state["top_k"])
                )
            ).all()

        blocks = [
            {
                "label": f"C{index}",
                "document_id": row.document_id,
                "span_id": row.id,
                "document_title": row.title,
                "url": row.url,
                "score": float(row.score),
                "text": row.text,
                "claims": [],
            }
            for index, row in enumerate(rows, start=1)
        ]
        return {"context_blocks": blocks}

    async def load_claims(state: ChatState) -> dict:
        blocks = state.get("context_blocks", [])
        if not blocks:
            return {}

        span_ids = [block["span_id"] for block in blocks]
        async with session_factory() as session:
            rows = (
                await session.execute(
                    select(
                        ClaimEvidence.span_id,
                        Claim.id,
                        Claim.claim_text,
                    )
                    .join(Claim, ClaimEvidence.claim_id == Claim.id)
                    .where(ClaimEvidence.span_id.in_(span_ids))
                    .where(Claim.status == "active")
                    .order_by(Claim.created_at, Claim.id)
                )
            ).all()

        claims_by_span: dict[uuid.UUID, list[dict[str, Any]]] = {
            span_id: [] for span_id in span_ids
        }
        for row in rows:
            claims_by_span[row.span_id].append({"claim_id": row.id, "claim_text": row.claim_text})

        hydrated_blocks = [
            {
                **block,
                "claims": claims_by_span.get(block["span_id"], []),
            }
            for block in blocks
        ]
        return {"context_blocks": hydrated_blocks}

    async def generate_answer(state: ChatState) -> dict:
        if not state.get("context_blocks"):
            return {"answer": INSUFFICIENT_EVIDENCE_ANSWER, "citation_labels": [], "tokens_used": 0}

        user = build_user_prompt(state["question"], state["context_blocks"])
        try:
            result, tokens = await client.complete_json(
                model=state["model"],
                system=SYSTEM_PROMPT,
                user=user,
                response_model=ChatAnswerOutput,
                run_type="chat_answer",
            )
        except LLMNetworkError as exc:
            return {"error": str(exc), "tokens_used": 0}

        return {
            "answer": result.answer,
            "citation_labels": result.citations,
            "tokens_used": tokens,
        }

    async def format_result(state: ChatState) -> dict:
        blocks_by_label = {block["label"]: block for block in state.get("context_blocks", [])}
        citations: list[dict[str, Any]] = []

        citation_labels = [
            _normalize_citation_label(label) for label in state.get("citation_labels", [])
        ]
        citation_labels = list(dict.fromkeys(citation_labels))
        for label in citation_labels:
            block = blocks_by_label.get(label)
            if block is None:
                continue
            citation = ChatCitation(
                document_id=block["document_id"],
                span_id=block["span_id"],
                document_title=block.get("document_title"),
                url=block.get("url"),
                score=block["score"],
                claim_ids=[claim["claim_id"] for claim in block.get("claims", [])],
            )
            citations.append(citation.model_dump())

        if state.get("context_blocks") and not citations:
            return {"answer": INSUFFICIENT_EVIDENCE_ANSWER, "citations": []}

        answer = state.get("answer") or INSUFFICIENT_EVIDENCE_ANSWER
        return {"answer": answer, "citations": citations}

    def route_after_load_claims(state: ChatState) -> str:
        if state.get("context_blocks"):
            return "generate_answer"
        return "format_result"

    builder = StateGraph(ChatState)
    builder.add_node("retrieve_spans", retrieve_spans)
    builder.add_node("load_claims", load_claims)
    builder.add_node("generate_answer", generate_answer)
    builder.add_node("format_result", format_result)

    builder.set_entry_point("retrieve_spans")
    builder.add_edge("retrieve_spans", "load_claims")
    builder.add_conditional_edges(
        "load_claims",
        route_after_load_claims,
        {"generate_answer": "generate_answer", "format_result": "format_result"},
    )
    builder.add_edge("generate_answer", "format_result")
    builder.add_edge("format_result", END)

    return builder.compile()


async def run_chat_with_context(graph, question: str, model: str, *, top_k: int) -> dict:
    async with chat_run() as run_id:
        final = await graph.ainvoke(
            {
                "question": question,
                "top_k": top_k,
                "model": model,
                "run_id": run_id,
                "context_blocks": [],
                "answer": "",
                "citation_labels": [],
                "citations": [],
                "tokens_used": 0,
                "error": None,
            }
        )
    final["run_id"] = run_id
    return final
