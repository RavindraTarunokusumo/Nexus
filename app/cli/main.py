"""Nexus CLI — typer App entry point."""
from __future__ import annotations

import asyncio
import concurrent.futures
import uuid
from typing import Optional

import typer

from app.cli.config import CLISettings
from app.cli.db import (
    get_document_with_spans,
    get_status_snapshot,
    list_documents,
    list_sources,
)
from app.cli.render import (
    render_document_detail,
    render_documents_table,
    render_search_results,
    render_sources_table,
    render_status,
)
from app.cli.http import (
    ingest_rss as http_ingest_rss,
    ingest_text as http_ingest_text,
    ingest_url as http_ingest_url,
    search_spans as http_search_spans,
)

app = typer.Typer(help="Nexus Lite — operator CLI for monitoring the system.")
ingest_app = typer.Typer(help="Trigger ingestion via the running server.")
app.add_typer(ingest_app, name="ingest")


def _run(coro):
    """Run a coroutine safely — works both inside and outside a running event loop.

    When pytest-asyncio (or any other framework) already owns the event loop,
    ``asyncio.run()`` raises RuntimeError.  Running the coroutine in a fresh
    daemon thread guarantees it always gets its own loop.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None:
        return asyncio.run(coro)

    # There is already a running loop (e.g. inside an async test).  Spin up a
    # worker thread that has no event loop so asyncio.run() works normally there.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result()


def _settings(db_url: Optional[str], api_url: Optional[str]) -> CLISettings:
    overrides = {}
    if db_url:
        overrides["database_url"] = db_url
    if api_url:
        overrides["api_base_url"] = api_url
    return CLISettings(**overrides) if overrides else CLISettings()


@app.command()
def status(
    json_output: bool = typer.Option(False, "--json", help="Output JSON instead of a table."),
    db_url: Optional[str] = typer.Option(None, "--db-url", help="Override DATABASE_URL."),
    api_url: Optional[str] = typer.Option(None, "--api-url", help="Override API base URL."),
) -> None:
    """Show pipeline health: counts by status, totals, last ingest."""
    cfg = _settings(db_url, api_url)
    snapshot = _run(get_status_snapshot(cfg.database_url))
    render_status(snapshot, json_output=json_output)


@app.command()
def sources(
    enabled: Optional[bool] = typer.Option(
        None, "--enabled/--disabled", help="Filter by enabled flag."
    ),
    json_output: bool = typer.Option(False, "--json"),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    api_url: Optional[str] = typer.Option(None, "--api-url"),
) -> None:
    """List configured sources."""
    cfg = _settings(db_url, api_url)
    result = _run(list_sources(cfg.database_url, enabled=enabled))
    render_sources_table(result, json_output=json_output)


@app.command()
def documents(
    status: Optional[str] = typer.Option(None, "--status", help="Filter by document status."),
    source_id: Optional[uuid.UUID] = typer.Option(None, "--source", help="Filter by source ID."),
    since: Optional[str] = typer.Option(None, "--since", help="Only docs fetched after ISO timestamp."),
    limit: int = typer.Option(50, "--limit"),
    json_output: bool = typer.Option(False, "--json"),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    api_url: Optional[str] = typer.Option(None, "--api-url"),
) -> None:
    """List documents with optional filters."""
    from datetime import datetime
    since_dt = datetime.fromisoformat(since) if since else None
    cfg = _settings(db_url, api_url)
    docs = _run(
        list_documents(
            cfg.database_url,
            status=status, source_id=source_id, since=since_dt, limit=limit,
        )
    )
    render_documents_table(docs, json_output=json_output)


@app.command()
def document(
    document_id: uuid.UUID = typer.Argument(..., help="Document UUID."),
    json_output: bool = typer.Option(False, "--json"),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    api_url: Optional[str] = typer.Option(None, "--api-url"),
) -> None:
    """Show one document and all its spans."""
    cfg = _settings(db_url, api_url)
    detail = _run(get_document_with_spans(cfg.database_url, document_id))
    if detail is None:
        typer.echo(f"Document {document_id} not found.", err=True)
        raise typer.Exit(code=1)
    render_document_detail(detail, json_output=json_output)


@app.command()
def search(
    query: str = typer.Argument(..., help="Natural language search query."),
    top_k: int = typer.Option(10, "--top-k"),
    domain_pack: Optional[str] = typer.Option(None, "--domain-pack"),
    json_output: bool = typer.Option(False, "--json"),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    api_url: Optional[str] = typer.Option(None, "--api-url"),
) -> None:
    """Semantic search over embedded spans."""
    cfg = _settings(db_url, api_url)
    results = _run(
        http_search_spans(cfg.api_base_url, query, top_k, domain_pack)
    )
    render_search_results(results, json_output=json_output)


@ingest_app.command("url")
def ingest_url_cmd(
    url: str = typer.Argument(..., help="URL to fetch and ingest."),
    source_name: str = typer.Option("manual", "--source-name"),
    domain_pack: str = typer.Option("personal_ai_tech", "--domain-pack"),
    json_output: bool = typer.Option(False, "--json"),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    api_url: Optional[str] = typer.Option(None, "--api-url"),
) -> None:
    """Fetch one URL and ingest its content."""
    cfg = _settings(db_url, api_url)
    result = _run(http_ingest_url(cfg.api_base_url, url, source_name, domain_pack))
    if json_output:
        import json as _json
        typer.echo(_json.dumps(result, indent=2, default=str))
    else:
        typer.echo(f"Ingested: {result['ingested']}, Skipped: {result['skipped']}")


@ingest_app.command("text")
def ingest_text_cmd(
    title: str = typer.Option(..., "--title", help="Document title."),
    file: str = typer.Option(..., "--file", help="Path to text/markdown file."),
    source_name: str = typer.Option("manual", "--source-name"),
    domain_pack: str = typer.Option("personal_ai_tech", "--domain-pack"),
    json_output: bool = typer.Option(False, "--json"),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    api_url: Optional[str] = typer.Option(None, "--api-url"),
) -> None:
    """Ingest the contents of a local text file."""
    from pathlib import Path
    text = Path(file).read_text(encoding="utf-8")
    cfg = _settings(db_url, api_url)
    result = _run(
        http_ingest_text(
            cfg.api_base_url,
            title=title, text=text, source_name=source_name, domain_pack=domain_pack,
        )
    )
    if json_output:
        import json as _json
        typer.echo(_json.dumps(result, indent=2, default=str))
    else:
        typer.echo(f"Ingested: {result['ingested']}, Skipped: {result['skipped']}")


@ingest_app.command("rss")
def ingest_rss_cmd(
    source_id: uuid.UUID = typer.Argument(..., help="Source UUID (must be source_type=rss)."),
    json_output: bool = typer.Option(False, "--json"),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    api_url: Optional[str] = typer.Option(None, "--api-url"),
) -> None:
    """Trigger RSS ingestion for a configured source."""
    cfg = _settings(db_url, api_url)
    result = _run(http_ingest_rss(cfg.api_base_url, source_id))
    if json_output:
        import json as _json
        typer.echo(_json.dumps(result, indent=2, default=str))
    else:
        typer.echo(f"Ingested: {result['ingested']}, Skipped: {result['skipped']}")
