"""S8 — fit confidence→P(match) calibration from existing eval data."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from app.db.session import make_engine, make_session_factory
from app.evaluation.confidence_calibration import (
    collect_calibration_pairs,
    fit_and_summarize,
    save_calibration,
)

OUT = Path(__file__).resolve().parents[1] / "evals" / "confidence_calibration.json"


async def main() -> int:
    sf = make_session_factory(make_engine("postgresql+asyncpg://nexus:nexus@localhost:55432/nexus"))
    async with sf() as session:
        pairs = await collect_calibration_pairs(session)
        summary = fit_and_summarize(pairs)

    save_calibration(summary, OUT)
    print(json.dumps(summary, indent=2))
    print(f"\nSaved → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
