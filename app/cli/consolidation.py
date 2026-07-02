"""nexus consolidation sub-commands — cluster relations into Thesis rows."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from app.cli.capsules import _require_db_url
from app.cli.config import CLISettings
from app.db.session import make_engine, make_session_factory
from app.domain_packs.loader import load_pack
from app.intelligence.consolidation import consolidate_domain

console = Console()
consolidation_app = typer.Typer(help="Domain consolidation commands.")


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


@consolidation_app.command("run")
def run(
    domain: str = typer.Option(..., "--domain", help="Domain pack id to consolidate within."),
    pack: str = typer.Option(
        "personal_ai_tech", "--pack", help="Domain pack YAML id (loads pack config)."
    ),
    min_strength: float = typer.Option(
        0.6, "--min-strength", help="Minimum relation strength to cluster on."
    ),
    min_cluster_size: int = typer.Option(
        2, "--min-cluster-size", help="Minimum connected capsules per thesis cluster."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report clusters without writing."),
    db_url: Optional[str] = typer.Option(None, "--db-url", help="Override DATABASE_URL."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON instead of a table."),
) -> None:
    """Cluster strongly-related capsules into Thesis rows for a domain."""
    cfg = CLISettings(**{"database_url": db_url} if db_url else {})
    database_url = _require_db_url(cfg)
    engine = make_engine(database_url)
    sf = make_session_factory(engine)
    domain_pack = load_pack(pack)

    async def _consolidate():
        async with sf() as session:
            return await consolidate_domain(
                session,
                domain=domain,
                pack=domain_pack,
                min_strength=min_strength,
                min_cluster_size=min_cluster_size,
                dry_run=dry_run,
            )

    report = _run(_consolidate())

    if json_output:
        typer.echo(json.dumps(report.model_dump(mode="json"), indent=2))
        return

    label = " (DRY RUN — no rows committed)" if dry_run else ""
    table = Table(title=f"Consolidation{label}")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Domain", report.domain)
    table.add_row(
        "Theses created" + (" (would create)" if dry_run else ""),
        str(report.theses_created),
    )
    console.print(table)
