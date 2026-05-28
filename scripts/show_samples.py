"""Pretty-print system-vs-gold for a handful of examples from a finished run."""
from __future__ import annotations

import asyncio
import sys
import uuid

import yaml
from sqlalchemy import select

from app.db.models import EvalResult
from app.db.session import make_engine, make_session_factory


PICKS = ["mr_001", "br_001", "rg_001", "si_001", "ot_002", "fc_001"]


async def main(run_id_str: str, dataset_path: str) -> int:
    sf = make_session_factory(
        make_engine("postgresql+asyncpg://nexus:nexus@localhost:55432/nexus")
    )
    run_id = uuid.UUID(run_id_str)

    with open(dataset_path, "r", encoding="utf-8") as f:
        gold = yaml.safe_load(f)
    ex_by_id = {ex["example_id"]: ex for ex in gold["examples"]}

    async with sf() as session:
        res = await session.execute(
            select(EvalResult)
            .where(EvalResult.run_id == run_id)
            .where(EvalResult.example_id.in_(PICKS))
        )
        rows = {r.example_id: r for r in res.scalars().all()}

    for ex_id in PICKS:
        ex = ex_by_id.get(ex_id)
        r = rows.get(ex_id)
        if not ex or not r:
            continue
        print("=" * 78)
        print(f"[{ex_id}]  status={r.status}")
        print("-" * 78)
        print("DOCUMENT:")
        print(f"  {ex['document_text'].strip()}")
        print()
        print("GOLD CLAIMS:")
        for g in ex["gold_claims"]:
            print(f"  - type: {g['claim_type']}")
            print(f"    text: {g['claim_text']}")
        print()
        print("SYSTEM PREDICTIONS:")
        sut = r.sut_output or {}
        for p in (sut.get("claims") or []):
            print(f"  - type: {p.get('claim_type')}  conf: {p.get('confidence')}")
            print(f"    text: {p.get('claim_text')}")
        print()
        print("METRICS:")
        m = r.deterministic_metrics or {}
        for k in ("precision", "recall", "f1", "type_accuracy"):
            print(f"  {k}: {m.get(k)}")
        verdict = r.judge_verdict or {}
        per_pair = verdict.get("per_pair_verdicts") or []
        if per_pair:
            print("JUDGE PER-PAIR:")
            for pp in per_pair:
                print(
                    f"  match={pp.get('match_status'):<8} type_correct={pp.get('type_correct')}  "
                    f"groundedness={pp.get('groundedness')}"
                )
                rat = pp.get("rationale", "")
                if rat:
                    print(f"    rationale: {rat[:140]}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1], sys.argv[2])))
