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
    LLMError,
    LLMNetworkError,
    LLMSchemaError,
)
from app.intelligence.prompts.extract_claims import (
    SYSTEM_PROMPT,
    build_correction_prompt,
    build_user_prompt,
)
from app.observability.run_context import extraction_run, span_scope
from app.observability.tracer import mark_document_timestamp, record_span_extraction

_MAX_RETRIES = 2

# Document status lifecycle constants (extends the ingestion statuses with the
# extraction outcomes; centralised here so routes_claims and tests can import them).
STATUS_EMBEDDED = "embedded"
STATUS_CLAIMS_EXTRACTED = "claims_extracted"
STATUS_EXTRACTION_PARTIAL = "extraction_partial"
STATUS_EXTRACTION_FAILED = "extraction_failed"

POST_EXTRACTION_STATUSES = (
    STATUS_EMBEDDED,
    STATUS_CLAIMS_EXTRACTED,
    STATUS_EXTRACTION_PARTIAL,
    STATUS_EXTRACTION_FAILED,
)


class ExtractionState(TypedDict):
    document_id: uuid.UUID
    run_id: uuid.UUID | None
    model: str
    spans: list[dict]
    results: list[dict]  # {span_id, claims, tokens, error}
    stored_claim_ids: list[uuid.UUID]
    total_tokens: int
    error: str | None


async def _extract_one_span(
    span: dict,
    client: Any,
    model: str,
    session_factory: async_sessionmaker,
    run_id: uuid.UUID,
    document_id: uuid.UUID,
) -> dict:
    """Extract claims from one span with correction-prompt retry (max _MAX_RETRIES).

    Binds span_id in run_context for the duration so all log lines and the
    agent_runs row carry the correct span correlation.
    """
    span_id = uuid.UUID(span["id"])
    user = build_user_prompt(span["text"], span.get("metadata_json") or {})
    total_tokens = 0
    attempts = 0

    async with span_scope(span_id):
        for attempt in range(_MAX_RETRIES + 1):
            attempts += 1
            try:
                result, tokens = await client.complete_json(
                    model=model,
                    system=SYSTEM_PROMPT,
                    user=user,
                    response_model=ExtractionOutput,
                )
                total_tokens += tokens
                await record_span_extraction(
                    session_factory,
                    run_id=run_id,
                    span_id=span_id,
                    document_id=document_id,
                    status="success",
                    attempts=attempts,
                )
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
                    user = build_correction_prompt(user, exc.raw_output, str(exc))
                    continue
                await record_span_extraction(
                    session_factory,
                    run_id=run_id,
                    span_id=span_id,
                    document_id=document_id,
                    status="schema_error",
                    attempts=attempts,
                    error=str(exc),
                )
                return {
                    "span_id": span["id"],
                    "claims": [],
                    "tokens": total_tokens,
                    "error": str(exc),
                }
            except LLMError as exc:
                await record_span_extraction(
                    session_factory,
                    run_id=run_id,
                    span_id=span_id,
                    document_id=document_id,
                    status="llm_error",
                    attempts=attempts,
                    error=str(exc),
                )
                return {
                    "span_id": span["id"],
                    "claims": [],
                    "tokens": total_tokens,
                    "error": str(exc),
                }

    # Unreachable: the loop returns from every branch above. Kept for type-checker comfort.
    return {"span_id": span["id"], "claims": [], "tokens": total_tokens, "error": "unreachable"}


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
                return {"error": f"Document {state['document_id']} not found", "run_id": None}
            if doc.status != STATUS_EMBEDDED:
                return {
                    "error": f"Document status is '{doc.status}'; must be 'embedded'",
                    "run_id": None,
                }
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

        await mark_document_timestamp(
            session_factory, state["document_id"], "extraction_started_at"
        )
        return {"spans": spans}

    async def extract_spans(state: ExtractionState) -> dict:
        if state.get("error"):
            return {}

        run_id = state.get("run_id")
        semaphore = asyncio.Semaphore(5)

        async def bounded(span: dict) -> dict:
            async with semaphore:
                return await _extract_one_span(
                    span,
                    client,
                    state["model"],
                    session_factory,
                    run_id=run_id,
                    document_id=state["document_id"],
                )

        try:
            results = list(await asyncio.gather(*[bounded(s) for s in state["spans"]]))
        except LLMNetworkError as exc:
            return {"error": str(exc), "results": []}

        total = sum(r.get("tokens", 0) for r in results)
        return {"results": results, "total_tokens": total}

    async def store_claims(state: ExtractionState) -> dict:
        async with session_factory() as session:
            claims_to_add: list[Claim] = []
            evidence_to_add: list[ClaimEvidence] = []
            stored_ids: list[uuid.UUID] = []

            for result in state.get("results", []):
                if result.get("error"):
                    continue
                span_id = uuid.UUID(result["span_id"])
                for claim_data in result.get("claims", []):
                    # Pre-assign UUIDs so we can build ClaimEvidence rows without
                    # an extra flush per claim.
                    claim_id = uuid.uuid4()
                    claims_to_add.append(
                        Claim(
                            id=claim_id,
                            document_id=state["document_id"],
                            claim_text=claim_data["claim_text"],
                            claim_type=claim_data["claim_type"],
                            entities_json=claim_data.get("entities"),
                            topics_json=claim_data.get("topics"),
                            confidence=claim_data.get("confidence"),
                            status="active",
                        )
                    )
                    evidence_to_add.append(
                        ClaimEvidence(
                            claim_id=claim_id,
                            span_id=span_id,
                            evidence_role="support",
                            confidence=claim_data.get("confidence"),
                        )
                    )
                    stored_ids.append(claim_id)

            if claims_to_add:
                session.add_all(claims_to_add)
                session.add_all(evidence_to_add)
                await session.commit()
        return {"stored_claim_ids": stored_ids}

    async def update_status(state: ExtractionState) -> dict:
        if state.get("error"):
            new_status = STATUS_EXTRACTION_FAILED
        else:
            results = state.get("results", [])
            if not results:
                new_status = STATUS_EXTRACTION_FAILED
            else:
                failed = sum(1 for r in results if r.get("error"))
                if failed == 0:
                    new_status = STATUS_CLAIMS_EXTRACTED
                elif failed < len(results):
                    new_status = STATUS_EXTRACTION_PARTIAL
                else:
                    new_status = STATUS_EXTRACTION_FAILED

        async with session_factory() as session:
            doc = await session.get(Document, state["document_id"])
            if doc:
                doc.status = new_status
                await session.commit()

        await mark_document_timestamp(
            session_factory, state["document_id"], "extraction_completed_at"
        )
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


async def run_with_context(graph, document_id: uuid.UUID, model: str) -> dict:
    """Enter extraction_run context, invoke the graph, return final state with run_id."""
    async with extraction_run(document_id) as run_id:
        final = await graph.ainvoke(
            {
                "document_id": document_id,
                "run_id": run_id,
                "model": model,
                "spans": [],
                "results": [],
                "stored_claim_ids": [],
                "total_tokens": 0,
                "error": None,
            }
        )
    final["run_id"] = run_id
    return final
