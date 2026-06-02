"""Direct unit tests for the update_status node in the extraction graph.

These tests avoid the testcontainers Postgres requirement (tests/conftest.py
imports a broken-on-this-machine chain) by mocking the session_factory at the
minimum surface area update_status touches: get(Document, id) + commit().

The goal is to pin the empty-document-is-success behaviour (review F1) without
spinning up a real DB.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.intelligence.extraction import (
    STATUS_CLAIMS_EXTRACTED,
    STATUS_EXTRACTION_FAILED,
    STATUS_EXTRACTION_PARTIAL,
    make_extraction_graph,
)


class _FakeDocument:
    def __init__(self, doc_id: uuid.UUID) -> None:
        self.id = doc_id
        self.status = "embedded"


class _FakeSession:
    """Async context-managed session that tracks the document row only.

    Implements just the surface area update_status uses: `get(Document, id)`
    plus `commit()`. The mark_document_timestamp helper is patched out via
    monkeypatch in the test itself, so we do not need to model timestamp
    columns here.
    """

    def __init__(self, doc: _FakeDocument) -> None:
        self._doc = doc

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        return None

    async def get(self, _model: Any, _id: uuid.UUID) -> _FakeDocument:
        return self._doc

    async def commit(self) -> None:
        return None


def _make_session_factory(doc: _FakeDocument) -> Any:
    factory = MagicMock()
    factory.side_effect = lambda: _FakeSession(doc)
    return factory


async def _invoke_update_status(
    *,
    error: str | None,
    results: list[dict],
) -> str:
    """Drive the update_status closure and return the new doc status."""
    doc_id = uuid.uuid4()
    doc = _FakeDocument(doc_id)
    session_factory = _make_session_factory(doc)

    # The client never gets called in update_status; provide a placeholder.
    client = object()

    with patch(
        "app.intelligence.extraction.mark_document_timestamp",
        new=AsyncMock(return_value=None),
    ):
        graph = make_extraction_graph(session_factory, client)

        # Pull the update_status node out of the compiled graph by introspection.
        # langgraph stores compiled nodes on .nodes; the runnable is `.bound`.
        node = graph.nodes["update_status"].bound  # type: ignore[attr-defined]

        state: dict[str, Any] = {
            "document_id": doc_id,
            "run_id": None,
            "model": "test-model",
            "pack": None,
            "source_type": None,
            "spans": [],
            "results": results,
            "projected_claims": [],
            "stored_claim_ids": [],
            "total_tokens": 0,
            "error": error,
        }

        await node.ainvoke(state)

    return doc.status


@pytest.mark.asyncio
async def test_empty_document_marked_claims_extracted() -> None:
    """A document with zero spans (and no error) is a successful no-op extraction.

    Regression for review finding F1: previously routed to extraction_failed.
    """
    new_status = await _invoke_update_status(error=None, results=[])
    assert new_status == STATUS_CLAIMS_EXTRACTED


@pytest.mark.asyncio
async def test_all_results_error_marked_extraction_failed() -> None:
    """If every span has an error, the document is genuinely failed."""
    results = [
        {"span_id": "s1", "objects": [], "tokens": 0, "error": "boom"},
        {"span_id": "s2", "objects": [], "tokens": 0, "error": "boom2"},
    ]
    new_status = await _invoke_update_status(error=None, results=results)
    assert new_status == STATUS_EXTRACTION_FAILED


@pytest.mark.asyncio
async def test_mixed_failure_marked_extraction_partial() -> None:
    """If some spans error and some succeed, the document is partial."""
    results = [
        {"span_id": "s1", "objects": [], "tokens": 0, "error": "boom"},
        {"span_id": "s2", "objects": [], "tokens": 0, "error": None},
    ]
    new_status = await _invoke_update_status(error=None, results=results)
    assert new_status == STATUS_EXTRACTION_PARTIAL


@pytest.mark.asyncio
async def test_state_error_marked_extraction_failed() -> None:
    """Network-error short-circuit (state['error'] set) still routes to failed."""
    new_status = await _invoke_update_status(
        error="LLMNetworkError: upstream 503", results=[]
    )
    assert new_status == STATUS_EXTRACTION_FAILED
