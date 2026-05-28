"""GLiNER2 smoke test v2 — per-sentence pipeline.

Use GLiNER2's strengths: entity extraction and classification.
The claim_text is the source sentence itself (verbatim quote, no rewriting).
"""
from __future__ import annotations

import json
import re
import sys
import time

from gliner2 import GLiNER2


SAMPLES = [
    (
        "mr_001",
        "Anthropic released Claude 4 Opus on March 12, 2025, marking a significant "
        "milestone for the company. The new model features a 200K token context "
        "window and improved reasoning capabilities over its predecessor. Early "
        "benchmarks suggest it outperforms GPT-4o on several coding and analysis tasks.",
    ),
    (
        "rg_001",
        "The European Union's AI Act entered into force on August 1, 2024, making "
        "it the world's first comprehensive AI regulation. The Act classifies AI "
        "systems by risk level and imposes stricter requirements on high-risk "
        "applications such as biometric surveillance and autonomous vehicles. "
        "General-purpose AI models with over 10^25 FLOPs of training compute face "
        "additional obligations.",
    ),
    (
        "si_001",
        "Security researchers at Embrace The Red disclosed a prompt injection "
        "vulnerability in GitHub Copilot Chat that allowed malicious repository "
        "content to hijack the assistant's context and exfiltrate user queries. "
        "The attack required no special permissions beyond read access to the "
        "repository. GitHub patched the vulnerability within 72 hours of disclosure.",
    ),
]

CLAIM_TYPES = [
    "release.model", "release.product", "release.dataset", "release.weights",
    "performance.benchmark", "performance.capability_demo", "performance.safety_eval",
    "research.methodology", "research.theoretical", "research.empirical", "research.replication",
    "infra.compute", "infra.hardware", "infra.deployment",
    "business.funding", "business.pricing", "business.partnership",
    "business.acquisition", "business.personnel",
    "governance.regulation", "governance.policy", "governance.safety_incident",
    "forecast.prediction", "forecast.roadmap_commitment",
]


def split_sentences(text: str) -> list[str]:
    t = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(\[])", t)
    return [p.strip() for p in parts if p.strip()]


def main() -> int:
    print("Loading model …", file=sys.stderr)
    t0 = time.perf_counter()
    model = GLiNER2.from_pretrained("fastino/gliner2-base-v1")
    print(f"  loaded in {time.perf_counter() - t0:.1f}s\n", file=sys.stderr)

    for ex_id, text in SAMPLES:
        print(f"========== {ex_id} ==========")
        sentences = split_sentences(text)
        per_doc_calls = 0
        doc_t0 = time.perf_counter()
        for sent in sentences:
            # Skip framing-only sentences via a quick classification.
            cls_claim = model.classify_text(
                sent, {"is_claim": ["yes", "no"]}
            )
            per_doc_calls += 1
            if cls_claim.get("is_claim") != "yes":
                print(f"  [skip] {sent[:80]!r}")
                continue
            # Classify type and extract entities in parallel intent.
            cls_type = model.classify_text(sent, {"claim_type": CLAIM_TYPES})
            ents = model.extract_entities(
                sent,
                ["organization", "person", "model", "product", "date", "metric", "money"],
            )
            per_doc_calls += 2
            ent_flat = [e for v in ents.get("entities", {}).values() for e in v]
            print(
                f"  [keep] type={cls_type.get('claim_type')}  "
                f"entities={ent_flat}  text={sent[:90]!r}"
            )
        doc_t = time.perf_counter() - doc_t0
        print(
            f"  → {per_doc_calls} model calls in {doc_t:.2f}s "
            f"({doc_t / per_doc_calls * 1000:.0f}ms/call avg)"
        )
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
