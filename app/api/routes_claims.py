"""Claim extraction endpoint and claims listing."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import delete, select

from app.api.deps import DbSession
from app.db.models import Claim, Document
from app.intelligence.extraction import make_extraction_graph
from app.intelligence.llm_client import LLMClient

router = APIRouter(tags=["claims"])

_COST_PER_TOKEN_USD = 0.30 / 1_000_000


class ClaimResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    claim_text: str
    claim_type: str
    entities_json: list | None
    topics_json: list | None
    confidence: float | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ExtractionSummary(BaseModel):
    document_id: uuid.UUID
    claims_extracted: int
    spans_processed: int
    spans_failed: int
    tokens_used: int
    cost_estimate_usd: float
    claim_ids: list[uuid.UUID]


@router.post("/documents/{document_id}/extract-claims", response_model=ExtractionSummary)
async def extract_claims(
    document_id: uuid.UUID,
    request: Request,
    session: DbSession,
    force: bool = Query(default=False),
) -> ExtractionSummary:
    from app.config import settings

    doc = await session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    if doc.status not in (
        "embedded",
        "claims_extracted",
        "extraction_partial",
        "extraction_failed",
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Document status is '{doc.status}'; must be 'embedded' to extract claims.",
        )

    existing_claim_id = await session.scalar(
        select(Claim.id).where(Claim.document_id == document_id).limit(1)
    )
    if existing_claim_id is not None and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Claims already exist. Use ?force=true to re-extract.",
        )

    if existing_claim_id is not None and force:
        await session.execute(delete(Claim).where(Claim.document_id == document_id))
        doc.status = "embedded"
        await session.commit()

    llm_client = LLMClient(
        api_key=settings.openrouter_api_key,
        session_factory=request.app.state.session_factory,
    )
    graph = make_extraction_graph(request.app.state.session_factory, llm_client)

    final = await graph.ainvoke(
        {
            "document_id": document_id,
            "model": settings.openrouter_t2_model,
            "spans": [],
            "results": [],
            "total_tokens": 0,
            "error": None,
        }
    )

    if final.get("error"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Extraction failed: {final['error']}",
        )

    results = final.get("results", [])
    spans_failed = sum(1 for r in results if r.get("error"))

    claim_ids = list(
        await session.scalars(select(Claim.id).where(Claim.document_id == document_id))
    )
    total_tokens = final.get("total_tokens", 0)

    return ExtractionSummary(
        document_id=document_id,
        claims_extracted=len(claim_ids),
        spans_processed=len(results),
        spans_failed=spans_failed,
        tokens_used=total_tokens,
        cost_estimate_usd=round(total_tokens * _COST_PER_TOKEN_USD, 6),
        claim_ids=claim_ids,
    )


@router.get("/claims", response_model=list[ClaimResponse])
async def list_claims(
    session: DbSession,
    document_id: uuid.UUID | None = None,
    claim_type: str | None = None,
    claim_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[ClaimResponse]:
    if document_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="document_id query parameter is required.",
        )
    stmt = select(Claim).where(Claim.document_id == document_id)
    if claim_type is not None:
        stmt = stmt.where(Claim.claim_type == claim_type)
    if claim_status is not None:
        stmt = stmt.where(Claim.status == claim_status)
    stmt = stmt.order_by(Claim.created_at.desc()).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    return [ClaimResponse.model_validate(r) for r in rows]
