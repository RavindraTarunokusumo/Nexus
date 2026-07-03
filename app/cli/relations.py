"""nexus relations sub-commands — cross-document relation classification."""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from app.cli.capsules import _require_db_url
from app.cli.config import CLISettings
from app.config import settings
from app.db.session import make_engine, make_session_factory
from app.domain_packs.loader import load_pack
from app.intelligence.cross_relations import classify_cross_document_relations
from app.intelligence.extraction import _resolve_t2_model
from app.intelligence.llm_client import LLMClient

console = Console()
relations_app = typer.Typer(help="Cross-document relation classification commands.")


def _run(coro):
    """Run a coroutine safely — works both inside and outside a running event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None:
        return asyncio.run(coro)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result()


@relations_app.command("run")
def run(
    domain: str = typer.Option(..., "--domain", help="Domain to process."),
    pack: Optional[str] = typer.Option(
        None,
        "--pack",
        help="Domain pack id (defaults to settings.default_pack_id).",
    ),
    max_pairs: int = typer.Option(60, "--max-pairs", help="Max pairs to classify."),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        help="T2 model (defaults to pack override or settings.t2_model).",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report pairs without classifying."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON instead of a table."),
    db_url: Optional[str] = typer.Option(None, "--db-url", help="Override DATABASE_URL."),
) -> None:
    """Classify cross-document capsule relations for a domain."""
    pack_id = pack or settings.default_pack_id
    domain_pack = load_pack(pack_id)
    resolved_model = model or _resolve_t2_model(domain_pack, settings.t2_model)

    cfg = CLISettings(**{"database_url": db_url} if db_url else {})
    database_url = _require_db_url(cfg)
    engine = make_engine(database_url)
    sf = make_session_factory(engine)
    client = LLMClient(
        settings.llm_api_key,
        sf,
        base_url=settings.llm_base_url,
    )

    async def _classify():
        return await classify_cross_document_relations(
            sf,
            client,
            domain=domain,
            pack=domain_pack,
            model=resolved_model,
            max_pairs=max_pairs,
            dry_run=dry_run,
        )

    report = _run(_classify())

    if json_output:
        typer.echo(report.model_dump_json(indent=2))
        return

    label = " (DRY RUN — no rows committed)" if dry_run else ""
    table = Table(title=f"Cross-Document Relations{label}")
    table.add_column("Metric", style="bold")
    table.add_column("Count", justify="right")
    table.add_row("Candidate pairs", str(report.candidate_pairs))
    table.add_row("Classified pairs", str(report.classified_pairs))
    table.add_row("Relations created", str(report.relations_created))
    table.add_row("Skipped (existing)", str(report.skipped_existing))
    console.print(table)
