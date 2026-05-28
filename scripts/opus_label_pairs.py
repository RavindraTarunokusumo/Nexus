"""Use Claude Opus 4.8 as the stand-in 'human' labeller for judge calibration.

Samples (gold_claim, pred_claim) pairs from past EvalResult rows, classifies
each via Claude Opus 4.8, and writes a labels YAML that `nexus eval calibrate`
can consume.

Each row in the output gets BOTH the existing judge verdict (deepseek) and
the new opus verdict, so calibration κ = agreement between deepseek-judge
and opus-stand-in-human.

Usage:
    python scripts/opus_label_pairs.py --n 60 \
        --out evals/human_labels/claim_extraction_opus_v1.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select

from app.config import settings as app_settings
from app.db.models import EvalResult
from app.db.session import make_engine, make_session_factory
from app.evaluation.prompts.claim_extraction_judge import (
    JUDGE_SYSTEM_PROMPT,
    ClaimPairVerdict,
    build_judge_prompt,
)
from app.intelligence.llm_client import LLMClient

# Tried in order; first one OpenRouter accepts wins. Anthropic models are
# typically blocked on this account's routing — we fall back to the most
# capable non-deepseek non-judge model available (Gemini 2.5 Pro), since
# the cross-family judge already uses gemini-2.5-flash.
OPUS_CANDIDATES = [
    "anthropic/claude-opus-4.8",
    "anthropic/claude-opus-4.7",
    "anthropic/claude-sonnet-4.6",
    "anthropic/claude-haiku-4.5",
    "google/gemini-2.5-pro",
]


async def _probe_model(client: LLMClient, model: str) -> bool:
    """Quick sanity ping — does this model accept a 1-token request?"""
    try:
        await client.complete_json(
            model=model,
            system='Return JSON: {"ok": true}.',
            user="ping",
            response_model=_PingOut,
            temperature=0.0,
            max_tokens=20,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  probe {model}: FAIL ({type(exc).__name__}: {str(exc)[:120]})", file=sys.stderr)
        return False


from pydantic import BaseModel


class _PingOut(BaseModel):
    ok: bool


async def pick_opus(client: LLMClient) -> str:
    """Return the first model that successfully labels a synthetic warm-up pair.

    A previous lightweight 'ping' probe was too restrictive — Gemini returned
    empty content under a 20-token cap. Instead we attempt a real judge call
    on a tiny synthetic (gold, pred) pair.
    """
    print("Probing OpenRouter for an available labeller model …", file=sys.stderr)
    warmup_gold = {
        "claim_text": "OpenAI released GPT-5 in April 2026.",
        "claim_type": "release.model",
    }
    warmup_pred = {
        "claim_text": "OpenAI released GPT-5 in April 2026.",
        "claim_type": "release.model",
    }
    user = build_judge_prompt(
        "OpenAI released GPT-5 in April 2026, marking a milestone.",
        warmup_gold,
        warmup_pred,
    )
    for m in OPUS_CANDIDATES:
        try:
            await client.complete_json(
                model=m,
                system=JUDGE_SYSTEM_PROMPT,
                user=user,
                response_model=ClaimPairVerdict,
                temperature=0.0,
            )
            print(f"  → using {m}", file=sys.stderr)
            return m
        except Exception as exc:  # noqa: BLE001
            print(
                f"  probe {m}: FAIL ({type(exc).__name__}: {str(exc)[:120]})",
                file=sys.stderr,
            )
    raise SystemExit("No labeller model reachable via current OpenRouter routing.")


async def collect_pairs(session, n: int, seed: int) -> list[dict[str, Any]]:
    """Pull n random (example_id, gold, pred, deepseek_verdict, run_id) rows."""
    res = await session.execute(
        select(EvalResult)
        .where(EvalResult.judge_verdict.isnot(None))
        .where(EvalResult.sut_output.isnot(None))
    )
    rows = res.scalars().all()

    pairs: list[dict[str, Any]] = []
    for r in rows:
        sut = r.sut_output or {}
        verdict = r.judge_verdict or {}
        per_pair = verdict.get("per_pair_verdicts") or []
        pred_claims = sut.get("claims") or []
        for i, pp in enumerate(per_pair):
            pred = pred_claims[i] if i < len(pred_claims) else None
            pairs.append(
                {
                    "run_id": str(r.run_id),
                    "example_id": r.example_id,
                    "pair_index": i,
                    "gold_claim_text": "",  # filled below
                    "pred_claim_text": (pred or {}).get("claim_text", "") if pred else "",
                    "pred_claim_type": (pred or {}).get("claim_type", "") if pred else "",
                    "deepseek_match_status": pp.get("match_status"),
                    "deepseek_groundedness": pp.get("groundedness"),
                }
            )

    random.seed(seed)
    random.shuffle(pairs)
    return pairs[:n]


async def attach_doc_and_gold(
    session, pairs: list[dict[str, Any]], gold_path: Path
) -> list[dict[str, Any]]:
    with open(gold_path, "r", encoding="utf-8") as f:
        gold = yaml.safe_load(f)
    ex_by_id = {ex["example_id"]: ex for ex in gold["examples"]}

    enriched: list[dict[str, Any]] = []
    for p in pairs:
        ex = ex_by_id.get(p["example_id"])
        if not ex:
            continue
        gc = ex["gold_claims"][0]
        p["document_text"] = ex["document_text"].strip()
        p["gold_claim_text"] = gc["claim_text"]
        p["gold_claim_type"] = gc["claim_type"]
        enriched.append(p)
    return enriched


async def label_with_opus(
    client: LLMClient, opus_model: str, pair: dict[str, Any]
) -> dict[str, Any]:
    gold = (
        {"claim_text": pair["gold_claim_text"], "claim_type": pair["gold_claim_type"]}
        if pair["gold_claim_text"]
        else None
    )
    pred = (
        {"claim_text": pair["pred_claim_text"], "claim_type": pair["pred_claim_type"]}
        if pair["pred_claim_text"]
        else None
    )
    user = build_judge_prompt(pair["document_text"], gold, pred)
    try:
        verdict, _ = await client.complete_json(
            model=opus_model,
            system=JUDGE_SYSTEM_PROMPT,
            user=user,
            response_model=ClaimPairVerdict,
            temperature=0.0,
        )
        return verdict.model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "match_status": "error",
            "type_correct": False,
            "groundedness": 0.0,
            "factuality": 0.0,
            "rationale": f"Opus label failed: {exc}",
        }


async def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60, help="Number of pairs to label")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--gold-path",
        type=Path,
        default=Path("evals/gold/claim_extraction/ai_tech_v3.yaml"),
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("evals/human_labels/claim_extraction_opus_v1.yaml"),
    )
    args = ap.parse_args(argv)

    sf = make_session_factory(make_engine("postgresql+asyncpg://nexus:nexus@localhost:55432/nexus"))
    client = LLMClient(api_key=app_settings.openrouter_api_key, session_factory=sf)
    opus_model = await pick_opus(client)

    async with sf() as session:
        pairs = await collect_pairs(session, args.n, args.seed)
        pairs = await attach_doc_and_gold(session, pairs, args.gold_path)

    print(f"Labeling {len(pairs)} pairs with {opus_model} …", file=sys.stderr)
    labeled: list[dict[str, Any]] = []
    for i, p in enumerate(pairs):
        verdict = await label_with_opus(client, opus_model, p)
        labeled.append(
            {
                "pair_id": f"opus_{i:03d}",
                "example_id": p["example_id"],
                "run_id": p["run_id"],
                "gold_claim_text": p["gold_claim_text"] or "",
                "pred_claim_text": p["pred_claim_text"] or "",
                "human_match_status": verdict["match_status"],
                "human_groundedness": round(float(verdict["groundedness"]), 3),
                "human_factuality": round(float(verdict["factuality"]), 3),
                "judge_match_status": p["deepseek_match_status"],
                "judge_groundedness": p["deepseek_groundedness"],
            }
        )
        print(
            f"  [{i+1}/{len(pairs)}] {p['example_id']}: "
            f"opus={verdict['match_status']:<8} deepseek={p['deepseek_match_status']}",
            file=sys.stderr,
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            {"labels": labeled, "labeller_model": opus_model},
            f,
            sort_keys=False,
            allow_unicode=True,
        )
    print(f"\nWrote {len(labeled)} labeled pairs → {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
