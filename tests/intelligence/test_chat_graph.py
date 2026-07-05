from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_session_factory(
    rows: list | None = None,
    has_sentinel: bool = True,
    evidence_rows: list | None = None,
) -> MagicMock:
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.scalar = AsyncMock(return_value=MagicMock() if has_sentinel else None)

    empty_result = MagicMock()
    empty_result.all.return_value = []
    candidate_result = MagicMock()
    candidate_result.all.return_value = rows or []
    evidence_result = MagicMock()
    evidence_result.all.return_value = evidence_rows or []
    mock_session.execute = AsyncMock(side_effect=[candidate_result, empty_result, evidence_result])

    sf = MagicMock()
    sf.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    sf.return_value.__aexit__ = AsyncMock(return_value=False)
    return sf


def _make_client(
    intent: str = "general",
    shape: str = "general",
    answer: str = "The answer",
    citations: list[str] | None = None,
) -> AsyncMock:
    client = AsyncMock()
    intent_result = MagicMock()
    intent_result.intent = intent
    intent_result.shape = shape
    answer_result = MagicMock()
    answer_result.notes = ""
    answer_result.answer = answer
    answer_result.citations = citations if citations is not None else ["C1"]
    client.complete_json = AsyncMock(side_effect=[(intent_result, 10), (answer_result, 100)])
    return client


def _make_embedder() -> MagicMock:
    e = MagicMock()
    e.embed_one.return_value = [0.1] * 384
    return e


def _make_pack(query_intents: dict | None = None) -> MagicMock:
    pack = MagicMock()
    pack.retrieval_policy.query_intents = query_intents if query_intents is not None else {}
    pack.retrieval_policy.hybrid_score_weights = {
        "semantic_similarity": 0.35,
        "domain_object_type_match": 0.20,
        "source_authority": 0.12,
        "recency": 0.12,
        "salience": 0.11,
        "relation_relevance": 0.07,
        "evidence_quality": 0.03,
    }
    pack.context_assembly.max_tokens_by_tier = {}
    pack.context_assembly.include = [
        "highest_salience_relevant_objects",
        "source_refs_and_excerpts",
    ]
    pack.context_assembly.ordering = "evidence_strength"
    return pack


def _capsule_row(capsule_id: uuid.UUID | None = None, doc_id: uuid.UUID | None = None) -> MagicMock:
    row = MagicMock()
    row.id = capsule_id or uuid.uuid4()
    row.document_id = doc_id or uuid.uuid4()
    row.text = "GPT-5 released with 128k context."
    row.domain_object_type = "model_release"
    row.object_family = "technical_objects"
    row.lifecycle_state = "active"
    row.salience = 0.8
    row.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    row.semantic_sim = 0.9
    row.title = "Release article"
    row.url = "https://example.com/release"
    row.epistemic_state = {}
    row.confidence = 0.8
    return row


@pytest.mark.asyncio
async def test_classify_intent_writes_query_intent() -> None:
    from app.intelligence.chat import _run_classify_intent

    client = AsyncMock()
    result_mock = MagicMock()
    result_mock.intent = "technical_deep_dive"
    result_mock.shape = "general"
    client.complete_json.return_value = (result_mock, 10)

    pack = MagicMock()
    pack.retrieval_policy.query_intents = {"technical_deep_dive": {}}
    state = {"question": "How does GPT-5 work?", "model": "test-model", "pack": pack}

    result = await _run_classify_intent(state, client)

    assert result == {"query_intent": "technical_deep_dive", "question_shape": "general"}


@pytest.mark.asyncio
async def test_retrieve_capsules_returns_labelled_blocks() -> None:
    from app.intelligence.chat import _run_retrieve_capsules

    capsule_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    sf = _make_session_factory(rows=[_capsule_row(capsule_id, doc_id)])
    embedder = _make_embedder()
    pack = _make_pack()

    state = {"question": "test", "top_k": 1, "query_intent": "general", "pack": pack}
    result = await _run_retrieve_capsules(state, sf, embedder)

    blocks = result["context_blocks"]
    assert len(blocks) == 1
    assert blocks[0]["label"] == "C1"
    assert blocks[0]["capsule_id"] == capsule_id
    assert blocks[0]["document_id"] == doc_id
    assert blocks[0]["text"] == "GPT-5 released with 128k context."
    assert blocks[0]["object_type"] == "model_release"


@pytest.mark.asyncio
async def test_retrieve_capsules_attaches_evidence() -> None:
    from app.intelligence.chat import _run_retrieve_capsules

    cap_id, doc_id, span_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    sf = _make_session_factory(
        rows=[_capsule_row(cap_id, doc_id)],
        evidence_rows=[(cap_id, span_id, 0, "supporting span text")],
    )
    state = {"question": "q", "top_k": 5, "query_intent": "general", "pack": _make_pack()}

    result = await _run_retrieve_capsules(state, sf, _make_embedder())

    evidence = result["context_blocks"][0]["evidence"]
    assert evidence[0]["text"] == "supporting span text"
    assert evidence[0]["span_id"] == span_id
    assert evidence[0]["span_index"] == 0


@pytest.mark.asyncio
async def test_retrieve_capsules_returns_empty_when_no_embeddings() -> None:
    from app.intelligence.chat import _run_retrieve_capsules

    sf = _make_session_factory(has_sentinel=False)
    embedder = _make_embedder()
    pack = _make_pack()

    state = {"question": "test", "top_k": 5, "query_intent": "general", "pack": pack}
    result = await _run_retrieve_capsules(state, sf, embedder)

    assert result == {"context_blocks": []}
    embedder.embed_one.assert_not_called()


@pytest.mark.asyncio
async def test_format_result_builds_capsule_citation() -> None:
    from app.intelligence.chat import make_chat_graph, run_chat_with_context

    capsule_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    sf = _make_session_factory(rows=[_capsule_row(capsule_id, doc_id)])
    client = _make_client(answer="GPT-5 is fast.", citations=["C1"])
    embedder = _make_embedder()
    pack = _make_pack(query_intents={"general": {}})

    graph = make_chat_graph(sf, client, embedder)
    with patch("app.intelligence.chat.load_pack", return_value=pack):
        result = await run_chat_with_context(graph, "What is GPT-5?", "test-model", top_k=1)

    assert result["answer"] == "GPT-5 is fast."
    assert len(result["citations"]) == 1
    cit = result["citations"][0]
    assert str(cit["capsule_id"]) == str(capsule_id)
    assert cit["summary"] == "GPT-5 released with 128k context."
    assert "span_id" not in cit
    assert "claim_ids" not in cit


@pytest.mark.asyncio
async def test_insufficient_evidence_when_no_capsule_embeddings() -> None:
    from app.intelligence.chat import make_chat_graph, run_chat_with_context

    sf = _make_session_factory(has_sentinel=False)
    client = _make_client()
    embedder = _make_embedder()
    pack = _make_pack()

    graph = make_chat_graph(sf, client, embedder)
    with patch("app.intelligence.chat.load_pack", return_value=pack):
        result = await run_chat_with_context(graph, "anything", "test-model", top_k=5)

    assert "I do not have enough evidence" in result["answer"]


@pytest.mark.asyncio
async def test_citation_label_normalization_brackets() -> None:
    from app.intelligence.chat import make_chat_graph, run_chat_with_context

    capsule_id = uuid.uuid4()
    sf = _make_session_factory(rows=[_capsule_row(capsule_id)])
    # LLM returns bracketed label [C1] — must normalize to C1
    client = _make_client(answer="Answer.", citations=["[C1]"])
    embedder = _make_embedder()
    pack = _make_pack(query_intents={"general": {}})

    graph = make_chat_graph(sf, client, embedder)
    with patch("app.intelligence.chat.load_pack", return_value=pack):
        result = await run_chat_with_context(graph, "test", "test-model", top_k=1)

    assert len(result["citations"]) == 1
    assert str(result["citations"][0]["capsule_id"]) == str(capsule_id)


@pytest.mark.asyncio
async def test_classify_intent_shape_fallback_on_llm_error() -> None:
    from app.intelligence.chat import _run_classify_intent
    from app.intelligence.llm_client import LLMError

    client = AsyncMock()
    client.complete_json.side_effect = LLMError("fail")

    pack = MagicMock()
    pack.retrieval_policy.query_intents = {"general": {}}
    state = {"question": "When did X GA?", "model": "test-model", "pack": pack}

    result = await _run_classify_intent(state, client)

    assert result == {"query_intent": "general", "question_shape": "general"}


@pytest.mark.asyncio
async def test_classify_intent_shape_fallback_on_invalid_shape() -> None:
    from app.intelligence.chat import _run_classify_intent

    client = AsyncMock()
    result_mock = MagicMock()
    result_mock.intent = "general"
    result_mock.shape = "not_a_real_shape"
    client.complete_json.return_value = (result_mock, 10)

    pack = MagicMock()
    pack.retrieval_policy.query_intents = {"general": {}}
    state = {"question": "When did X GA?", "model": "test-model", "pack": pack}

    result = await _run_classify_intent(state, client)

    assert result == {"query_intent": "general", "question_shape": "general"}


@pytest.mark.asyncio
async def test_generate_answer_threads_factoid_hint() -> None:
    from app.intelligence.chat import make_chat_graph, run_chat_with_context
    from app.intelligence.prompts import chat_answer as chat_answer_module
    from app.intelligence.router import resolve_strategy

    capsule_id = uuid.uuid4()
    sf = _make_session_factory(rows=[_capsule_row(capsule_id)])
    client = _make_client(shape="factoid", answer="Jan 2026.", citations=["C1"])
    embedder = _make_embedder()
    pack = _make_pack(query_intents={"general": {}})

    graph = make_chat_graph(sf, client, embedder)
    with (
        patch("app.intelligence.chat.load_pack", return_value=pack),
        patch(
            "app.intelligence.chat.build_user_prompt",
            wraps=chat_answer_module.build_user_prompt,
        ) as mock_build_prompt,
    ):
        await run_chat_with_context(graph, "When did X GA?", "test-model", top_k=1)

    expected_hint = resolve_strategy("factoid").answer_hint
    mock_build_prompt.assert_called_once()
    assert mock_build_prompt.call_args.kwargs.get("hint") == expected_hint


def test_build_user_prompt_renders_hint_line() -> None:
    from app.intelligence.prompts.chat_answer import build_user_prompt

    blocks = [
        {
            "label": "C1",
            "document_title": "T",
            "url": None,
            "object_type": "model_release",
            "score": 0.9,
            "text": "GPT-5 released.",
        }
    ]
    with_hint = build_user_prompt("q", blocks, hint="State the specific date.")
    assert with_hint.endswith("Answer guidance: State the specific date.")
    without_hint = build_user_prompt("q", blocks)
    assert "Answer guidance:" not in without_hint


def _executed_limit(sf: MagicMock) -> int:
    stmt = sf.return_value.__aenter__.return_value.execute.call_args_list[0].args[0]
    return stmt._limit_clause.value


@pytest.mark.asyncio
async def test_retrieve_capsules_factoid_widens_fetch_limit() -> None:
    from app.intelligence.chat import _run_retrieve_capsules
    from app.intelligence.router import STRATEGIES

    sf = _make_session_factory(rows=[_capsule_row()])
    state = {
        "question": "q",
        "top_k": 5,
        "query_intent": "general",
        "question_shape": "factoid",
        "pack": _make_pack(),
    }
    await _run_retrieve_capsules(state, sf, _make_embedder())
    assert _executed_limit(sf) == 5 * STRATEGIES["factoid"].fetch_k_multiplier


@pytest.mark.asyncio
async def test_retrieve_capsules_multi_doc_raises_top_k_and_fetch() -> None:
    from app.intelligence.chat import _run_retrieve_capsules
    from app.intelligence.router import STRATEGIES

    sf = _make_session_factory(rows=[_capsule_row()])
    state = {
        "question": "q",
        "top_k": 5,
        "query_intent": "general",
        "question_shape": "multi_doc",
        "pack": _make_pack(),
    }
    await _run_retrieve_capsules(state, sf, _make_embedder())
    strategy = STRATEGIES["multi_doc"]
    assert _executed_limit(sf) == (5 + strategy.top_k_delta) * strategy.fetch_k_multiplier


@pytest.mark.asyncio
async def test_retrieve_capsules_pack_none_skips_weight_overrides() -> None:
    from app.intelligence.chat import _run_retrieve_capsules

    sf = _make_session_factory(rows=[_capsule_row()])
    state = {
        "question": "q",
        "top_k": 5,
        "query_intent": "general",
        "question_shape": "factoid",
        "pack": None,
    }
    with patch("app.intelligence.chat.compute_hybrid_score", return_value=1.0) as mock_score:
        await _run_retrieve_capsules(state, sf, _make_embedder())
    assert mock_score.call_args.args[1] == {}
