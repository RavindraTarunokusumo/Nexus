"""nexus theses sub-commands — cluster semantic_relations into Thesis rows."""

from __future__ import annotations

import asyncio
import json
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from app.cli.capsules import _require_db_url
from app.cli.config import CLISettings
from app.db.session import make_engine, make_session_factory
from app.intelligence.theses import synthesize_theses_from_relations

console = Console()
theses_app = typer.Typer(help="Thesis management commands.")


@theses_app.command("synthesize")
def synthesize(
    domain: str = typer.Option(..., "--domain", help="Domain pack id to cluster within."),
    min_strength: float = typer.Option(
        0.6, "--min-strength", help="Minimum relation strength to cluster on."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report clusters without writing."),
    db_url: Optional[str] = typer.Option(None, "--db-url", help="Override DATABASE_URL."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON instead of a table."),
) -> None:
    """Cluster strongly-related same-family capsules into Thesis rows.

    Reads semantic_relations written by classify_relations, unions connected
    capsules via strength >= --min-strength, and writes one Thesis per
    cluster of size >= 2. Re-running is not idempotent in this first writer
    (no unique constraint on theses) — intended for manual/reviewed use.
    """
    cfg = CLISettings(**{"database_url": db_url} if db_url else {})
    database_url = _require_db_url(cfg)
    engine = make_engine(database_url)
    sf = make_session_factory(engine)

    async def _run() -> list:
        async with sf() as session:
            if dry_run:
                # Dry-run: build clusters but roll back instead of commit.
                theses = await synthesize_theses_from_relations(
                    session, domain=domain, min_strength=min_strength
                )
                await session.rollback()
                return theses
            return await synthesize_theses_from_relations(
                session, domain=domain, min_strength=min_strength
            )

    theses = asyncio.run(_run())

    if json_output:
        typer.echo(
            json.dumps(
                {"domain": domain, "theses_written": len(theses), "dry_run": dry_run}, indent=2
            )
        )
        return

    label = " (DRY RUN — no rows committed)" if dry_run else ""
    table = Table(title=f"Thesis Synthesis{label}")
    table.add_column("Metric", style="bold")
    table.add_column("Count", justify="right")
    table.add_row("Theses written" + (" (would write)" if dry_run else ""), str(len(theses)))
    console.print(table)
