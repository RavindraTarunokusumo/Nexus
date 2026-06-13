from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import Document, SemanticCapsule
from app.domain_packs.loader import load_pack
from app.intelligence.llm_client import LLMError, LLMNetworkError
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
    capsule_id: uuid.UUID
    document_title: str | None
    url: str | None
    score: float
    object_type: str | None
    object_family: str | None
    lifecycle_state: str | None
    summary: str


class ChatState(TypedDict):
    question: str
    top_k: int
    model: str
    run_id: uuid.UUID | None
    query_intent: str
    pack: Any
    context_blocks: list[dict[str, Any]]
    answer: str
    citation_labels: list[str]
    citations: list[dict[str, Any]]
    tokens_used: int
    error: str | None


INSUFFICIENT_EVIDENCE_ANSWER = (
    "I do not have enough evidence to answer that from the current corpus."
)

_PRIORITY_SCORES = [1.0, 0.5, 0.25, 0.1]


def estimate_tokens(text: str) -> int:
    """Cheap char-based token estimate (~4 chars/token). Sufficient for a soft budget gate."""
    return (len(text) + 3) // 4


def _assemble_within_budget(
    scored: list[tuple[dict, float]],
    top_k: int,
    token_budget: int | None,
) -> list[tuple[dict, float]]:
    """Pick score-ordered blocks under a token budget; top_k caps the count.

    Always includes the highest-scored block even if it alone exceeds the budget.
    token_budget=None falls back to the flat top_k slice.
    """
    if token_budget is None:
        return scored[:top_k]
    selected: list[tuple[dict, float]] = []
    running = 0
    for cand, score in scored:
        if len(selected) >= top_k:
            break
        est = estimate_tokens(cand["text"])
        if selected and running + est > token_budget:
            break
        selected.append((cand, score))
        running += est
    return selected


def _normalize_citation_label(label: str) -> str:
    return label.strip().removeprefix("[").removesuffix("]").strip()


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
    except LLMError:
        intent = "general"
    return {"query_intent": intent}


async def _run_retrieve_capsules(
    state: dict,
    session_factory: async_sessionmaker,
    embedder: Any,
) -> dict:
    async with session_factory() as session:
        sentinel = await session.scalar(
            select(SemanticCapsule).where(SemanticCapsule.embedding.isnot(None)).limit(1)
        )
        if sentinel is None:
            return {"context_blocks": []}

        query_vec = embedder.embed_one(state["question"])
        distance = SemanticCapsule.embedding.cosine_distance(query_vec)
        fetch_k = state["top_k"] * 3
        rows = (
            await session.execute(
                select(
                    SemanticCapsule.id,
                    SemanticCapsule.document_id,
                    SemanticCapsule.text,
                    SemanticCapsule.domain_object_type,
                    SemanticCapsule.object_family,
                    SemanticCapsule.lifecycle_state,
                    SemanticCapsule.salience,
                    SemanticCapsule.created_at,
                    (1 - distance).label("semantic_sim"),
                    Document.title.label("title"),
                    Document.url.label("url"),
                )
                .join(Document, SemanticCapsule.document_id == Document.id)
                .where(SemanticCapsule.embedding.isnot(None))
                .where(SemanticCapsule.lifecycle_state == "active")
                .order_by(distance)
                .limit(fetch_k)
            )
        ).all()

    pack = state.get("pack")
    query_intent = state.get("query_intent", "general")
    retrieval_priorities: list[str] = []
    if pack is not None and query_intent != "general":
        intent_cfg = pack.retrieval_policy.query_intents.get(query_intent, {})
        retrieval_priorities = intent_cfg.get("retrieval_priorities", [])

    weights: dict[str, float] = {}
    if pack is not None:
        weights = dict(pack.retrieval_policy.hybrid_score_weights)

    if rows:
        created_ats = [r.created_at for r in rows]
        recency_min: datetime = min(created_ats)
        recency_max: datetime = max(created_ats)
    else:
        now = datetime.now(timezone.utc)
        recency_min = recency_max = now

    candidates = [
        {
            "id": r.id,
            "document_id": r.document_id,
            "text": r.text,
            "object_type": r.domain_object_type,
            "object_family": r.object_family,
            "lifecycle_state": r.lifecycle_state,
            "salience": r.salience,
            "created_at": r.created_at,
            "semantic_sim": float(r.semantic_sim),
            "title": r.title,
            "url": r.url,
        }
        for r in rows
    ]

    scored = sorted(
        [
            (c, compute_hybrid_score(c, weights, retrieval_priorities, recency_min, recency_max))
            for c in candidates
        ],
        key=lambda x: x[1],
        reverse=True,
    )
    token_budget: int | None = None
    if pack is not None:
        token_budget = pack.context_assembly.max_tokens_by_tier.get("T2")
    top = _assemble_within_budget(scored, state["top_k"], token_budget)

    blocks = [
        {
            "label": f"C{i}",
            "document_id": c["document_id"],
            "capsule_id": c["id"],
            "document_title": c["title"],
            "url": c["url"],
            "score": score,
            "text": c["text"],
            "object_type": c["object_type"],
            "object_family": c["object_family"],
            "lifecycle_state": c["lifecycle_state"],
        }
        for i, (c, score) in enumerate(top, start=1)
    ]
    return {"context_blocks": blocks}


def make_chat_graph(session_factory: async_sessionmaker, client: Any, embedder: Any):
    async def classify_intent(state: ChatState) -> dict:
        return await _run_classify_intent(state, client)

    async def retrieve_capsules(state: ChatState) -> dict:
        return await _run_retrieve_capsules(state, session_factory, embedder)

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
        return {"answer": result.answer, "citation_labels": result.citations, "tokens_used": tokens}

    async def format_result(state: ChatState) -> dict:
        blocks_by_label = {block["label"]: block for block in state.get("context_blocks", [])}
        citation_labels = list(
            dict.fromkeys(
                _normalize_citation_label(lbl) for lbl in state.get("citation_labels", [])
            )
        )
        citations: list[dict[str, Any]] = []
        for label in citation_labels:
            block = blocks_by_label.get(label)
            if block is None:
                continue
            citations.append(
                ChatCitation(
                    document_id=block["document_id"],
                    capsule_id=block["capsule_id"],
                    document_title=block.get("document_title"),
                    url=block.get("url"),
                    score=block["score"],
                    object_type=block.get("object_type"),
                    object_family=block.get("object_family"),
                    lifecycle_state=block.get("lifecycle_state"),
                    summary=block["text"],
                ).model_dump()
            )
        if state.get("context_blocks") and not citations:
            return {"answer": INSUFFICIENT_EVIDENCE_ANSWER, "citations": []}
        return {
            "answer": state.get("answer") or INSUFFICIENT_EVIDENCE_ANSWER,
            "citations": citations,
        }

    def route_after_retrieve(state: ChatState) -> str:
        return "generate_answer" if state.get("context_blocks") else "format_result"

    builder = StateGraph(ChatState)
    builder.add_node("classify_intent", classify_intent)
    builder.add_node("retrieve_capsules", retrieve_capsules)
    builder.add_node("generate_answer", generate_answer)
    builder.add_node("format_result", format_result)

    builder.set_entry_point("classify_intent")
    builder.add_edge("classify_intent", "retrieve_capsules")
    builder.add_conditional_edges(
        "retrieve_capsules",
        route_after_retrieve,
        {"generate_answer": "generate_answer", "format_result": "format_result"},
    )
    builder.add_edge("generate_answer", "format_result")
    builder.add_edge("format_result", END)

    return builder.compile()


async def run_chat_with_context(
    graph: Any,
    question: str,
    model: str,
    *,
    top_k: int,
    pack: Any = None,
) -> dict:
    if pack is None:
        from app.config import settings

        pack = load_pack(settings.default_pack_id)
    async with chat_run() as run_id:
        final = await graph.ainvoke(
            {
                "question": question,
                "top_k": top_k,
                "model": model,
                "run_id": run_id,
                "query_intent": "general",
                "pack": pack,
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
