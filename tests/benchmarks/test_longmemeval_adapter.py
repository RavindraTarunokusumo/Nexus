"""Unit tests for LongMemEval adapter pure helpers (no DB, LLM, or network)."""

from scripts.benchmarks.run_longmemeval import (
    LongMemEvalJudgeVerdict,
    build_judge_prompt,
    is_abstention,
    render_session_text,
    select_instances,
    session_to_document,
)

_SAMPLE_TURNS = [
    {"role": "user", "content": "I bought a red car.", "has_answer": True},
    {"role": "assistant", "content": "Nice choice!", "has_answer": False},
]


def test_render_session_text_role_labels():
    text = render_session_text(_SAMPLE_TURNS)
    assert text.startswith("User: I bought a red car.")
    assert "Assistant: Nice choice!" in text
    assert "has_answer" not in text


def test_render_session_text_ignores_has_answer_flag():
    turns = [{"role": "user", "content": "secret", "has_answer": True}]
    assert render_session_text(turns) == "User: secret"


def test_session_to_document_field_mapping():
    doc = session_to_document(
        "q1",
        "sess_a",
        "2023/04/10 (Mon) 23:07",
        _SAMPLE_TURNS,
        session_index=2,
    )
    assert doc["title"] == "q1/2"
    assert doc["url"] == "longmemeval://q1/sess_a"
    assert "User: I bought a red car." in doc["text"]
    assert doc["published_at"] is not None
    assert doc["published_at"].year == 2023
    assert doc["published_at"].month == 4
    assert doc["published_at"].day == 10


def test_session_to_document_missing_date_falls_back_to_question_date():
    doc = session_to_document(
        "q1",
        "sess_a",
        None,
        _SAMPLE_TURNS,
        question_date="2024/01/15 (Mon) 12:00",
    )
    assert doc["published_at"] is not None
    assert doc["published_at"].year == 2024
    assert doc["published_at"].month == 1
    assert doc["published_at"].day == 15


def test_session_to_document_no_parseable_dates_omits_published_at():
    doc = session_to_document("q1", "sess_a", "not-a-date", _SAMPLE_TURNS, question_date="also-bad")
    assert doc["published_at"] is None


def test_select_instances_category_filter():
    instances = [
        {"question_id": "a", "question_type": "knowledge-update"},
        {"question_id": "b", "question_type": "temporal-reasoning"},
        {"question_id": "c", "question_type": "multi-session"},
    ]
    selected = select_instances(instances, categories=["knowledge-update"], limit=0, offset=0)
    assert [i["question_id"] for i in selected] == ["a"]


def test_select_instances_limit_offset_slice_after_filter():
    instances = [
        {"question_id": "a", "question_type": "knowledge-update"},
        {"question_id": "b", "question_type": "knowledge-update"},
        {"question_id": "c", "question_type": "knowledge-update"},
        {"question_id": "d", "question_type": "temporal-reasoning"},
    ]
    selected = select_instances(
        instances,
        categories=["knowledge-update", "temporal-reasoning"],
        limit=2,
        offset=1,
    )
    assert [i["question_id"] for i in selected] == ["b", "c"]


def test_select_instances_limit_zero_means_no_cap():
    instances = [{"question_id": str(i), "question_type": "knowledge-update"} for i in range(5)]
    selected = select_instances(instances, categories=["knowledge-update"], limit=0, offset=0)
    assert len(selected) == 5


def test_is_abstention():
    assert is_abstention("gpt4_70e84552_abs") is True
    assert is_abstention("gpt4_2655b836") is False


def test_build_judge_prompt_knowledge_update():
    prompt = build_judge_prompt(
        "What is my car color?",
        "red",
        "Your car is red.",
        abstention=False,
        question_type="knowledge-update",
    )
    assert "What is my car color?" in prompt
    assert "red" in prompt
    assert "Your car is red." in prompt
    assert "updated answer" in prompt
    assert "unanswerable" not in prompt.lower()


def test_build_judge_prompt_temporal_reasoning_off_by_one_clause():
    prompt = build_judge_prompt(
        "How many days?",
        "18",
        "19 days",
        abstention=False,
        question_type="temporal-reasoning",
    )
    assert "off-by-one" in prompt
    assert "How many days?" in prompt


def test_build_judge_prompt_abstention_branch():
    prompt = build_judge_prompt(
        "Which came first?",
        "Not enough information about cows.",
        "I do not have enough evidence to answer that from the current corpus.",
        abstention=True,
    )
    assert "unanswerable" in prompt.lower()
    assert "Which came first?" in prompt
    assert "Not enough information about cows." in prompt
    assert "Correct Answer" not in prompt


def test_longmemeval_judge_verdict_parsing():
    verdict = LongMemEvalJudgeVerdict.model_validate_json(
        '{"correct": true, "rationale": "Response matches gold."}'
    )
    assert verdict.correct is True
    assert verdict.rationale == "Response matches gold."

    negative = LongMemEvalJudgeVerdict.model_validate_json(
        '{"correct": false, "rationale": "Missing key fact."}'
    )
    assert negative.correct is False
