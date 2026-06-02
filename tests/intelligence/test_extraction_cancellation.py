"""Tests that cancelled spans in extract_spans still get an audit row.

Regression for review finding F3: when one span task raises
LLMNetworkError, asyncio.gather cancels the siblings mid-flight. Each
cancelled task must still record an audit row via record_span_extraction
before re-raising, so the per-span audit trail does not silently lose
spans. The audit write is wrapped in asyncio.shield so it completes
even though cancellation is propagating through the task.

These tests exercise _extract_one_span directly with a recording stub for
record_span_extraction, so no DB is needed.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import patch

import pytest

import app.intelligence.extraction as extraction_module
from app.intelligence.extraction import _extract_one_span

# ---------------------------------------------------------------------------
# Recording stub for record_span_extraction
# ---------------------------------------------------------------------------


class _AuditRecorder:
    """Captures every record_span_extraction call. No DB writes."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(
        self,
        _session_factory: Any,
        *,
        run_id: uuid.UUID,
        span_id: uuid.UUID,
        document_id: uuid.UUID,
        status: str,
        attempts: int,
        error: str | None = None,
    ) -> None:
        self.calls.append(
            {
                "run_id": run_id,
                "span_id": span_id,
                "document_id": document_id,
                "status": status,
                "attempts": attempts,
                "error": error,
            }
        )


# ---------------------------------------------------------------------------
# Fake LLM client whose complete_json sleeps long enough to be cancelled
# ---------------------------------------------------------------------------


class _SleepingClient:
    """LLM client whose complete_json never returns until cancelled."""

    async def complete_json(self, **_kwargs: Any) -> tuple[Any, int]:
        await asyncio.sleep(60)  # well over any test timeout; expects cancellation
        raise AssertionError("unreachable: sleep should have been cancelled")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancelled_span_records_audit_row() -> None:
    """When a span task is cancelled mid-flight, _extract_one_span writes an
    audit row with status='cancelled' before re-raising CancelledError."""
    recorder = _AuditRecorder()
    span_id = uuid.uuid4()
    document_id = uuid.uuid4()
    run_id = uuid.uuid4()
    span = {
        "id": str(span_id),
        "text": "GPT-5 was released today.",
        "token_count": 10,
        "metadata_json": {"title": "Doc", "source_name": "S"},
    }

    with patch.object(extraction_module, "record_span_extraction", new=recorder):
        task = asyncio.create_task(
            _extract_one_span(
                span,
                _SleepingClient(),
                "test-model",
                session_factory=object(),  # never used (recorder stubbed)
                run_id=run_id,
                document_id=document_id,
                source_prefix="PREFIX",
            )
        )
        # Yield once so the task actually enters the await client.complete_json call.
        await asyncio.sleep(0)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    # Exactly one audit row, with status='cancelled' and the expected metadata.
    assert len(recorder.calls) == 1, recorder.calls
    call = recorder.calls[0]
    assert call["status"] == "cancelled"
    assert call["span_id"] == span_id
    assert call["document_id"] == document_id
    assert call["run_id"] == run_id
    assert call["attempts"] >= 1
    assert call["error"] == "cancelled"


def test_extract_one_span_shields_cancellation_audit() -> None:
    """Source-shape guard: _extract_one_span must wrap the cancellation
    audit write in asyncio.shield(...) so the row reaches the DB even when
    CancelledError is propagating through the task. Without the shield, the
    write itself can be interrupted by cancellation, defeating F3."""
    import inspect

    src = inspect.getsource(_extract_one_span)
    assert "asyncio.shield(" in src, (
        "_extract_one_span must wrap record_span_extraction in "
        "asyncio.shield(...) inside its except asyncio.CancelledError branch "
        "so the cancellation audit row is durable even mid-cancel."
    )
