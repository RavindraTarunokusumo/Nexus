"""S4 — claim canonicalization.

Group claims that assert the same underlying fact (even when phrased differently
or extracted from different documents) by:

  1. Normalizing entity strings (lowercase, strip punctuation, alias resolution).
  2. Computing a per-claim signature: (claim_type, sorted_entity_tuple, date_anchor).
  3. Clustering claims by signature; the first-seen claim becomes the "canonical"
     and others get canonical_claim_id pointing to it.

This is a deterministic batch job — no LLM calls. It can be re-run idempotently
to absorb new claims into existing canonical clusters.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Iterable

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Claim

# Minimal alias table — extend as we observe more variants.
_ENTITY_ALIASES: dict[str, str] = {
    "openai": "OpenAI",
    "open ai": "OpenAI",
    "anthropic": "Anthropic",
    "anthropic pbc": "Anthropic",
    "google": "Google",
    "google deepmind": "Google DeepMind",
    "deepmind": "Google DeepMind",
    "meta": "Meta",
    "meta ai": "Meta",
    "meta platforms": "Meta",
    "microsoft": "Microsoft",
    "msft": "Microsoft",
    "xai": "xAI",
    "x ai": "xAI",
    "mistral": "Mistral AI",
    "mistral ai": "Mistral AI",
    "hugging face": "Hugging Face",
    "huggingface": "Hugging Face",
    "deepseek": "DeepSeek",
    "deep seek": "DeepSeek",
}


def normalize_entity(raw: str) -> str:
    """Lowercase, strip punctuation/whitespace, resolve via alias table."""
    s = re.sub(r"[^a-z0-9 ]", "", raw.lower()).strip()
    if not s:
        return raw.strip()
    return _ENTITY_ALIASES.get(s, raw.strip())


def extract_date_anchor(claim_text: str) -> str | None:
    """Extract the most specific date-like anchor from a claim, normalized.

    Priority: full date (March 12, 2025) > month + year (March 2025) > year (2025).
    Returns ISO-ish string or None.
    """
    full = re.search(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2}),?\s+(\d{4})",
        claim_text,
        re.IGNORECASE,
    )
    if full:
        return f"{full.group(3)}-{_month_num(full.group(1))}-{int(full.group(2)):02d}"
    month_year = re.search(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})",
        claim_text,
        re.IGNORECASE,
    )
    if month_year:
        return f"{month_year.group(2)}-{_month_num(month_year.group(1))}"
    year = re.search(r"\b(20\d{2})\b", claim_text)
    if year:
        return year.group(1)
    return None


def _month_num(m: str) -> str:
    return {
        "jan": "01",
        "feb": "02",
        "mar": "03",
        "apr": "04",
        "may": "05",
        "jun": "06",
        "jul": "07",
        "aug": "08",
        "sep": "09",
        "oct": "10",
        "nov": "11",
        "dec": "12",
    }[m.lower()[:3]]


def claim_signature(
    claim_type: str,
    entities: Iterable[str],
    claim_text: str,
) -> tuple[str, tuple[str, ...], str | None]:
    """Build a deterministic signature used for clustering near-duplicate claims."""
    norm_entities = tuple(sorted({normalize_entity(e) for e in entities if e}))
    return (claim_type, norm_entities, extract_date_anchor(claim_text))


async def canonicalize(session: AsyncSession, *, dry_run: bool = False) -> dict:
    """Cluster all claims by signature and attach canonical_claim_id to non-canonical members.

    Returns a stats dict: {clusters_total, claims_reassigned, claims_canonical}.
    """
    res = await session.execute(select(Claim).order_by(Claim.created_at))
    claims = res.scalars().all()

    buckets: dict[tuple, list[Claim]] = defaultdict(list)
    for c in claims:
        entities = []
        if c.entities_json:
            if isinstance(c.entities_json, list):
                entities = c.entities_json
            elif isinstance(c.entities_json, dict) and "entities" in c.entities_json:
                entities = c.entities_json["entities"]
        sig = claim_signature(c.claim_type, entities, c.claim_text)
        buckets[sig].append(c)

    reassigned = 0
    canonical_count = 0
    for sig, members in buckets.items():
        if not members:
            continue
        canonical = members[0]
        canonical_count += 1
        for m in members[1:]:
            if m.canonical_claim_id != canonical.id:
                if not dry_run:
                    await session.execute(
                        update(Claim)
                        .where(Claim.id == m.id)
                        .values(canonical_claim_id=canonical.id)
                    )
                reassigned += 1

    if not dry_run:
        await session.commit()

    return {
        "clusters_total": len(buckets),
        "claims_canonical": canonical_count,
        "claims_reassigned": reassigned,
    }


async def supersede_check(session: AsyncSession, *, dry_run: bool = False) -> dict:
    """S9 helper — within each canonical cluster, mark older claims as superseded by the newest.

    Uses created_at as the recency signal. The newest claim per cluster is the
    active one; older claims get superseded_by set to the newest's id.
    """
    res = await session.execute(select(Claim).order_by(Claim.created_at.desc()))
    claims = res.scalars().all()

    by_canon: dict[uuid.UUID, list[Claim]] = defaultdict(list)
    for c in claims:
        key = c.canonical_claim_id or c.id
        by_canon[key].append(c)

    superseded = 0
    for _key, members in by_canon.items():
        if len(members) <= 1:
            continue
        members.sort(key=lambda c: c.created_at, reverse=True)
        newest = members[0]
        for older in members[1:]:
            if older.superseded_by != newest.id:
                if not dry_run:
                    await session.execute(
                        update(Claim)
                        .where(Claim.id == older.id)
                        .values(superseded_by=newest.id)
                    )
                superseded += 1

    if not dry_run:
        await session.commit()
    return {"superseded_count": superseded}
