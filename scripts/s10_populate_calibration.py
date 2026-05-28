"""S10 — populate empty judge_match_status/judge_groundedness in calibration YAML.

Reads the gold dataset to get document_text per example_id, then invokes the
current judge on each (gold_claim, pred_claim) pair from the labels file,
writes the verdict back into the YAML in-place, and prints kappa.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import yaml

from app.config import settings as app_settings
from app.db.session import make_engine, make_session_factory
from app.evaluation.judges import ClaimExtractionJudge
from app.evaluation.meta_eval import compute_kappa, compute_pearson
from app.intelligence.llm_client import LLMClient

ROOT = Path(__file__).resolve().parents[1]
GOLD_PATH = ROOT / "evals" / "gold" / "claim_extraction" / "ai_tech_v1.yaml"
LABELS_PATH = ROOT / "evals" / "human_labels" / "claim_extraction.yaml"


async def main() -> int:
    with open(GOLD_PATH, "r", encoding="utf-8") as f:
        gold_ds = yaml.safe_load(f)
    docs = {ex["example_id"]: ex["document_text"].strip() for ex in gold_ds["examples"]}
    gold_claim_by_ex: dict[str, dict] = {
        ex["example_id"]: ex["gold_claims"][0] for ex in gold_ds["examples"]
    }

    with open(LABELS_PATH, "r", encoding="utf-8") as f:
        labels_doc = yaml.safe_load(f)

    sf = make_session_factory(
        make_engine("postgresql+asyncpg://nexus:nexus@localhost:55432/nexus")
    )
    llm = LLMClient(api_key=app_settings.openrouter_api_key, session_factory=sf)
    judge = ClaimExtractionJudge(model=app_settings.t3_model, llm_client=llm)

    updated = 0
    for lbl in labels_doc["labels"]:
        if lbl.get("judge_match_status"):
            continue
        ex_id = lbl["example_id"]
        doc_text = docs.get(ex_id, "")
        gold_claim = gold_claim_by_ex.get(ex_id) or {
            "claim_text": lbl["gold_claim_text"],
            "claim_type": "other",
        }
        if lbl["pred_claim_text"]:
            pred_claim = {"claim_text": lbl["pred_claim_text"], "claim_type": "other"}
        else:
            pred_claim = None  # type: ignore[assignment]

        verdict, _tokens = await judge._judge_pair(doc_text, gold_claim, pred_claim)
        lbl["judge_match_status"] = verdict["match_status"]
        lbl["judge_groundedness"] = round(float(verdict["groundedness"]), 3)
        updated += 1
        print(
            f"{lbl['pair_id']} {ex_id}: "
            f"human={lbl['human_match_status']:<8} judge={verdict['match_status']:<8} "
            f"g_h={lbl['human_groundedness']} g_j={lbl['judge_groundedness']}"
        )

    with open(LABELS_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(labels_doc, f, sort_keys=False, allow_unicode=True)
    print(f"Wrote {updated} verdicts to {LABELS_PATH}")

    judge_vals = [lbl["judge_match_status"] for lbl in labels_doc["labels"]]
    human_vals = [lbl["human_match_status"] for lbl in labels_doc["labels"]]
    kappa = compute_kappa(judge_vals, human_vals)

    judge_gnd = [
        float(lbl["judge_groundedness"])
        for lbl in labels_doc["labels"]
        if lbl["judge_groundedness"] is not None
    ]
    human_gnd = [
        float(lbl["human_groundedness"])
        for lbl in labels_doc["labels"]
        if lbl["human_groundedness"] is not None
    ]
    r = compute_pearson(judge_gnd, human_gnd) if len(judge_gnd) > 1 else None

    print()
    print(f"match_status_kappa = {kappa:.4f}")
    if r is not None:
        print(f"groundedness_pearson_r = {r:.4f}")
    print("Recommendation:", "PASS" if kappa >= 0.6 else "FAIL")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
