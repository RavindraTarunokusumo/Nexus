"""End-to-end CLI tests via typer.testing.CliRunner."""

import json
import uuid

import pytest
from typer.testing import CliRunner

from app.cli.main import app
from app.db.models import Document, Source

runner = CliRunner()


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
