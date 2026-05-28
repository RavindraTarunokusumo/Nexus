"""GLiNER2 smoke test — load the model and run extract_json on one example."""
from __future__ import annotations

import json
import sys
import time

from gliner2 import GLiNER2


SAMPLE = (
    "Anthropic released Claude 4 Opus on March 12, 2025, marking a significant "
    "milestone for the company. The new model features a 200K token context "
    "window and improved reasoning capabilities over its predecessor. Early "
    "benchmarks suggest it outperforms GPT-4o on several coding and analysis tasks."
)


def main() -> int:
    print("Loading fastino/gliner2-base-v1 …", file=sys.stderr)
    t0 = time.perf_counter()
    model = GLiNER2.from_pretrained("fastino/gliner2-base-v1")
    print(f"  loaded in {time.perf_counter() - t0:.1f}s", file=sys.stderr)

    print("\n--- extract_entities ---")
    t0 = time.perf_counter()
    ents = model.extract_entities(SAMPLE, ["company", "model", "date", "metric"])
    print(json.dumps(ents, indent=2))
    print(f"  ({time.perf_counter() - t0:.2f}s)", file=sys.stderr)

    print("\n--- extract_json: claim schema ---")
    schema = {
        "claim": [
            "claim_text::str::An atomic factual proposition stated by the text",
            "claim_type::str::Type label such as release.model or performance.benchmark",
            "entities::list[str]::Named entities mentioned in this specific claim",
        ]
    }
    t0 = time.perf_counter()
    out = model.extract_json(SAMPLE, schema)
    print(json.dumps(out, indent=2))
    print(f"  ({time.perf_counter() - t0:.2f}s)", file=sys.stderr)

    print("\n--- classify_text: claim_type over candidate ---")
    if isinstance(out, dict):
        items = out.get("claim") or []
        if items:
            first_text = items[0].get("claim_text", "")
            t0 = time.perf_counter()
            cls = model.classify_text(
                first_text,
                {
                    "claim_type": [
                        "release.model", "release.product", "release.dataset", "release.weights",
                        "performance.benchmark", "performance.capability_demo", "performance.safety_eval",
                        "research.methodology", "research.theoretical", "research.empirical", "research.replication",
                        "infra.compute", "infra.hardware", "infra.deployment",
                        "business.funding", "business.pricing", "business.partnership", "business.acquisition", "business.personnel",
                        "governance.regulation", "governance.policy", "governance.safety_incident",
                        "forecast.prediction", "forecast.roadmap_commitment",
                    ]
                },
            )
            print(f"  '{first_text[:80]}' → {cls}")
            print(f"  ({time.perf_counter() - t0:.2f}s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
