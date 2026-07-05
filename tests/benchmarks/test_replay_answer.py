"""Unit tests for the answer-path replay lab's pure helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from scripts.benchmarks.replay_answer import (
    _build_lean_prompt,
    _parse_dt,
    _prep_blocks,
)
from scripts.benchmarks.run_longmemeval import _serialize_blocks


def _block(label: str, date: str | None, score: float, text: str = "t") -> dict:
    return {"label": label, "published_at": date, "score": score, "text": text}


def test_parse_dt_round_trip_and_bad_input():
    assert _parse_dt("2023-04-10T17:50:00+00:00") == datetime(
        2023, 4, 10, 17, 50, tzinfo=timezone.utc
    )
    assert _parse_dt(None) is None
    assert _parse_dt("") is None
    assert _parse_dt("not-a-date") is None


def test_serialize_blocks_makes_datetime_json_safe_and_reparses():
    block = {"published_at": datetime(2023, 4, 10, tzinfo=timezone.utc), "text": "x"}
    serialized = _serialize_blocks([block])
    assert isinstance(serialized[0]["published_at"], str)
    assert _parse_dt(serialized[0]["published_at"]) == datetime(2023, 4, 10, tzinfo=timezone.utc)


def test_prep_blocks_score_order_preserved_and_chrono_sorts():
    raw = [
        _block("C1", "2023-03-01T00:00:00+00:00", 0.9),
        _block("C2", "2023-01-01T00:00:00+00:00", 0.5),
        _block("C3", "2023-02-01T00:00:00+00:00", 0.7),
    ]
    score = _prep_blocks(raw, "score")
    assert [b["label"] for b in score] == ["C1", "C2", "C3"]  # input order kept
    chrono = _prep_blocks(raw, "chrono")
    assert [b["label"] for b in chrono] == ["C2", "C3", "C1"]  # earliest first


def test_prep_blocks_max_blocks_keeps_top_score():
    raw = [
        _block("C1", None, 0.2),
        _block("C2", None, 0.9),
        _block("C3", None, 0.5),
    ]
    kept = _prep_blocks(raw, "score", max_blocks=2)
    assert {b["label"] for b in kept} == {"C2", "C3"}  # lowest-score C1 dropped


def test_lean_prompt_drops_metadata_keeps_essentials():
    blocks = [
        {
            "label": "C1",
            "published_at": datetime(2023, 4, 10, tzinfo=timezone.utc),
            "role": "supersession",
            "text": "capsule body",
            "url": "http://x",
            "document_title": "Title",
            "score": 0.42,
            "object_type": "event",
            "evidence": [{"text": "an excerpt"}],
        }
    ]
    out = _build_lean_prompt("Q?", blocks, hint="", as_of=None)
    assert "capsule body" in out
    assert "Date: 2023-04-10" in out
    assert "Role: supersession" in out
    assert "Excerpt: an excerpt" in out
    for dropped in ("http://x", "Title", "0.42", "object_type", "Score"):
        assert dropped not in out


def test_lean_prompt_guards_missing_evidence_text():
    blocks = [{"label": "C1", "published_at": None, "text": "body", "evidence": [{"span_id": "x"}]}]
    # must not raise on evidence lacking a 'text' key
    out = _build_lean_prompt("Q?", blocks, hint="", as_of=None)
    assert "Excerpt:" not in out
