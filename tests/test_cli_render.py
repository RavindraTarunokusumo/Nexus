"""Unit tests for app/cli/render.py — pure formatters, no DB."""

import json
import uuid
from datetime import datetime, timezone

from app.cli.render import (
    render_chat_answer,
    render_claims_table,
    render_document_detail,
    render_documents_table,
    render_extraction_summary,
    render_search_results,
    render_sources_table,
    render_status,
)


def _make_status_snapshot(**overrides):
    base = {
        "docs_by_status": {"fetched": 2, "chunked": 1, "embedded": 10},
        "total_documents": 13,
        "total_spans": 84,
        "total_sources": 3,
        "enabled_sources": 2,
        "last_ingest_at": datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc),
        "stuck_count": 0,
    }
    base.update(overrides)
    return base


def test_render_status_human_contains_counts(capsys):
    render_status(_make_status_snapshot(), json_output=False)
    out = capsys.readouterr().out
    assert "fetched" in out
    assert "chunked" in out
    assert "embedded" in out
    assert "13" in out  # total documents
    assert "84" in out  # spans


def test_render_status_json_is_parseable(capsys):
    snap = _make_status_snapshot()
    render_status(snap, json_output=True)
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["total_documents"] == 13
    assert parsed["docs_by_status"]["embedded"] == 10


def test_render_status_handles_empty_db(capsys):
    snap = _make_status_snapshot(
        docs_by_status={},
        total_documents=0,
        total_spans=0,
        total_sources=0,
        enabled_sources=0,
        last_ingest_at=None,
    )
    render_status(snap, json_output=False)
    out = capsys.readouterr().out
    assert "0" in out  # at least one zero rendered


def test_render_sources_table_handles_empty(capsys):
    render_sources_table([], json_output=False)
    out = capsys.readouterr().out
    assert "No sources" in out or "sources" in out.lower()


def test_render_sources_table_renders_rows(capsys):
    sources = [
        {
            "id": uuid.uuid4(),
            "name": "Feed A",
            "source_type": "rss",
            "url": "https://a.example/feed",
            "domain_pack": "personal_ai_tech",
            "enabled": True,
            "credibility_score": 0.8,
        }
    ]
    render_sources_table(sources, json_output=False)
    out = capsys.readouterr().out
    assert "Feed A" in out
    assert "rss" in out


def test_render_documents_table_json_round_trip(capsys):
    docs = [
        {
            "id": uuid.uuid4(),
            "title": "Doc 1",
            "url": "https://example.com/1",
            "status": "embedded",
            "content_hash": "abc123",
            "source_name": "Feed A",
            "fetched_at": datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc),
            "published_at": None,
        }
    ]
    render_documents_table(docs, json_output=True)
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed[0]["title"] == "Doc 1"
    assert parsed[0]["status"] == "embedded"


def test_render_documents_table_empty(capsys):
    render_documents_table([], json_output=False)
    out = capsys.readouterr().out
    assert "No documents" in out or "documents" in out.lower()


def test_render_document_detail_shows_spans(capsys):
    detail = {
        "id": uuid.uuid4(),
        "title": "Test Doc",
        "url": "https://example.com",
        "status": "embedded",
        "content_hash": "deadbeef" * 4,
        "source_name": "Feed A",
        "fetched_at": datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc),
        "published_at": None,
        "spans": [
            {
                "id": uuid.uuid4(),
                "span_index": 0,
                "text": "First span text here",
                "token_count": 4,
                "has_embedding": True,
            },
            {
                "id": uuid.uuid4(),
                "span_index": 1,
                "text": "Second span text here",
                "token_count": 4,
                "has_embedding": False,
            },
        ],
    }
    render_document_detail(detail, json_output=False)
    out = capsys.readouterr().out
    assert "Test Doc" in out
    assert "First span" in out
    # Embedding vector itself must never appear; placeholder ok
    assert "vec(384)" in out or "has_embedding" in out or "embedded" in out.lower()


def test_render_search_results_shows_score_and_text(capsys):
    results = [
        {
            "span_id": str(uuid.uuid4()),
            "document_id": str(uuid.uuid4()),
            "span_index": 0,
            "score": 0.87,
            "text": "Open-source LLM Llama released today",
            "document_title": "Article 1",
            "document_status": "embedded",
        }
    ]
    render_search_results(results, json_output=False)
    out = capsys.readouterr().out
    assert "0.87" in out
    assert "Open-source LLM" in out
    assert "Article 1" in out
    assert "embedded" in out


def test_render_extraction_summary_human(capsys):
    summary = {
        "document_id": str(uuid.uuid4()),
        "claims_extracted": 3,
        "spans_processed": 2,
        "spans_failed": 0,
        "tokens_used": 450,
        "cost_estimate_usd": 0.000135,
        "claim_ids": [str(uuid.uuid4()) for _ in range(3)],
    }
    render_extraction_summary(summary, json_output=False)
    out = capsys.readouterr().out
    assert "3" in out
    assert "450" in out
    assert "0.000135" in out


def test_render_extraction_summary_json(capsys):
    summary = {
        "document_id": str(uuid.uuid4()),
        "claims_extracted": 1,
        "spans_processed": 1,
        "spans_failed": 0,
        "tokens_used": 100,
        "cost_estimate_usd": 0.00003,
        "claim_ids": [str(uuid.uuid4())],
    }
    render_extraction_summary(summary, json_output=True)
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["claims_extracted"] == 1
    assert parsed["tokens_used"] == 100


def test_render_claims_table_human(capsys):
    claims = [
        {
            "id": uuid.uuid4(),
            "claim_text": "GPT-5 was released by OpenAI.",
            "claim_type": "model_release",
            "entities_json": ["OpenAI", "GPT-5"],
            "topics_json": ["LLM releases"],
            "confidence": 0.92,
            "status": "active",
            "created_at": datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc),
        }
    ]
    render_claims_table(claims, json_output=False)
    out = capsys.readouterr().out
    assert "model_release" in out
    assert "GPT-5" in out or "OpenAI" in out
    assert "0.92" in out


def test_render_claims_table_empty(capsys):
    render_claims_table([], json_output=False)
    out = capsys.readouterr().out
    assert "No claims" in out


def test_render_document_detail_includes_claims(capsys):
    detail = {
        "id": uuid.uuid4(),
        "title": "Test Doc",
        "url": None,
        "status": "claims_extracted",
        "content_hash": "abc",
        "source_name": "Feed",
        "fetched_at": datetime(2026, 5, 18, tzinfo=timezone.utc),
        "published_at": None,
        "spans": [],
    }
    claims = [
        {
            "id": uuid.uuid4(),
            "claim_text": "Model X beats GPT-4.",
            "claim_type": "benchmark_result",
            "entities_json": ["Model X"],
            "topics_json": [],
            "confidence": 0.85,
            "status": "active",
            "created_at": datetime(2026, 5, 18, tzinfo=timezone.utc),
        }
    ]
    render_document_detail(detail, json_output=False, claims=claims)
    out = capsys.readouterr().out
    assert "Model X" in out
    assert "benchmark_result" in out


def test_render_document_detail_claims_in_json(capsys):
    detail = {
        "id": uuid.uuid4(),
        "title": "T",
        "url": None,
        "status": "claims_extracted",
        "content_hash": "x",
        "source_name": "S",
        "fetched_at": None,
        "published_at": None,
        "spans": [],
    }
    cid = uuid.uuid4()
    claims = [
        {
            "id": cid,
            "claim_text": "Claim text here.",
            "claim_type": "other",
            "entities_json": [],
            "topics_json": [],
            "confidence": 0.5,
            "status": "active",
            "created_at": datetime(2026, 5, 18, tzinfo=timezone.utc),
        }
    ]
    render_document_detail(detail, json_output=True, claims=claims)
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["title"] == "T"
    assert len(parsed["claims"]) == 1
    assert parsed["claims"][0]["claim_text"] == "Claim text here."


def test_render_search_results_json(capsys):
    results = [
        {
            "span_id": str(uuid.uuid4()),
            "document_id": str(uuid.uuid4()),
            "span_index": 0,
            "score": 0.5,
            "text": "t",
            "document_title": None,
            "document_status": "embedded",
        }
    ]
    render_search_results(results, json_output=True)
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed[0]["score"] == 0.5


def test_render_chat_answer_human(capsys):
    render_chat_answer(
        {
            "answer": "Model X was released.",
            "citations": [
                {
                    "document_id": str(uuid.uuid4()),
                    "span_id": str(uuid.uuid4()),
                    "document_title": "Release article",
                    "url": "https://example.com/release",
                    "score": 0.91,
                    "claim_ids": [str(uuid.uuid4())],
                }
            ],
            "tokens_used": 123,
            "cost_estimate_usd": 0.000017,
        },
        json_output=False,
    )
    out = capsys.readouterr().out
    assert "Model X was released" in out
    assert "Release article" in out
    assert "0.91" in out
