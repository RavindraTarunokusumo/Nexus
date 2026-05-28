"""Show the new GLiNER extractor's full output for 3 sample examples,
including raw NER and canonical entity normalization."""
from __future__ import annotations

import sys

import yaml

from app.intelligence.gliner_extractor import extract_claims

SAMPLE_IDS = ["mr_001", "rg_001", "fe_001"]


def main() -> int:
    with open("evals/gold/claim_extraction/ai_tech_v3.yaml", "r", encoding="utf-8") as f:
        ds = yaml.safe_load(f)
    ex_by_id = {ex["example_id"]: ex for ex in ds["examples"]}

    for ex_id in SAMPLE_IDS:
        ex = ex_by_id[ex_id]
        print("=" * 78)
        print(f"[{ex_id}]")
        print(f"DOC: {ex['document_text'].strip()}")
        print(f"GOLD: type={ex['gold_claims'][0]['claim_type']}  text={ex['gold_claims'][0]['claim_text']!r}")
        print("-" * 78)
        claims = extract_claims(ex["document_text"])
        if not claims:
            print("  (no sentences classified as atomic_fact)")
            continue
        for c in claims:
            print(f"  claim_text: {c.claim_text}")
            print(f"  claim_type: {c.claim_type}  conf={c.confidence}")
            print(f"  sentence_role: {c.sentence_role}")
            print(f"  raw_entities:       {c.raw_entities}")
            print(f"  canonical_entities: {c.entities}")
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
