"""S4 demo — exercise canonicalization on synthetic claim rows.

The eval framework persists predictions to eval_results.sut_output, not the
main claims table, so we seed a few synthetic Claim rows representing the same
fact phrased differently and across different documents, then run the
canonicalization job and supersede check.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.db.models import Claim, Document, Source
from app.db.session import make_engine, make_session_factory
from app.intelligence.canonicalization import (
    canonicalize,
    claim_signature,
    supersede_check,
)

SYNTHETIC = [
    # Same fact, three phrasings, three different docs, different dates.
    {
        "text": "Anthropic released Claude 4 Opus on March 12, 2025.",
        "type": "model_release",
        "entities": ["Anthropic", "Claude 4 Opus"],
        "days_ago": 200,
    },
    {
        "text": "On March 12, 2025, anthropic launched Claude 4 Opus.",  # alias variant
        "type": "model_release",
        "entities": ["anthropic", "Claude 4 Opus"],
        "days_ago": 195,
    },
    {
        "text": "Anthropic PBC shipped Claude 4 Opus in March 2025.",
        "type": "model_release",
        "entities": ["Anthropic PBC", "Claude 4 Opus"],
        "days_ago": 100,  # newer
    },
    # Different fact in same cluster (different model)
    {
        "text": "OpenAI released GPT-5 on April 3, 2026.",
        "type": "model_release",
        "entities": ["OpenAI", "GPT-5"],
        "days_ago": 60,
    },
    # Same entities, different type → different cluster
    {
        "text": "OpenAI raised $40B in funding in October 2025.",
        "type": "funding_event",
        "entities": ["OpenAI"],
        "days_ago": 200,
    },
]


async def main() -> int:
    sf = make_session_factory(make_engine("postgresql+asyncpg://nexus:nexus@localhost:55432/nexus"))

    # 0) Demonstrate the signature builder
    print("=== signature samples ===")
    for s in SYNTHETIC:
        sig = claim_signature(s["type"], s["entities"], s["text"])
        print(f"  {s['text'][:60]:<62}  → {sig}")
    print()

    async with sf() as session:
        # Clean prior demo rows.
        await session.execute(
            delete(Claim).where(Claim.claim_text.in_([s["text"] for s in SYNTHETIC]))
        )
        await session.commit()

        # Need a source + document.
        src = (await session.execute(select(Source).limit(1))).scalar_one_or_none()
        if src is None:
            src = Source(
                id=uuid.uuid4(),
                name="canonicalization-demo",
                source_type="manual",
            )
            session.add(src)
            await session.flush()

        # One document per synthetic claim to simulate cross-doc.
        now = datetime.now(timezone.utc)
        created_ids: list[uuid.UUID] = []
        for i, s in enumerate(SYNTHETIC):
            doc = Document(
                id=uuid.uuid4(),
                source_id=src.id,
                title=f"demo-{i}",
                content_hash=f"demo-{uuid.uuid4().hex[:12]}-{i}",
                status="claims_extracted",
            )
            session.add(doc)
            await session.flush()
            claim = Claim(
                id=uuid.uuid4(),
                document_id=doc.id,
                claim_text=s["text"],
                claim_type=s["type"],
                entities_json=s["entities"],
                topics_json=[],
                confidence=0.9,
                created_at=now - timedelta(days=s["days_ago"]),
            )
            session.add(claim)
            created_ids.append(claim.id)
        await session.commit()

        # 1) Run canonicalization.
        stats = await canonicalize(session)
        print(f"=== canonicalize() → {stats} ===\n")

        # 2) Run supersede check.
        supstats = await supersede_check(session)
        print(f"=== supersede_check() → {supstats} ===\n")

        # 3) Print resulting clusters.
        res = await session.execute(
            select(Claim).where(Claim.id.in_(created_ids)).order_by(Claim.created_at)
        )
        for c in res.scalars().all():
            canon = "self" if c.canonical_claim_id is None else str(c.canonical_claim_id)[:8]
            sup = "—" if c.superseded_by is None else str(c.superseded_by)[:8]
            print(
                f"  [{str(c.id)[:8]}] canon={canon}  superseded_by={sup}  "
                f"created={c.created_at.date()}  text={c.claim_text[:50]!r}"
            )

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
