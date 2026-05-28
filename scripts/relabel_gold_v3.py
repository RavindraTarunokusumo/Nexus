"""Relabel ai_tech_v2 (legacy 11-type) → ai_tech_v3 (taxonomy v2 dotted).

Uses legacy_to_new() from app/intelligence/taxonomy for the deterministic
cases. The 4 'other' examples and the 'infrastructure_update' cases that
look like deployment are handled with hand-coded special cases.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from app.intelligence.taxonomy import is_valid, legacy_to_new

ROOT = Path(__file__).resolve().parents[1]
V2_PATH = ROOT / "evals" / "gold" / "claim_extraction" / "ai_tech_v2.yaml"
V3_PATH = ROOT / "evals" / "gold" / "claim_extraction" / "ai_tech_v3.yaml"


# Manual reclassification for examples that the deterministic mapper can't
# resolve (legacy 'other') or that warrant a more specific subtype than the
# default mapping provides.
#
# Format: example_id → new dotted type
_MANUAL: dict[str, str] = {
    # Legacy 'other' — must be reclassified.
    "ot_001": "business.acquisition",  # "Inflection AI wound down ... most staff moving to Microsoft" → acqui-hire
    "ot_002": "governance.policy",  # "Character.AI announced a content moderation overhaul" → vendor policy
    "ot_003": "business.personnel",  # "OpenAI dissolved its Superalignment team ... departures" → org/personnel
    "ot_004": "release.product",  # "Linux Foundation launched the Open Platform for Enterprise AI" → product
    # Infrastructure examples that are really deployment, not raw compute.
    "iu_002": "infra.deployment",  # "Cloudflare extended Workers AI ... edge ... 100ms latency"
    # Research subtype refinements.
    "rf_001": "research.methodology",  # If this example talks about a new training method (default empirical otherwise)
    "rf_004": "research.empirical",  # "frontier reasoning models collapse" — empirical observation
    "rf_005": "research.empirical",  # AlphaProof IMO score — empirical demonstration
}


def main() -> int:
    with open(V2_PATH, "r", encoding="utf-8") as f:
        ds = yaml.safe_load(f)

    ds["name"] = "ai_tech_v3"
    ds["version"] = 3
    ds["description"] = (
        "45 hand-curated AI/tech news examples — taxonomy v2 (dotted "
        "'<category>.<subtype>'). Re-labeled from ai_tech_v2 via the deterministic "
        "legacy mapper + manual reclassification for 'other' and ambiguous cases."
    )

    skipped = 0
    relabeled = 0
    unresolved: list[str] = []
    for ex in ds["examples"]:
        ex_id = ex["example_id"]
        for gc in ex["gold_claims"]:
            old = gc["claim_type"]
            if ex_id in _MANUAL:
                new = _MANUAL[ex_id]
            else:
                new = legacy_to_new(old)
            if new is None:
                unresolved.append(f"{ex_id} ({old})")
                continue
            if not is_valid(new):
                print(f"WARN: invalid new type {new!r} for {ex_id}", file=sys.stderr)
                continue
            if new == old:
                skipped += 1
            else:
                gc["claim_type"] = new
                relabeled += 1

    if unresolved:
        print("UNRESOLVED (need manual mapping):", *unresolved, sep="\n  ", file=sys.stderr)
        return 1

    with open(V3_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(ds, f, sort_keys=False, allow_unicode=True, width=200)

    print(f"Relabeled {relabeled} claims; skipped {skipped} (already matched).")
    print(f"Wrote → {V3_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
