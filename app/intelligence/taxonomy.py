"""AI-research claim taxonomy v2.

Replaces the legacy flat 11-type enum with a two-level taxonomy:
7 categories, 23 subtypes. Encoded as a dotted string "<category>.<subtype>".

The single source of truth is `CATEGORIES`. Everything else (`ALL_TYPES`,
`Literal`, `legacy_to_new`) is derived from it.

Design rules:
  - No `other` bucket. The model is instructed to pick the closest category.
  - Category is the first decision; subtype the second. This lets us score
    category-level accuracy (typically easier) and subtype accuracy (harder).
  - Subtype names are local to their category — e.g., `model` under `release`
    is distinct from any other `model`.
"""

from __future__ import annotations

from typing import Final

CATEGORIES: Final[dict[str, dict[str, str]]] = {
    "release": {
        "model": "A specific AI/ML model released, launched, announced, or shipped (any modality).",
        "product": "A non-model product, feature, app, agent, IDE, or SDK released or launched.",
        "dataset": "A training set, benchmark, or evaluation set released or published.",
        "weights": "Model weights of a previously closed or new model made publicly available.",
    },
    "performance": {
        "benchmark": "A model achieves a measurable score on a named public benchmark.",
        "capability_demo": "A working demonstration that proves a capability, not tied to a named benchmark.",
        "safety_eval": "A safety/robustness/jailbreak/red-team finding — rate, severity, or category.",
    },
    "research": {
        "methodology": "A novel training method, architecture, optimization technique, or recipe.",
        "theoretical": "A scaling law, emergence, generalization bound, or other theoretical result.",
        "empirical": "An interpretability, behavioral, or measurement result not falling above.",
        "replication": "An independent reproduction or refutation of a prior published result.",
    },
    "infra": {
        "compute": "Cluster size, GPU/TPU count, datacenter build, training-run scale.",
        "hardware": "A new chip, accelerator, or hardware platform announcement.",
        "deployment": "Latency, throughput, region availability, or production-deployment change.",
    },
    "business": {
        "funding": "Investment round, valuation, IPO, or major financial event.",
        "pricing": "API pricing, subscription cost, token cost, or commercial-terms change.",
        "partnership": "Distribution deal, cloud-provider deal, integration, or strategic alliance.",
        "acquisition": "M&A, acqui-hire, or talent acquisition of a whole team.",
        "personnel": "Key individual hire or departure (named person, named role).",
    },
    "governance": {
        "regulation": "Law, executive order, agency rule, court ruling, or compliance requirement.",
        "policy": "Vendor policy, voluntary commitment, code of conduct, or terms-of-service change.",
        "safety_incident": "Vulnerability, breach, jailbreak in production, exfiltration, or harm event.",
    },
    "forecast": {
        "prediction": "A dated prediction or projection from an analyst, leader, or researcher.",
        "roadmap_commitment": "A vendor public commitment to a future feature, model, or date.",
    },
}


def _all_types() -> tuple[str, ...]:
    return tuple(f"{cat}.{sub}" for cat, subs in CATEGORIES.items() for sub in subs)


ALL_TYPES: Final[tuple[str, ...]] = _all_types()
ALL_CATEGORIES: Final[tuple[str, ...]] = tuple(CATEGORIES.keys())


# Deterministic mapping from the legacy 11-type vocabulary to the new dotted form.
# `other` is intentionally not mapped — it must be reclassified by hand.
_LEGACY_MAP: Final[dict[str, str]] = {
    "model_release": "release.model",
    "benchmark_result": "performance.benchmark",
    "product_launch": "release.product",
    "pricing_change": "business.pricing",
    "research_finding": "research.empirical",
    "infrastructure_update": "infra.compute",
    "security_issue": "governance.safety_incident",
    "funding_event": "business.funding",
    "regulation": "governance.regulation",
    "forecast": "forecast.prediction",
}


def legacy_to_new(legacy_type: str) -> str | None:
    """Return new dotted type for a legacy type, or None if it needs manual review."""
    return _LEGACY_MAP.get(legacy_type)


def split_type(dotted: str) -> tuple[str, str]:
    """Split 'category.subtype' → (category, subtype). Raises ValueError if malformed."""
    if "." not in dotted:
        raise ValueError(f"Type must be 'category.subtype' form, got: {dotted!r}")
    cat, sub = dotted.split(".", 1)
    return cat, sub


def is_valid(dotted: str) -> bool:
    if "." not in dotted:
        return False
    cat, sub = dotted.split(".", 1)
    return cat in CATEGORIES and sub in CATEGORIES[cat]


def category_of(dotted: str) -> str:
    """Return the top-level category for a dotted type, or '' if unknown."""
    cat, _ = split_type(dotted) if "." in dotted else ("", "")
    return cat if cat in CATEGORIES else ""
