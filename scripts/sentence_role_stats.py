"""Re-run sentence role classification on v3 with the multi-class label.

Replaces the binary is_claim with sentence_role ∈
{atomic_fact, framing, opinion, background}. Reports the actual
distribution across the 116 sentences in the corpus.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import yaml

from app.intelligence.gliner_extractor import (
    classify_all_sentence_roles,
    split_sentences,
)

GOLD_PATH = Path("evals/gold/claim_extraction/ai_tech_v3.yaml")


def main() -> int:
    with open(GOLD_PATH, "r", encoding="utf-8") as f:
        ds = yaml.safe_load(f)

    role_counts: Counter[str] = Counter()
    by_role_conf: dict[str, list[float]] = {}
    total_sents = 0
    samples_per_role: dict[str, list[str]] = {}

    for ex in ds["examples"]:
        rows = classify_all_sentence_roles(ex["document_text"])
        for sent, role, conf in rows:
            total_sents += 1
            role_counts[role] += 1
            by_role_conf.setdefault(role, []).append(conf)
            samples_per_role.setdefault(role, []).append(sent)

    print("=" * 70)
    print(f"  Sentence-role distribution across v3 ({total_sents} sentences)")
    print("=" * 70)
    print(f"{'role':<18}{'n':>5}{'%':>8}{'mean_conf':>12}")
    print("-" * 50)
    for role in ("atomic_fact", "framing", "opinion", "background"):
        n = role_counts.get(role, 0)
        confs = by_role_conf.get(role, [])
        mc = sum(confs) / len(confs) if confs else 0.0
        print(f"{role:<18}{n:>5}{n / total_sents * 100:>7.1f}%{mc:>12.3f}")

    print()
    print("=" * 70)
    print("  Sample sentences per role (up to 3)")
    print("=" * 70)
    for role in ("atomic_fact", "framing", "opinion", "background"):
        print(f"\n[{role}]")
        for s in samples_per_role.get(role, [])[:3]:
            print(f"  - {s[:120]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
