"""Domain consolidation worker — clusters strong relations into Thesis rows."""

from __future__ import annotations

import uuid

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain_packs.loader import DomainPack
from app.intelligence.theses import synthesize_theses_from_relations

__all__ = ["ConsolidationReport", "consolidate_domain"]


class ConsolidationReport(BaseModel):
    domain: str
    theses_created: int
    thesis_ids: list[uuid.UUID]


async def consolidate_domain(
    session: AsyncSession,
    *,
    domain: str,
    pack: DomainPack,
    min_strength: float = 0.6,
    min_cluster_size: int = 2,
    created_by_tier: str = "t3",
    dry_run: bool = False,
) -> ConsolidationReport:
    """Run thesis synthesis for a domain; shape results into a consolidation report."""
    _ = pack
    theses = await synthesize_theses_from_relations(
        session,
        domain=domain,
        min_strength=min_strength,
        min_cluster_size=min_cluster_size,
        created_by_tier=created_by_tier,
        dry_run=dry_run,
    )
    return ConsolidationReport(
        domain=domain,
        theses_created=len(theses),
        thesis_ids=[t.id for t in theses],
    )
