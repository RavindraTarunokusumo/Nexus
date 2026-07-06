"""Unit tests for LoCoMo adapter pure helpers (no DB, LLM, or network)."""

from app.config import settings
from scripts.benchmarks.run_locomo import (
    LoCoMoJudgeVerdict,
    _conversation_to_corpus,
    _last_session_as_of,
    _parse_args,
    _parse_locomo_datetime,
    _render_report,
    build_judge_prompt,
    category_name,
    conversation_sessions,
    gold_answer_text,
    is_adversarial,
    render_locomo_session_text,
    select_conversations,
    select_questions,
    session_to_document,
)

_SAMPLE_TURNS = [
    {"speaker": "Caroline", "dia_id": "D1:1", "text": "Hey Mel! Good to see you!"},
    {"speaker": "Melanie", "dia_id": "D1:2", "text": "Hey Caroline! I'm swamped."},
]

_SAMPLE_CONVERSATION = {
    "speaker_a": "Caroline",
    "speaker_b": "Melanie",
    "session_1_date_time": "1:56 pm on 8 May, 2023",
    "session_1": _SAMPLE_TURNS,
    "session_2_date_time": "2:00 pm on 15 May, 2023",
    "session_2": [{"speaker": "Caroline", "dia_id": "D2:1", "text": "Went for a run."}],
}

_SAMPLE_SAMPLE = {
    "sample_id": "conv-1",
    "conversation": _SAMPLE_CONVERSATION,
    "qa": [
        {
            "question": "What did Caroline do?",
            "answer": "Went for a run.",
            "evidence": ["D2:1"],
            "category": 4,
        },
        {"question": "When?", "answer": "15 May 2023", "evidence": ["D2:1"], "category": 2},
        {
            "question": "What did Caroline realize?",
            "evidence": ["D2:1"],
            "category": 5,
            "adversarial_answer": "self-care is important",
        },
    ],
}


def test_render_locomo_session_text_speaker_labels():
    text = render_locomo_session_text(_SAMPLE_TURNS)
    assert text == "Caroline: Hey Mel! Good to see you!\nMelanie: Hey Caroline! I'm swamped."


def test_parse_locomo_datetime_valid():
    parsed = _parse_locomo_datetime("1:56 pm on 8 May, 2023")
    assert parsed is not None
    assert (parsed.year, parsed.month, parsed.day, parsed.hour, parsed.minute) == (
        2023,
        5,
        8,
        13,
        56,
    )


def test_parse_locomo_datetime_invalid_returns_none():
    assert _parse_locomo_datetime("not a date") is None
    assert _parse_locomo_datetime(None) is None
    assert _parse_locomo_datetime("") is None


def test_conversation_sessions_orders_by_session_number():
    sessions = conversation_sessions(_SAMPLE_CONVERSATION)
    assert [n for n, _, _ in sessions] == [1, 2]
    assert sessions[0][1] == "1:56 pm on 8 May, 2023"
    assert sessions[1][2][0]["text"] == "Went for a run."


def test_conversation_sessions_ignores_padding_date_time_only_keys():
    conversation = dict(_SAMPLE_CONVERSATION)
    conversation["session_20_date_time"] = "9:00 am on 1 January, 2024"  # no session_20 content
    sessions = conversation_sessions(conversation)
    assert [n for n, _, _ in sessions] == [1, 2]


def test_session_to_document_field_mapping():
    doc = session_to_document("conv-1", 1, "1:56 pm on 8 May, 2023", _SAMPLE_TURNS)
    assert doc["title"] == "conv-1/session_1"
    assert doc["url"] == "locomo://conv-1/session_1"
    assert "Caroline: Hey Mel!" in doc["text"]
    assert doc["published_at"] is not None
    assert doc["published_at"].year == 2023


def test_conversation_to_corpus_one_document_per_session():
    corpus = _conversation_to_corpus(_SAMPLE_SAMPLE)
    assert len(corpus) == 2
    assert corpus[0]["url"] == "locomo://conv-1/session_1"
    assert corpus[1]["url"] == "locomo://conv-1/session_2"


def test_conversation_to_corpus_skips_empty_session(capsys):
    # An empty turns list renders to "" (no speaker-prefixed lines at all) — the only
    # way a rendered session is genuinely blank, since every non-empty turn list always
    # produces at least one "Speaker: ..." line.
    sample = {
        "sample_id": "conv-2",
        "conversation": {
            "session_1_date_time": "1:56 pm on 8 May, 2023",
            "session_1": [],
        },
    }
    corpus = _conversation_to_corpus(sample)
    assert corpus == []
    assert "skipping empty session" in capsys.readouterr().out


def test_last_session_as_of_picks_latest_date():
    as_of = _last_session_as_of(_SAMPLE_CONVERSATION)
    assert as_of is not None
    assert (as_of.year, as_of.month, as_of.day) == (2023, 5, 15)


def test_last_session_as_of_no_parseable_dates_returns_none():
    conversation = {"session_1_date_time": "garbage", "session_1": _SAMPLE_TURNS}
    assert _last_session_as_of(conversation) is None


def test_select_conversations_limit_offset():
    samples = [{"sample_id": str(i)} for i in range(5)]
    selected = select_conversations(samples, limit=2, offset=1)
    assert [s["sample_id"] for s in selected] == ["1", "2"]


def test_select_conversations_limit_zero_means_no_cap():
    samples = [{"sample_id": str(i)} for i in range(5)]
    assert len(select_conversations(samples, limit=0, offset=0)) == 5


def test_select_questions_category_filter():
    selected = select_questions(_SAMPLE_SAMPLE["qa"], categories=[2, 5], limit=0)
    assert [qa["category"] for qa in selected] == [2, 5]


def test_select_questions_limit_applies_after_filter():
    selected = select_questions(_SAMPLE_SAMPLE["qa"], categories=[2, 4, 5], limit=1)
    assert len(selected) == 1
    assert selected[0]["category"] == 4


def test_is_adversarial():
    assert is_adversarial(5) is True
    assert is_adversarial(1) is False
    assert is_adversarial(None) is False


def test_category_name_known_and_unknown():
    assert category_name(1) == "multi_hop"
    assert category_name(2) == "temporal"
    assert category_name(5) == "adversarial"
    assert category_name(99) == "category_99"
    assert category_name(None) == "unknown"


def test_gold_answer_text_adversarial_uses_adversarial_answer():
    qa = {"category": 5, "adversarial_answer": "self-care is important"}
    assert gold_answer_text(qa) == "self-care is important"


def test_gold_answer_text_non_adversarial_uses_answer():
    assert gold_answer_text({"category": 2, "answer": 2022}) == "2022"
    assert gold_answer_text({"category": 4, "answer": "Adoption agencies"}) == "Adoption agencies"


def test_build_judge_prompt_adversarial_branch():
    prompt = build_judge_prompt(
        "What did Caroline realize?",
        "self-care is important",
        "The conversation does not mention this.",
        category=5,
    )
    assert "unanswerable" in prompt.lower()
    assert "What did Caroline realize?" in prompt
    assert "self-care is important" in prompt
    assert "Correct Answer" not in prompt


def test_build_judge_prompt_temporal_branch():
    prompt = build_judge_prompt("When?", "15 May 2023", "May 15, 2023", category=2)
    assert "off-by-one" in prompt
    assert "15 May 2023" in prompt


def test_build_judge_prompt_default_branch():
    prompt = build_judge_prompt("What?", "a run", "Went for a run.", category=4)
    assert "off-by-one" not in prompt
    assert "unanswerable" not in prompt.lower()
    assert "Correct Answer: a run" in prompt


def test_locomo_judge_verdict_parsing():
    verdict = LoCoMoJudgeVerdict.model_validate_json('{"correct": true, "rationale": "matches"}')
    assert verdict.correct is True
    assert verdict.rationale == "matches"


def test_render_report_includes_overall_and_per_category():
    rows = [
        {"category": 4, "autoeval_label": True, "latency_s": 1.0, "tokens_used": 10},
        {"category": 4, "autoeval_label": False, "latency_s": 2.0, "tokens_used": 20},
        {"category": 5, "autoeval_label": True, "latency_s": None, "tokens_used": None},
    ]
    report = _render_report(rows, judge_model="test-model")
    assert "# LoCoMo Report" in report
    assert "test-model" in report
    assert "## 4 (single_hop)" in report
    assert "## 5 (adversarial)" in report
    assert "| accuracy | 0.667 |" in report  # overall: 2/3 correct


def test_render_report_no_rows_reports_na():
    report = _render_report([], judge_model="test-model")
    assert "| accuracy | n/a |" in report


def test_parse_args_defaults():
    args = _parse_args([])
    assert args.categories == "1,2,3,4,5"
    assert args.limit == 0
    assert args.offset == 0
    assert args.question_limit == 0
    assert args.k == 5
    assert args.pack is None
    assert args.workers == 1
    assert args.db_url_template == ""
    assert args.db_url is None


def test_parse_args_pass_through():
    args = _parse_args(
        [
            "--categories",
            "2,5",
            "--limit",
            "1",
            "--question-limit",
            "2",
            "--workers",
            "3",
            "--db-url-template",
            "postgresql+asyncpg://nexus:nexus@localhost:5434/nexus_locomo_w{n}",
            "--db-url",
            "postgresql+asyncpg://nexus:nexus@localhost:5434/nexus_locomo",
        ]
    )
    assert args.categories == "2,5"
    assert args.limit == 1
    assert args.question_limit == 2
    assert args.workers == 3
    assert (
        args.db_url_template == "postgresql+asyncpg://nexus:nexus@localhost:5434/nexus_locomo_w{n}"
    )
    assert args.db_url == "postgresql+asyncpg://nexus:nexus@localhost:5434/nexus_locomo"


def test_run_locomo_pack_defaults_to_settings_default_pack_id():
    import inspect

    from scripts.benchmarks import run_locomo as module

    sig = inspect.signature(module.run_locomo)
    assert sig.parameters["pack"].default is None
    assert settings.default_pack_id == "personal_ai_tech"
