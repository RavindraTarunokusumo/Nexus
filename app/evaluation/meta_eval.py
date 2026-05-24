# app/evaluation/meta_eval.py
"""Judge calibration — Cohen's κ and Pearson r between judge and human labels."""

from __future__ import annotations

import math
from pathlib import Path

import yaml


def load_human_labels(path: Path) -> list[dict]:
    """Load human-labeled (example_id, judge_verdict, human_verdict) triples."""
    if not path.exists():
        raise FileNotFoundError(f"Human labels file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data.get("labels", [])


def compute_kappa(judge_labels: list[str], human_labels: list[str]) -> float:
    """Compute Cohen's κ for two categorical label sequences.

    κ < 0.4 → poor agreement (rewrite the rubric).
    κ 0.4–0.6 → moderate agreement.
    κ ≥ 0.6 → substantial agreement (trust the judge for gating decisions).
    """
    if len(judge_labels) != len(human_labels):
        raise ValueError(
            f"Label lists must be the same length: {len(judge_labels)} vs {len(human_labels)}"
        )
    n = len(judge_labels)
    if n == 0:
        return 0.0

    categories = list(set(judge_labels) | set(human_labels))

    # Observed agreement
    po = sum(j == h for j, h in zip(judge_labels, human_labels, strict=False)) / n

    # Expected agreement by chance
    pe = sum((judge_labels.count(c) / n) * (human_labels.count(c) / n) for c in categories)

    return (po - pe) / (1.0 - pe) if pe < 1.0 else 1.0


def compute_pearson(x: list[float], y: list[float]) -> float:
    """Pearson product-moment correlation coefficient."""
    n = len(x)
    if len(y) != n or n <= 1:
        raise ValueError("Both lists must have equal length > 1")
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y, strict=False))
    den = math.sqrt(sum((xi - mx) ** 2 for xi in x) * sum((yi - my) ** 2 for yi in y))
    return num / den if den > 0 else 0.0
