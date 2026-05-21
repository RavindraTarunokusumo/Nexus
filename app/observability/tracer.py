"""Thin DB-writing helpers for pipeline audit — never raises, always logs on failure."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from app.db.models import AgentRun, Document, SpanExtraction
from app.observability.run_context import current_context

logger = logging.getLogger(__name__)

_TIMESTAMP_FIELDS = Literal[
    "chunked_at", "embedded_at", "extraction_started_at", "extraction_completed_at"
]


async def record_agent_run(
    session_factory,
    *,
    run_type: str,
    model: str,
    input_payload: dict,
    raw_output: str | None,
    total_tokens: int,
    status: str,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> None:
    """Insert one agent_runs row. Reads run_id/document_id/span_id from contextvars.
    Catches and logs DB errors; never raises."""
    ctx = current_context()
    cost = total_tokens * (0.14 / 1_000_000)
    try:
        async with session_factory() as session:
            session.add(AgentRun(
                run_type=run_type,
                model=model,
                input_json=input_payload,
                output_json={"raw": raw_output},
                cost_estimate=cost,
                status=status,
                run_id=ctx["run_id"],
                document_id=ctx["document_id"],
                span_id=ctx["span_id"],
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            ))
            await session.commit()
    except Exception:
        logger.exception(
            "record_agent_run failed",
            extra={"run_type": run_type, "status": status},
        )


async def record_span_extraction(
    session_factory,
    *,
    run_id: uuid.UUID,
    span_id: uuid.UUID,
    document_id: uuid.UUID,
    status: str,
    attempts: int,
    error: str | None = None,
) -> None:
    """Insert one span_extractions row. Catches and logs DB errors; never raises."""
    try:
        async with session_factory() as session:
            session.add(SpanExtraction(
                run_id=run_id,
                span_id=span_id,
                document_id=document_id,
                status=status,
                attempts=attempts,
                error=error,
            ))
            await session.commit()
    except Exception:
        logger.exception(
            "record_span_extraction failed",
            extra={"span_id": str(span_id), "status": status},
        )


async def mark_document_timestamp(
    session_factory,
    document_id: uuid.UUID,
    field: _TIMESTAMP_FIELDS,
) -> None:
    """Set one *_at timestamp column on a Document row. Catches and logs DB errors; never raises."""
    try:
        async with session_factory() as session:
            doc = await session.get(Document, document_id)
            if doc is not None:
                setattr(doc, field, datetime.now(timezone.utc))
                await session.commit()
    except Exception:
        logger.exception(
            "mark_document_timestamp failed",
            extra={"document_id": str(document_id), "field": field},
        )
