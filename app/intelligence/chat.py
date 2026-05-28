from __future__ import annotations

import uuid
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import Claim, ClaimEvidence, Document, Span
from app.intelligence.llm_client import LLMNetworkError
from app.intelligence.prompts.chat_answer import SYSTEM_PROMPT, build_user_prompt
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


def make_chat_graph(session_factory: async_sessionmaker, client: Any, embedder: Any):  # noqa: C901
    async def retrieve_spans(state: ChatState) -> dict:
        """Hybrid retrieval over span and claim embeddings (S5).

        Strategy:
          1. Query top-K spans by Span.embedding cosine similarity.
          2. Query top-K claims by Claim.claim_embedding cosine similarity; map
             each claim back to its supporting span via ClaimEvidence.
          3. Merge by span_id, keep max(span_score, claim_score).
          4. Sort by the merged score, take top-K.

        If no claim has an embedding (S5 not yet populated), step 2 is a no-op
        and behavior collapses to the prior span-only path.
        """
        async with session_factory() as session:
            sentinel = await session.scalar(select(Span).where(Span.embedding.isnot(None)).limit(1))
            if sentinel is None:
                return {"context_blocks": []}

            query_vec = embedder.embed_one(state["question"])
            top_k = state["top_k"]

            # --- Span-side retrieval ---
            span_distance = Span.embedding.cosine_distance(query_vec)
            span_rows = (
                await session.execute(
                    select(
                        Span.id,
                        Span.document_id,
                        Span.text,
                        (1 - span_distance).label("score"),
                        Document.title.label("title"),
                        Document.url.label("url"),
                    )
                    .join(Document, Span.document_id == Document.id)
                    .where(Span.embedding.isnot(None))
                    .order_by(span_distance, Document.id, Span.span_index, Span.id)
                    .limit(top_k)
                )
            ).all()

            # --- Claim-side retrieval (S5) ---
            # Resolve each top claim back to its supporting span. A claim may
            # appear via multiple ClaimEvidence rows; take the best span score
            # per claim, but we'll merge on span_id below.
            claim_rows: list = []
            claim_sentinel = await session.scalar(
                select(Claim).where(Claim.claim_embedding.isnot(None)).limit(1)
            )
            if claim_sentinel is not None:
                claim_distance = Claim.claim_embedding.cosine_distance(query_vec)
                claim_rows = (
                    await session.execute(
                        select(
                            Span.id.label("span_id"),
                            Span.document_id,
                            Span.text,
                            (1 - claim_distance).label("score"),
                            Document.title.label("title"),
                            Document.url.label("url"),
                        )
                        .join(ClaimEvidence, ClaimEvidence.claim_id == Claim.id)
                        .join(Span, ClaimEvidence.span_id == Span.id)
                        .join(Document, Span.document_id == Document.id)
                        .where(Claim.claim_embedding.isnot(None))
                        .where(Claim.status == "active")
                        .order_by(claim_distance)
                        .limit(top_k)
                    )
                ).all()

        # --- Merge by span_id, keeping max score ---
        merged: dict[uuid.UUID, dict[str, Any]] = {}
        for row in span_rows:
            merged[row.id] = {
                "span_id": row.id,
                "document_id": row.document_id,
                "document_title": row.title,
                "url": row.url,
                "text": row.text,
                "score": float(row.score),
            }
        for row in claim_rows:
            existing = merged.get(row.span_id)
            score = float(row.score)
            if existing is None:
                merged[row.span_id] = {
                    "span_id": row.span_id,
                    "document_id": row.document_id,
                    "document_title": row.title,
                    "url": row.url,
                    "text": row.text,
                    "score": score,
                }
            elif score > existing["score"]:
                existing["score"] = score

        # Rank by the merged score and label.
        ranked = sorted(merged.values(), key=lambda b: b["score"], reverse=True)[:top_k]
        blocks = [{**b, "label": f"C{i}", "claims": []} for i, b in enumerate(ranked, start=1)]
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
