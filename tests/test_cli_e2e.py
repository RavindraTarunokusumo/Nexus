"""End-to-end CLI tests via typer.testing.CliRunner."""

import json
import re
import uuid

import pytest
from typer.testing import CliRunner

from app.cli.main import app
from app.db.models import Document, Source

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


async def _seed_two_docs(session_factory):
    async with session_factory() as session:
        src = Source(name="Test Feed", source_type="rss", url="https://t.example/feed")
        session.add(src)
        await session.flush()
        d1 = Document(
            source_id=src.id,
            title="Doc One",
            clean_text="x",
            content_hash=f"h-{uuid.uuid4()}",
            status="embedded",
        )
        d2 = Document(
            source_id=src.id,
            title="Doc Two",
            clean_text="y",
            content_hash=f"h-{uuid.uuid4()}",
            status="fetched",
        )
        session.add_all([d1, d2])
        await session.commit()
        return src.id, d1.id, d2.id


@pytest.mark.asyncio
async def test_status_command_json(session_factory, db_url):
    await _seed_two_docs(session_factory)
    result = runner.invoke(app, ["status", "--json", "--db-url", db_url])
    assert result.exit_code == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["total_documents"] == 2
    assert data["docs_by_status"]["embedded"] == 1
    assert data["docs_by_status"]["fetched"] == 1


@pytest.mark.asyncio
async def test_sources_command_json(session_factory, db_url):
    await _seed_two_docs(session_factory)
    result = runner.invoke(app, ["sources", "--json", "--db-url", db_url])
    assert result.exit_code == 0, result.stdout
    data = json.loads(result.stdout)
    assert len(data) == 1
    assert data[0]["name"] == "Test Feed"


@pytest.mark.asyncio
async def test_documents_command_filters_by_status(session_factory, db_url):
    await _seed_two_docs(session_factory)
    result = runner.invoke(app, ["documents", "--status", "embedded", "--json", "--db-url", db_url])
    assert result.exit_code == 0, result.stdout
    data = json.loads(result.stdout)
    assert len(data) == 1
    assert data[0]["title"] == "Doc One"


@pytest.mark.asyncio
async def test_document_detail_command(session_factory, db_url):
    _, doc_id, _ = await _seed_two_docs(session_factory)
    result = runner.invoke(app, ["document", str(doc_id), "--json", "--db-url", db_url])
    assert result.exit_code == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["title"] == "Doc One"
    assert data["spans"] == []


@pytest.mark.asyncio
async def test_document_not_found_exits_nonzero(db_url):
    result = runner.invoke(app, ["document", str(uuid.uuid4()), "--db-url", db_url])
    assert result.exit_code != 0


def test_status_help_works():
    result = runner.invoke(app, ["status", "--help"])
    assert result.exit_code == 0
    assert "Pipeline" in result.stdout or "status" in result.stdout.lower()


@pytest.mark.asyncio
async def test_search_command_calls_http_with_correct_payload(monkeypatch, db_url):
    captured = {}

    async def fake_search(base_url, query, top_k):
        captured["base_url"] = base_url
        captured["query"] = query
        captured["top_k"] = top_k
        return [
            {
                "span_id": str(uuid.uuid4()),
                "document_id": str(uuid.uuid4()),
                "span_index": 0,
                "score": 0.91,
                "text": "matched span",
                "document_title": "Doc",
                "document_status": "embedded",
            }
        ]

    monkeypatch.setattr("app.cli.main.http_search_spans", fake_search)

    result = runner.invoke(
        app,
        [
            "search",
            "open-source LLMs",
            "--top-k",
            "5",
            "--json",
            "--api-url",
            "http://test.example",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert captured["query"] == "open-source LLMs"
    assert captured["top_k"] == 5
    assert captured["base_url"] == "http://test.example"
    data = json.loads(result.stdout)
    assert data[0]["score"] == 0.91


@pytest.mark.asyncio
async def test_ingest_url_command(monkeypatch, db_url):
    captured = {}

    async def fake_ingest_url(base_url, url, source_name, domain_pack):
        captured.update(
            base_url=base_url, url=url, source_name=source_name, domain_pack=domain_pack
        )
        return {
            "ingested": 1,
            "skipped": 0,
            "documents": [{"id": str(uuid.uuid4()), "title": None}],
        }

    monkeypatch.setattr("app.cli.main.http_ingest_url", fake_ingest_url)

    result = runner.invoke(
        app,
        [
            "ingest",
            "url",
            "https://example.com/article",
            "--db-url",
            db_url,
            "--api-url",
            "http://test.example",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert captured["url"] == "https://example.com/article"
    assert "ingested" in result.stdout.lower() or "1" in result.stdout


@pytest.mark.asyncio
async def test_ingest_text_command_reads_file(monkeypatch, db_url, tmp_path):
    text_file = tmp_path / "article.md"
    text_file.write_text("Article body content here.", encoding="utf-8")
    captured = {}

    async def fake_ingest_text(base_url, *, title, text, source_name, domain_pack):
        captured.update(title=title, text=text, source_name=source_name)
        return {"ingested": 1, "skipped": 0, "documents": []}

    monkeypatch.setattr("app.cli.main.http_ingest_text", fake_ingest_text)

    result = runner.invoke(
        app,
        ["ingest", "text", "--title", "My Article", "--file", str(text_file), "--db-url", db_url],
    )
    assert result.exit_code == 0, result.stdout
    assert captured["title"] == "My Article"
    assert captured["text"] == "Article body content here."


@pytest.mark.asyncio
async def test_extract_command_calls_http(monkeypatch, db_url):
    captured = {}

    async def fake_extract(base_url, document_id, *, force):
        captured["document_id"] = document_id
        captured["force"] = force
        return {
            "document_id": str(document_id),
            "claims_extracted": 2,
            "spans_processed": 1,
            "spans_failed": 0,
            "tokens_used": 300,
            "cost_estimate_usd": 0.00009,
            "claim_ids": [str(uuid.uuid4()), str(uuid.uuid4())],
        }

    monkeypatch.setattr("app.cli.main.http_extract_claims", fake_extract)
    doc_id = uuid.uuid4()
    result = runner.invoke(
        app,
        ["extract", str(doc_id), "--api-url", "http://test.example", "--json"],
    )
    assert result.exit_code == 0, result.stdout
    assert captured["document_id"] == doc_id
    assert captured["force"] is False
    data = json.loads(result.stdout)
    assert data["claims_extracted"] == 2


@pytest.mark.asyncio
async def test_chat_command_calls_http(monkeypatch, db_url):
    captured = {}

    async def fake_chat(base_url, question, top_k):
        captured["base_url"] = base_url
        captured["question"] = question
        captured["top_k"] = top_k
        return {
            "answer": "Grounded answer.",
            "citations": [],
            "retrieved_context_count": 0,
            "run_id": str(uuid.uuid4()),
            "tokens_used": 0,
            "cost_estimate_usd": 0.0,
        }

    monkeypatch.setattr("app.cli.main.http_chat_answer", fake_chat)
    result = runner.invoke(
        app,
        ["chat", "What changed?", "--top-k", "5", "--json", "--api-url", "http://test.example"],
    )
    assert result.exit_code == 0, result.stdout
    assert captured["base_url"] == "http://test.example"
    assert captured["question"] == "What changed?"
    assert captured["top_k"] == 5
    assert json.loads(result.stdout)["answer"] == "Grounded answer."


@pytest.mark.asyncio
async def test_extract_command_force_flag(monkeypatch, db_url):
    captured = {}

    async def fake_extract(base_url, document_id, *, force):
        captured["force"] = force
        return {
            "document_id": str(document_id),
            "claims_extracted": 1,
            "spans_processed": 1,
            "spans_failed": 0,
            "tokens_used": 100,
            "cost_estimate_usd": 0.00003,
            "claim_ids": [str(uuid.uuid4())],
        }

    monkeypatch.setattr("app.cli.main.http_extract_claims", fake_extract)
    result = runner.invoke(
        app,
        ["extract", str(uuid.uuid4()), "--force", "--api-url", "http://test.example"],
    )
    assert result.exit_code == 0, result.stdout
    assert captured["force"] is True


@pytest.mark.asyncio
async def test_extract_command_api_error_exits_nonzero(monkeypatch, db_url):
    from app.cli.http import CLIHttpError

    async def fail_extract(base_url, document_id, *, force):
        raise CLIHttpError("409: claims already exist")

    monkeypatch.setattr("app.cli.main.http_extract_claims", fail_extract)
    result = runner.invoke(
        app,
        ["extract", str(uuid.uuid4()), "--api-url", "http://test.example"],
    )
    assert result.exit_code != 0


@pytest.mark.asyncio
async def test_document_claims_flag_shows_claims(session_factory, db_url):
    from app.db.models import Claim

    _, doc_id, _ = await _seed_two_docs(session_factory)
    async with session_factory() as session:
        session.add(
            Claim(
                document_id=doc_id,
                claim_text="GPT-5 released.",
                claim_type="model_release",
                entities_json=["OpenAI"],
                topics_json=[],
                confidence=0.9,
                status="active",
            )
        )
        await session.commit()

    result = runner.invoke(
        app,
        ["document", str(doc_id), "--claims", "--json", "--db-url", db_url],
    )
    assert result.exit_code == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["title"] == "Doc One"
    assert len(data["claims"]) == 1
    assert data["claims"][0]["claim_text"] == "GPT-5 released."


@pytest.mark.asyncio
async def test_document_no_claims_flag_omits_claims(session_factory, db_url):
    _, doc_id, _ = await _seed_two_docs(session_factory)
    result = runner.invoke(
        app,
        ["document", str(doc_id), "--json", "--db-url", db_url],
    )
    assert result.exit_code == 0, result.stdout
    data = json.loads(result.stdout)
    assert "claims" not in data


@pytest.mark.asyncio
async def test_ingest_rss_command(monkeypatch, db_url):
    source_id = uuid.uuid4()
    captured = {}

    async def fake_ingest_rss(base_url, sid):
        captured["source_id"] = sid
        return {"ingested": 3, "skipped": 1, "documents": []}

    monkeypatch.setattr("app.cli.main.http_ingest_rss", fake_ingest_rss)

    result = runner.invoke(app, ["ingest", "rss", str(source_id), "--db-url", db_url])
    assert result.exit_code == 0, result.stdout
    assert captured["source_id"] == source_id


def test_capsules_backfill_help_works():
    result = runner.invoke(app, ["capsules", "backfill", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" in _strip_ansi(result.stdout)


def test_theses_synthesize_help_works():
    result = runner.invoke(app, ["theses", "synthesize", "--help"])
    assert result.exit_code == 0
    assert "--domain" in _strip_ansi(result.stdout)


def test_artefacts_create_help_works():
    result = runner.invoke(app, ["artefacts", "create", "--help"])
    assert result.exit_code == 0
    assert "--question" in _strip_ansi(result.stdout)


def test_artefacts_create_rejects_bad_capsule_id():
    result = runner.invoke(
        app,
        [
            "artefacts",
            "create",
            "--domain",
            "x",
            "--question",
            "q",
            "--answer",
            "a",
            "--capsule-id",
            "not-a-uuid",
        ],
    )
    assert result.exit_code != 0
