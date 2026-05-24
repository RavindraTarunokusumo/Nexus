# app/evaluation/metrics.py
"""Deterministic evaluation metrics for claim extraction and span retrieval."""

from __future__ import annotations

import math


def precision_recall_f1(
    gold_ids: set[str],
    pred_ids: set[str],
) -> tuple[float, float, float]:
    """Compute precision, recall, and F1 for two sets of IDs.

    Both-empty case: returns (1.0, 1.0, 1.0) — perfect agreement on nothing.
    """
    if not gold_ids and not pred_ids:
        return 1.0, 1.0, 1.0
    if not pred_ids:
        return 0.0, 0.0, 0.0
    if not gold_ids:
        return 0.0, 0.0, 0.0

    tp = len(gold_ids & pred_ids)
    precision = tp / len(pred_ids)
    recall = tp / len(gold_ids)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def precision_at_k(
    gold_ids: set[str],
    ranked_pred_ids: list[str],
    k: int,
) -> float:
    """Fraction of the top-k predictions that are in gold_ids."""
    if k <= 0:
        return 0.0
    top_k = ranked_pred_ids[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for pid in top_k if pid in gold_ids)
    return hits / len(top_k)


def ndcg_at_k(graded_relevances: list[float], k: int) -> float:
    """Normalized Discounted Cumulative Gain at k.

    graded_relevances: list of relevance scores in ranked order (e.g. [1, 0, 1]).
    Returns 0.0 if ideal DCG is 0.
    """

    def _dcg(rels: list[float], cutoff: int) -> float:
        return sum(rel / math.log2(i + 2) for i, rel in enumerate(rels[:cutoff]))

    dcg = _dcg(graded_relevances, k)
    ideal = _dcg(sorted(graded_relevances, reverse=True), k)
    return dcg / ideal if ideal > 0 else 0.0


def _jaccard(a: str, b: str) -> float:
    """Word-level Jaccard similarity between two strings."""
    set_a = set(a.lower().split())
    set_b = set(b.lower().split())
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    intersection = set_a & set_b
    return len(intersection) / len(union)


def align_claims(
    gold_claims: list[dict],
    pred_claims: list[dict],
    similarity_threshold: float = 0.5,
) -> list[tuple[dict | None, dict | None]]:
    """Greedily align predicted claims to gold claims by Jaccard word-overlap.

    Returns a list of (gold | None, pred | None) pairs:
    - (gold, pred)  → matched pair
    - (gold, None)  → missing (gold claim not predicted)
    - (None, pred)  → spurious (pred claim not in gold)
    """
    unmatched_gold = list(gold_claims)
    unmatched_pred = list(pred_claims)
    pairs: list[tuple[dict | None, dict | None]] = []

    # Build similarity matrix and greedy-match highest pairs first
    while unmatched_gold and unmatched_pred:
        best_sim = -1.0
        best_gi = best_pi = -1
        for gi, g in enumerate(unmatched_gold):
            for pi, p in enumerate(unmatched_pred):
                sim = _jaccard(g.get("claim_text", ""), p.get("claim_text", ""))
                if sim > best_sim:
                    best_sim = sim
                    best_gi, best_pi = gi, pi

        if best_sim >= similarity_threshold:
            pairs.append((unmatched_gold.pop(best_gi), unmatched_pred.pop(best_pi)))
        else:
            break  # no more matches above threshold

    # Remaining gold → missing; remaining pred → spurious
    for g in unmatched_gold:
        pairs.append((g, None))
    for p in unmatched_pred:
        pairs.append((None, p))

    return pairs
