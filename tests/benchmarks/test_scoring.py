from scripts.benchmarks.scoring import aggregate, score_answer

_TIMELINE_QUESTION = {
    "question_id": "tl-001",
    "category": "timeline",
    "question": "When did X ship?",
    "expected_answer_keywords": ["september 15", "2025"],
    "forbidden_keywords": ["2024"],
    "expected_doc_keys": ["doc-a", "doc-b"],
    "expected_abstain": False,
    "notes": "",
}

_ABSTENTION_QUESTION = {
    "question_id": "ab-001",
    "category": "abstention",
    "question": "What score does the unreleased model get?",
    "expected_answer_keywords": [],
    "forbidden_keywords": [],
    "expected_doc_keys": [],
    "expected_abstain": True,
    "notes": "",
}


def test_score_answer_empty_citations_yields_none_recall_and_precision():
    result = score_answer(
        _TIMELINE_QUESTION,
        "It shipped September 15, 2025.",
        cited_doc_keys=[],
        retrieved_doc_keys=["doc-a"],
        abstained=False,
    )
    assert result["evidence_recall_at_k"] == 0.0
    assert result["citation_precision"] is None
    assert result["citation_faithfulness"] is True


def test_score_answer_abstention_correct():
    result = score_answer(
        _ABSTENTION_QUESTION,
        "I do not have enough evidence to answer that from the current corpus.",
        cited_doc_keys=[],
        retrieved_doc_keys=[],
        abstained=True,
    )
    assert result["answer_correctness"] == 1.0
    assert result["abstention_accuracy"] is True


def test_score_answer_abstention_incorrect_when_should_have_answered():
    question = dict(_TIMELINE_QUESTION, expected_abstain=False)
    result = score_answer(
        question,
        "I do not have enough evidence to answer that from the current corpus.",
        cited_doc_keys=[],
        retrieved_doc_keys=[],
        abstained=True,
    )
    assert result["answer_correctness"] == 0.0
    assert result["abstention_accuracy"] is False


def test_score_answer_abstention_incorrect_when_should_have_abstained():
    result = score_answer(
        _ABSTENTION_QUESTION,
        "The unreleased model scores 91.2 on the benchmark.",
        cited_doc_keys=[],
        retrieved_doc_keys=[],
        abstained=False,
    )
    assert result["answer_correctness"] == 0.0
    assert result["abstention_accuracy"] is False


def test_score_answer_forbidden_keyword_hit():
    result = score_answer(
        _TIMELINE_QUESTION,
        "It shipped September 15, 2024.",
        cited_doc_keys=[],
        retrieved_doc_keys=[],
        abstained=False,
    )
    assert result["forbidden_violation"] is True
    assert result["temporal_correctness"] is False


def test_score_answer_recall_and_precision_math():
    result = score_answer(
        _TIMELINE_QUESTION,
        "It shipped September 15, 2025.",
        cited_doc_keys=["doc-a", "doc-c"],
        retrieved_doc_keys=["doc-a", "doc-b", "doc-c"],
        abstained=False,
    )
    assert result["evidence_recall_at_k"] == 0.5  # {doc-a} ∩ expected / |expected|=2
    assert result["citation_precision"] == 0.5  # {doc-a} ∩ expected / |cited|=2
    assert result["citation_faithfulness"] is True


def test_score_answer_citation_faithfulness_false_when_cited_not_retrieved():
    result = score_answer(
        _TIMELINE_QUESTION,
        "It shipped September 15, 2025.",
        cited_doc_keys=["doc-z"],
        retrieved_doc_keys=["doc-a"],
        abstained=False,
    )
    assert result["citation_faithfulness"] is False


def test_score_answer_temporal_correctness_only_for_timeline_category():
    other = dict(_TIMELINE_QUESTION, category="multi_doc")
    result = score_answer(
        other,
        "It shipped September 15, 2025.",
        cited_doc_keys=[],
        retrieved_doc_keys=[],
        abstained=False,
    )
    assert result["temporal_correctness"] is None
    assert result["supersession_correctness"] is None


def test_score_answer_supersession_correctness_gated_by_category():
    question = dict(_TIMELINE_QUESTION, category="superseded")
    correct = score_answer(
        question,
        "It shipped September 15, 2025.",
        cited_doc_keys=[],
        retrieved_doc_keys=[],
        abstained=False,
    )
    assert correct["supersession_correctness"] is True
    assert correct["temporal_correctness"] is None


def test_aggregate_none_handling_across_categories():
    rows = [
        {
            **score_answer(_TIMELINE_QUESTION, "September 15, 2025", [], [], False),
            "category": "timeline",
        },
        {
            **score_answer(
                dict(_TIMELINE_QUESTION, category="multi_doc"), "no match", [], [], False
            ),
            "category": "multi_doc",
        },
    ]
    result = aggregate(rows)
    assert result["n"] == 2
    # multi_doc rows never populate temporal_correctness -> excluded, not zeroed.
    assert result["by_category"]["multi_doc"]["temporal_correctness"] is None
    assert result["by_category"]["timeline"]["temporal_correctness"] == 1.0
    # Overall mean only pools the one non-None timeline value.
    assert result["overall"]["temporal_correctness"] == 1.0


def test_aggregate_latency_and_tokens_optional():
    rows = [
        {
            **score_answer(_ABSTENTION_QUESTION, "abstain", [], [], True),
            "category": "abstention",
            "latency_s": 1.0,
            "tokens_used": 100,
        },
        {
            **score_answer(_ABSTENTION_QUESTION, "abstain", [], [], True),
            "category": "abstention",
            "latency_s": 3.0,
            "tokens_used": 200,
        },
    ]
    result = aggregate(rows)
    assert result["overall"]["latency_p50_s"] in (1.0, 3.0)
    assert result["overall"]["latency_p95_s"] == 3.0
    assert result["overall"]["total_tokens_used"] == 300.0


def test_aggregate_without_latency_or_tokens_omits_keys():
    rows = [
        {**score_answer(_ABSTENTION_QUESTION, "abstain", [], [], True), "category": "abstention"}
    ]
    result = aggregate(rows)
    assert "latency_p50_s" not in result["overall"]
    assert "total_tokens_used" not in result["overall"]
