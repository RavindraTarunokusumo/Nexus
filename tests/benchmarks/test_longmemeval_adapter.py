"""Unit tests for LongMemEval adapter pure helpers (no DB, LLM, or network)."""

from app.config import settings
from scripts.benchmarks.run_longmemeval import (
    LongMemEvalJudgeVerdict,
    _parse_args,
    build_judge_prompt,
    is_abstention,
    render_session_text,
    select_instances,
    session_to_document,
    shard_instances,
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


def test_select_instances_per_category_limit():
    instances = [
        {"question_id": "a", "question_type": "knowledge-update"},
        {"question_id": "b", "question_type": "knowledge-update"},
        {"question_id": "c", "question_type": "temporal-reasoning"},
        {"question_id": "d", "question_type": "temporal-reasoning"},
        {"question_id": "e", "question_type": "temporal-reasoning"},
    ]
    selected = select_instances(
        instances,
        categories=["knowledge-update", "temporal-reasoning"],
        limit=0,
        offset=0,
        per_category_limit=1,
    )
    assert [i["question_id"] for i in selected] == ["a", "c"]


def test_select_instances_question_ids_override():
    instances = [
        {"question_id": "a", "question_type": "knowledge-update"},
        {"question_id": "b", "question_type": "temporal-reasoning"},
        {"question_id": "c", "question_type": "temporal-reasoning"},
    ]
    selected = select_instances(
        instances,
        categories=["knowledge-update", "temporal-reasoning"],
        limit=1,
        offset=0,
        question_ids=["c", "a"],
    )
    assert [i["question_id"] for i in selected] == ["a", "c"]


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


def test_parse_args_pack_defaults_to_none():
    args = _parse_args([])
    assert args.pack is None


def test_parse_args_pack_pass_through():
    args = _parse_args(["--pack", "conversation_v1"])
    assert args.pack == "conversation_v1"


def test_shard_instances_round_robin_three_workers():
    instances = [{"question_id": str(i)} for i in range(7)]
    w1 = shard_instances(instances, workers=3, worker_index=1)
    w2 = shard_instances(instances, workers=3, worker_index=2)
    w3 = shard_instances(instances, workers=3, worker_index=3)
    assert [idx for idx, _ in w1] == [0, 3, 6]
    assert [idx for idx, _ in w2] == [1, 4]
    assert [idx for idx, _ in w3] == [2, 5]
    assert [inst["question_id"] for _, inst in w1] == ["0", "3", "6"]


def test_shard_instances_single_worker_gets_all():
    instances = [{"question_id": "a"}, {"question_id": "b"}]
    shard = shard_instances(instances, workers=1, worker_index=1)
    assert [idx for idx, _ in shard] == [0, 1]


def test_parse_args_workers_and_db_url_template_defaults():
    args = _parse_args([])
    assert args.workers == 1
    assert args.db_url_template == ""


def test_parse_args_workers_and_db_url_template_pass_through():
    args = _parse_args(
        [
            "--workers",
            "4",
            "--db-url-template",
            "postgresql+asyncpg://nexus:nexus@localhost:5432/nexus_lme_w{n}",
        ]
    )
    assert args.workers == 4
    assert args.db_url_template == "postgresql+asyncpg://nexus:nexus@localhost:5432/nexus_lme_w{n}"


def test_run_longmemeval_pack_defaults_to_settings_default_pack_id():
    import inspect

    from scripts.benchmarks import run_longmemeval as module

    sig = inspect.signature(module.run_longmemeval)
    assert sig.parameters["pack"].default is None
    assert settings.default_pack_id == "personal_ai_tech"
