"""nexus lifecycle sub-commands — apply retention and epistemic lifecycle rules."""

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
from app.intelligence.lifecycle import apply_lifecycle_transitions

console = Console()
lifecycle_app = typer.Typer(help="Capsule lifecycle transition commands.")


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


@lifecycle_app.command("run")
def run(
    domain: Optional[str] = typer.Option(
        None,
        "--domain",
        help="Domain to process (defaults to the selected pack's domain).",
    ),
    pack: Optional[str] = typer.Option(
        None,
        "--pack",
        help="Domain pack id (defaults to settings.default_pack_id).",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report transitions without writing."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON instead of a table."),
    db_url: Optional[str] = typer.Option(None, "--db-url", help="Override DATABASE_URL."),
) -> None:
    """Apply deterministic lifecycle transitions for candidate/active capsules."""
    pack_id = pack or settings.default_pack_id
    domain_pack = load_pack(pack_id)
    resolved_domain = domain or domain_pack.metadata.domain

    cfg = CLISettings(**{"database_url": db_url} if db_url else {})
    database_url = _require_db_url(cfg)
    engine = make_engine(database_url)
    sf = make_session_factory(engine)

    async def _apply():
        async with sf() as session:
            return await apply_lifecycle_transitions(
                session,
                domain=resolved_domain,
                pack=domain_pack,
                dry_run=dry_run,
            )

    report = _run(_apply())

    if json_output:
        typer.echo(report.model_dump_json(indent=2))
        return

    label = " (DRY RUN — no rows committed)" if dry_run else ""
    table = Table(title=f"Lifecycle Transitions{label}")
    table.add_column("To state", style="bold")
    table.add_column("Count", justify="right")
    if report.counts:
        for state, count in sorted(report.counts.items()):
            table.add_row(state, str(count))
    else:
        table.add_row("(none)", "0")
    console.print(table)
