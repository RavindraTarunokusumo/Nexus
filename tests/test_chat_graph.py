import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import Claim, ClaimEvidence, Document, Source, Span
from app.intelligence.chat import make_chat_graph, run_chat_with_context
from app.intelligence.llm_client import LLMNetworkError
from app.observability.run_context import (
    chat_run,
    current_context,
    extraction_run,
    span_scope,
)


class FixedEmbedder:
    def embed_one(self, text):
        return [1.0] + [0.0] * 383


class FakeChatClient:
    def __init__(self, response=None, error=None):
        self.response = response or {"answer": "Model X was released.", "citations": ["C1"]}
        self.error = error
        self.calls = []

    async def complete_json(self, *, model, system, user, response_model, **kwargs):
        self.calls.append({"model": model, "system": system, "user": user, "kwargs": kwargs})
        if self.error:
            raise self.error
        return response_model.model_validate(self.response), 123


async def _seed_hybrid_context(session_factory: async_sessionmaker):
    async with session_factory() as session:
        source = Source(name="Feed", source_type="rss", url="https://feed.example/rss")
        session.add(source)
        await session.flush()
        doc = Document(
            source_id=source.id,
            title="Release article",
            url="https://example.com/release",
            raw_text="Model X was released.",
            clean_text="Model X was released.",
            content_hash=f"h-{uuid.uuid4()}",
            status="claims_extracted",
        )
        session.add(doc)
        await session.flush()
        span = Span(
            document_id=doc.id,
            span_index=0,
            text="Model X was released with open weights.",
            token_count=8,
            embedding=[1.0] + [0.0] * 383,
        )
        session.add(span)
        await session.flush()
        claim = Claim(
            document_id=doc.id,
            claim_text="Model X was released with open weights.",
            claim_type="model_release",
            entities_json=["Model X"],
            topics_json=["open weights"],
            confidence=0.9,
            status="active",
        )
        session.add(claim)
        await session.flush()
        session.add(
            ClaimEvidence(
                claim_id=claim.id,
                span_id=span.id,
                evidence_role="support",
                confidence=0.9,
            )
        )
        await session.commit()
        return doc.id, span.id, claim.id


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


@pytest.mark.asyncio
async def test_chat_graph_insufficient_evidence_skips_model(session_factory):
    client = FakeChatClient()
    graph = make_chat_graph(session_factory, client, FixedEmbedder())

    final = await run_chat_with_context(graph, "unknown question", "m", top_k=3)

    assert final["answer"].startswith("I do not have enough evidence")
    assert final["citations"] == []
    assert final["tokens_used"] == 0
    assert client.calls == []


@pytest.mark.asyncio
async def test_chat_graph_uses_spans_and_linked_claims(session_factory):
    _doc_id, span_id, claim_id = await _seed_hybrid_context(session_factory)
    client = FakeChatClient(response={"answer": "Model X was released.", "citations": ["C1"]})
    graph = make_chat_graph(session_factory, client, FixedEmbedder())

    final = await run_chat_with_context(graph, "What was released?", "m", top_k=3)

    assert final["answer"] == "Model X was released."
    assert final["citations"][0]["span_id"] == span_id
    assert final["citations"][0]["claim_ids"] == [claim_id]
    assert "Model X was released with open weights." in client.calls[0]["user"]
    assert "run_type" in client.calls[0]["kwargs"]
    assert client.calls[0]["kwargs"]["run_type"] == "chat_answer"


@pytest.mark.asyncio
async def test_chat_graph_accepts_bracketed_citation_labels(session_factory):
    _doc_id, span_id, claim_id = await _seed_hybrid_context(session_factory)
    client = FakeChatClient(response={"answer": "Model X was released.", "citations": [" [C1] "]})
    graph = make_chat_graph(session_factory, client, FixedEmbedder())

    final = await run_chat_with_context(graph, "What was released?", "m", top_k=3)

    assert final["answer"] == "Model X was released."
    assert final["citations"][0]["span_id"] == span_id
    assert final["citations"][0]["claim_ids"] == [claim_id]


@pytest.mark.asyncio
async def test_chat_graph_rejects_generated_answer_without_citations(session_factory):
    await _seed_hybrid_context(session_factory)
    client = FakeChatClient(response={"answer": "Answer.", "citations": []})
    graph = make_chat_graph(session_factory, client, FixedEmbedder())

    final = await run_chat_with_context(graph, "What was released?", "m", top_k=3)

    assert final["answer"].startswith("I do not have enough evidence")
    assert final["citations"] == []


@pytest.mark.asyncio
async def test_chat_graph_deduplicates_normalized_citation_labels(session_factory):
    _doc_id, span_id, claim_id = await _seed_hybrid_context(session_factory)
    client = FakeChatClient(
        response={"answer": "Model X was released.", "citations": ["C1", " [C1] "]}
    )
    graph = make_chat_graph(session_factory, client, FixedEmbedder())

    final = await run_chat_with_context(graph, "What was released?", "m", top_k=3)

    assert final["answer"] == "Model X was released."
    assert len(final["citations"]) == 1
    assert final["citations"][0]["span_id"] == span_id
    assert final["citations"][0]["claim_ids"] == [claim_id]


@pytest.mark.asyncio
async def test_chat_graph_orders_equal_similarity_spans_deterministically(session_factory):
    async with session_factory() as session:
        source = Source(name="Feed", source_type="rss", url="https://feed.example/rss")
        session.add(source)
        await session.flush()

        later_doc_id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        earlier_doc_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        later_span_id = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
        earlier_span_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
        later_doc = Document(
            id=later_doc_id,
            source_id=source.id,
            title="Later document",
            url="https://example.com/later",
            raw_text="Later document text.",
            clean_text="Later document text.",
            content_hash=f"h-{later_doc_id}",
            status="embedded",
        )
        earlier_doc = Document(
            id=earlier_doc_id,
            source_id=source.id,
            title="Earlier document",
            url="https://example.com/earlier",
            raw_text="Earlier document text.",
            clean_text="Earlier document text.",
            content_hash=f"h-{earlier_doc_id}",
            status="embedded",
        )
        session.add_all([later_doc, earlier_doc])
        await session.flush()
        session.add_all(
            [
                Span(
                    id=later_span_id,
                    document_id=later_doc.id,
                    span_index=0,
                    text="Later document equal-score span.",
                    token_count=5,
                    embedding=[1.0] + [0.0] * 383,
                ),
                Span(
                    id=earlier_span_id,
                    document_id=earlier_doc.id,
                    span_index=0,
                    text="Earlier document equal-score span.",
                    token_count=5,
                    embedding=[1.0] + [0.0] * 383,
                ),
            ]
        )
        await session.commit()

    client = FakeChatClient(response={"answer": "Answer.", "citations": ["C1", "C2"]})
    graph = make_chat_graph(session_factory, client, FixedEmbedder())

    final = await run_chat_with_context(graph, "What happened?", "m", top_k=2)

    assert [citation["span_id"] for citation in final["citations"]] == [
        earlier_span_id,
        later_span_id,
    ]
    user_prompt = client.calls[0]["user"]
    assert user_prompt.index("[C1]") < user_prompt.index("Earlier document equal-score span.")
    assert user_prompt.index("Earlier document equal-score span.") < user_prompt.index("[C2]")
    assert user_prompt.index("[C2]") < user_prompt.index("Later document equal-score span.")


@pytest.mark.asyncio
async def test_chat_graph_excludes_rejected_linked_claims(session_factory):
    doc_id, span_id, claim_id = await _seed_hybrid_context(session_factory)
    async with session_factory() as session:
        rejected_claim = Claim(
            document_id=doc_id,
            claim_text="Rejected claim should not be used.",
            claim_type="other",
            entities_json=[],
            topics_json=[],
            confidence=0.1,
            status="rejected",
        )
        session.add(rejected_claim)
        await session.flush()
        session.add(
            ClaimEvidence(
                claim_id=rejected_claim.id,
                span_id=span_id,
                evidence_role="support",
                confidence=0.1,
            )
        )
        await session.commit()

    client = FakeChatClient(response={"answer": "Model X was released.", "citations": ["C1"]})
    graph = make_chat_graph(session_factory, client, FixedEmbedder())

    final = await run_chat_with_context(graph, "What was released?", "m", top_k=3)

    assert final["citations"][0]["claim_ids"] == [claim_id]
    assert "Model X was released with open weights." in client.calls[0]["user"]
    assert "Rejected claim should not be used." not in client.calls[0]["user"]


@pytest.mark.asyncio
async def test_chat_graph_drops_unknown_citation_labels(session_factory):
    await _seed_hybrid_context(session_factory)
    client = FakeChatClient(response={"answer": "Answer.", "citations": ["C9"]})
    graph = make_chat_graph(session_factory, client, FixedEmbedder())

    final = await run_chat_with_context(graph, "What happened?", "m", top_k=3)

    assert final["answer"].startswith("I do not have enough evidence")
    assert final["citations"] == []


@pytest.mark.asyncio
async def test_chat_graph_network_error_bubbles(session_factory):
    await _seed_hybrid_context(session_factory)
    client = FakeChatClient(error=LLMNetworkError("OpenRouter 503"))
    graph = make_chat_graph(session_factory, client, FixedEmbedder())

    final = await run_chat_with_context(graph, "What happened?", "m", top_k=3)

    assert "OpenRouter 503" in final["error"]
