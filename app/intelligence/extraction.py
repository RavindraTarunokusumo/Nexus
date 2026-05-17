"""LangGraph extraction graph for per-span concurrent claim extraction."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import Claim, ClaimEvidence, Document, Span
from app.intelligence.llm_client import (
    ExtractionOutput,
    LLMNetworkError,
    LLMSchemaError,
)
from app.intelligence.prompts.extract_claims import (
    SYSTEM_PROMPT,
    build_correction_prompt,
    build_user_prompt,
)

_MAX_RETRIES = 2


class ExtractionState(TypedDict):
    document_id: uuid.UUID
    model: str
    spans: list[dict]
    results: list[dict]  # {span_id, claims, tokens, error}
    total_tokens: int
    error: str | None


async def _extract_one_span(span: dict, client: Any, model: str) -> dict:
    """Extract claims from one span with correction-prompt retry (max _MAX_RETRIES)."""
    user = build_user_prompt(span["text"], span.get("metadata_json") or {})
    total_tokens = 0

    for attempt in range(_MAX_RETRIES + 1):
        try:
            result, tokens = await client.complete_json(
                model=model,
                system=SYSTEM_PROMPT,
                user=user,
                response_model=ExtractionOutput,
            )
            total_tokens += tokens
            return {
                "span_id": span["id"],
                "claims": [c.model_dump() for c in result.claims],
                "tokens": total_tokens,
                "error": None,
            }
        except LLMNetworkError:
            raise  # abort the entire graph
        except LLMSchemaError as exc:
            if attempt < _MAX_RETRIES:
                user = build_correction_prompt(user, "", str(exc))
                continue
            return {
                "span_id": span["id"],
                "claims": [],
                "tokens": total_tokens,
                "error": str(exc),
            }

    return {"span_id": span["id"], "claims": [], "tokens": 0, "error": "max retries exceeded"}


def make_extraction_graph(session_factory: async_sessionmaker, client: Any):  # noqa: C901
    """Build and compile the LangGraph extraction graph bound to session_factory and client.

    Cyclomatic complexity is C90-flagged because the factory defines four nested node
    functions; each is simple individually but the count aggregates in the outer scope.
    Keeping them nested preserves the closure over `session_factory` and `client`.
    """

    async def load_spans(state: ExtractionState) -> dict:
        async with session_factory() as session:
            doc = await session.get(Document, state["document_id"])
            if doc is None:
                return {"error": f"Document {state['document_id']} not found"}
            if doc.status != "embedded":
                return {"error": f"Document status is '{doc.status}'; must be 'embedded'"}
            rows = (
                (
                    await session.execute(
                        select(Span)
                        .where(Span.document_id == state["document_id"])
                        .order_by(Span.span_index)
                    )
                )
                .scalars()
                .all()
            )
            spans = [
                {
                    "id": str(s.id),
                    "text": s.text,
                    "token_count": s.token_count,
                    "metadata_json": s.metadata_json,
                }
                for s in rows
            ]
        return {"spans": spans}

    async def extract_spans(state: ExtractionState) -> dict:
        if state.get("error"):
            return {}

        semaphore = asyncio.Semaphore(5)

        async def bounded(span: dict) -> dict:
            async with semaphore:
                return await _extract_one_span(span, client, state["model"])

        try:
            results = list(await asyncio.gather(*[bounded(s) for s in state["spans"]]))
        except LLMNetworkError as exc:
            return {"error": str(exc), "results": []}

        total = sum(r.get("tokens", 0) for r in results)
        return {"results": results, "total_tokens": total}

    async def store_claims(state: ExtractionState) -> dict:
        async with session_factory() as session:
            for result in state.get("results", []):
                if result.get("error"):
                    continue
                for claim_data in result.get("claims", []):
                    claim = Claim(
                        document_id=state["document_id"],
                        claim_text=claim_data["claim_text"],
                        claim_type=claim_data["claim_type"],
                        entities_json=claim_data.get("entities"),
                        topics_json=claim_data.get("topics"),
                        confidence=claim_data.get("confidence"),
                        status="active",
                    )
                    session.add(claim)
                    await session.flush()
                    session.add(
                        ClaimEvidence(
                            claim_id=claim.id,
                            span_id=uuid.UUID(result["span_id"]),
                            evidence_role="support",
                            confidence=claim_data.get("confidence"),
                        )
                    )
            await session.commit()
        return {}

    async def update_status(state: ExtractionState) -> dict:
        if state.get("error"):
            new_status = "extraction_failed"
        else:
            results = state.get("results", [])
            if not results:
                new_status = "extraction_failed"
            else:
                failed = sum(1 for r in results if r.get("error"))
                if failed == 0:
                    new_status = "claims_extracted"
                elif failed < len(results):
                    new_status = "extraction_partial"
                else:
                    new_status = "extraction_failed"

        async with session_factory() as session:
            doc = await session.get(Document, state["document_id"])
            if doc:
                doc.status = new_status
                await session.commit()
        return {}

    def _route_after_extract(state: ExtractionState) -> str:
        return "update_status" if state.get("error") else "store_claims"

    builder = StateGraph(ExtractionState)
    builder.add_node("load_spans", load_spans)
    builder.add_node("extract_spans", extract_spans)
    builder.add_node("store_claims", store_claims)
    builder.add_node("update_status", update_status)

    builder.set_entry_point("load_spans")
    builder.add_edge("load_spans", "extract_spans")
    builder.add_conditional_edges(
        "extract_spans",
        _route_after_extract,
        {"store_claims": "store_claims", "update_status": "update_status"},
    )
    builder.add_edge("store_claims", "update_status")
    builder.add_edge("update_status", END)

    return builder.compile()
