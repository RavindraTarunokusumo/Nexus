import uuid

import pytest

from app.observability.run_context import (
    chat_run,
    current_context,
    extraction_run,
    span_scope,
)


@pytest.mark.asyncio
async def test_chat_run_clears_document_and_span_context_then_restores():
    document_id = uuid.uuid4()
    span_id = uuid.uuid4()

    async with extraction_run(document_id) as extraction_run_id:
        async with span_scope(span_id):
            assert current_context() == {
                "run_id": extraction_run_id,
                "document_id": document_id,
                "span_id": span_id,
            }

            async with chat_run() as chat_run_id:
                assert chat_run_id != extraction_run_id
                assert current_context() == {
                    "run_id": chat_run_id,
                    "document_id": None,
                    "span_id": None,
                }

            assert current_context() == {
                "run_id": extraction_run_id,
                "document_id": document_id,
                "span_id": span_id,
            }
