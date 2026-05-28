"""Per-type slice for a finished eval run (taxonomy v2-aware)."""

from __future__ import annotations

import asyncio
import sys
import uuid
from collections import defaultdict

import yaml
from sqlalchemy import select

from app.db.models import EvalResult
from app.db.session import make_engine, make_session_factory


async def main(run_id_str: str, dataset_path: str) -> int:
    sf = make_session_factory(make_engine("postgresql+asyncpg://nexus:nexus@localhost:55432/nexus"))
    run_id = uuid.UUID(run_id_str)

    with open(dataset_path, "r", encoding="utf-8") as f:
        gold = yaml.safe_load(f)
    type_by_ex = {ex["example_id"]: ex["gold_claims"][0]["claim_type"] for ex in gold["examples"]}

    async with sf() as session:
        res = await session.execute(select(EvalResult).where(EvalResult.run_id == run_id))
        rows = res.scalars().all()

    by_subtype: dict = defaultdict(lambda: {"n": 0, "p": [], "r": [], "f": [], "ta": []})
    by_category: dict = defaultdict(lambda: {"n": 0, "p": [], "r": [], "f": [], "ta": []})
    for row in rows:
        ct = type_by_ex.get(row.example_id, "?")
        cat = ct.split(".", 1)[0] if "." in ct else ct
        m = row.deterministic_metrics or {}
        for tgt, key in ((by_subtype, ct), (by_category, cat)):
            b = tgt[key]
            b["n"] += 1
            if m:
                b["p"].append(m.get("precision", 0))
                b["r"].append(m.get("recall", 0))
                b["f"].append(m.get("f1", 0))
                b["ta"].append(m.get("type_accuracy", 0))

    avg = lambda xs: round(sum(xs) / len(xs), 3) if xs else 0
    for title, agg in (("CATEGORY", by_category), ("SUBTYPE", by_subtype)):
        print(f"\n=== by {title} ===")
        print(f"{'type':<32}{'n':>3}{'P':>8}{'R':>8}{'F1':>8}{'type':>8}")
        print("-" * 70)
        for k in sorted(agg, key=lambda x: -agg[x]["n"]):
            a = agg[k]
            print(
                f"{k:<32}{a['n']:>3}{avg(a['p']):>8}{avg(a['r']):>8}{avg(a['f']):>8}{avg(a['ta']):>8}"
            )
    return 0


if __name__ == "__main__":
    run_id = sys.argv[1]
    dataset = sys.argv[2]
    sys.exit(asyncio.run(main(run_id, dataset)))
