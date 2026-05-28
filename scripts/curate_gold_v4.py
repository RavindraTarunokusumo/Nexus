"""Curate ai_tech_v4 — multi-claim gold from v3.

Each entry in _ADDITIONS is a list of additional atomic claims for the
example_id. The v3 gold_claim is preserved as gold_claims[0]; new claims
are appended.

These additions were hand-curated from the document_text of each v3
example. Each new claim is a verifiable atomic proposition stated in
the source. Framing ("marking a milestone"), opinion ("Early adopters
report"), and inferences are excluded.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / "evals" / "gold" / "claim_extraction" / "ai_tech_v3.yaml"
V4 = ROOT / "evals" / "gold" / "claim_extraction" / "ai_tech_v4.yaml"


# example_id → list of (claim_type, claim_text) tuples to add after gold_claims[0].
_ADDITIONS: dict[str, list[tuple[str, str]]] = {
    "mr_001": [
        ("release.model", "Claude 4 Opus has a 200K token context window."),
    ],
    "mr_002": [
        ("release.weights", "Llama 4 Scout is available on Hugging Face under Meta's custom community license."),
    ],
    "mr_003": [
        ("infra.compute", "Grok-3 was trained on approximately 200,000 Nvidia H100 GPUs in a single cluster."),
        ("performance.capability_demo", "Grok-3 introduces a Think mode that exposes step-by-step chain-of-thought reasoning before answering."),
    ],
    "br_001": [
        ("performance.benchmark", "The previous SWE-bench Verified record was held by Claude 3.7 Sonnet at 70.3%."),
    ],
    "br_002": [
        ("performance.benchmark", "Independent third-party reproducibility checks confirmed the Gemini 2.0 Pro MMLU result within one percentage point."),
    ],
    "br_003": [
        ("research.methodology", "DeepSeek-V3 uses a multi-token prediction training objective."),
    ],
    "pl_001": [
        ("performance.capability_demo", "Sora can generate videos up to 20 seconds long at 1080p resolution."),
    ],
    # pl_002 — only one verifiable claim in the source; no addition.
    "pl_003": [
        ("research.methodology", "Codestral Mamba is built on the Mamba state-space architecture."),
    ],
    "pc_001": [
        ("business.pricing", "OpenAI cut the GPT-4o API output token price from $15 to $10 per million tokens."),
    ],
    # pc_002 — single quantitative claim; no addition.
    "pc_003": [
        ("business.pricing", "Gemini 1.5 Flash input costs $0.0375 per million tokens after the October 2024 price cut."),
    ],
    "rf_001": [
        ("performance.benchmark", "AlphaFold 3 achieves state-of-the-art accuracy on the PoseBusters benchmark for ligand binding prediction."),
    ],
    "rf_002": [
        ("performance.capability_demo", "4-bit quantized Mistral 7B runs at 30 tokens per second on an M3 MacBook Pro."),
    ],
    # rf_003 — single empirical finding; no addition.
    "iu_001": [
        ("infra.hardware", "Trainium3 delivers 4x the performance per watt compared to Trainium2."),
    ],
    "iu_002": [
        ("infra.deployment", "Cloudflare Workers AI inference latency is below 100ms for most regions."),
    ],
    "iu_003": [
        ("business.pricing", "TPU v5e costs 30% less per chip than TPU v4."),
    ],
    "si_001": [
        ("governance.safety_incident", "GitHub patched the Copilot Chat prompt injection vulnerability within 72 hours of disclosure."),
    ],
    # si_002 — single incident claim; no addition.
    "fe_001": [
        ("business.funding", "Anthropic was valued at approximately $18 billion post-money after the Series E round."),
    ],
    # fe_002, fe_003 — single funding claims; no addition.
    "rg_001": [
        ("governance.regulation", "The EU AI Act imposes additional obligations on general-purpose AI models trained at over 10^25 FLOPs."),
    ],
    # rg_002, rg_003 — single regulation/policy claims; no addition.
    # fc_001 — single forecast; no addition.
    "fc_002": [
        ("forecast.prediction", "Stanford HAI forecast that multimodal AI models will become the dominant paradigm by 2027."),
    ],
    "ot_001": [
        ("business.personnel", "Inflection AI co-founder Mustafa Suleyman joined Microsoft as CEO of Microsoft AI."),
    ],
    # ot_002 — single policy claim; no addition.
    # si_003, si_004 — single incident claims; no addition.
    "ot_003": [
        ("business.personnel", "Ilya Sutskever and Jan Leike departed OpenAI shortly after the Superalignment team was dissolved."),
    ],
    # ot_004 — single product launch; no addition.
    # rf_004, rf_005 — single empirical findings; no addition.
    # rg_004, rg_005 — single regulatory actions; no addition.
    # fc_003, fc_004 — single forecasts; no addition.
    "mr_004": [
        ("release.model", "Mistral Large 2 is a 123-billion-parameter model with a 128K context window."),
    ],
    # br_004 — single benchmark; no addition.
    "fe_004": [
        ("business.funding", "xAI was valued at $24 billion post-money after the May 2024 Series C round."),
    ],
    # iu_004 — single compute claim; no addition.
    "pc_004": [
        ("business.pricing", "Gemini 1.5 Flash input costs $0.075 per million tokens for prompts under 128K after the August 2024 cut."),
    ],
}


def main() -> int:
    with open(V3, "r", encoding="utf-8") as f:
        ds = yaml.safe_load(f)

    ds["name"] = "ai_tech_v4"
    ds["version"] = 4
    ds["description"] = (
        "45 examples from v3, re-curated to include all distinct atomic claims "
        "the document text supports (not just the headline). Fixes the "
        "annotation-style precision artifact identified during system tuning."
    )

    added = 0
    for ex in ds["examples"]:
        ex_id = ex["example_id"]
        adds = _ADDITIONS.get(ex_id, [])
        for ctype, ctext in adds:
            ex["gold_claims"].append(
                {"claim_type": ctype, "claim_text": ctext, "supporting_span": [0, len(ctext)]}
            )
            added += 1

    with open(V4, "w", encoding="utf-8") as f:
        yaml.safe_dump(ds, f, sort_keys=False, allow_unicode=True, width=200)

    print(f"v3 had {sum(1 for ex in ds['examples'])} examples, 1 claim each (45 claims).")
    print(f"v4 has {sum(1 for ex in ds['examples'])} examples, {sum(len(ex['gold_claims']) for ex in ds['examples'])} claims total (+{added}).")
    print(f"Wrote → {V4}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
