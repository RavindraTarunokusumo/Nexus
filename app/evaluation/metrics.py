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


def _normalize_words(s: str) -> set[str]:
    """Word set after stripping trailing punctuation that distorts overlap.

    'March 12, 2025.' and 'March 12, 2025,' should share the '2025' token, not
    end up as distinct '2025.' / '2025,' / '2025' tokens.
    """
    import re

    tokens = re.findall(r"[a-z0-9$%]+", s.lower())
    return set(tokens)


def _dice(a: str, b: str) -> float:
    """Sørensen-Dice coefficient: 2|A∩B| / (|A|+|B|).

    More forgiving than Jaccard when one string is a substring of the other —
    Dice = 0.50 corresponds to Jaccard ≈ 0.33. This matches the eval better
    when the system emits verbatim sentences and gold has trimmed atomic
    phrases.
    """
    set_a = _normalize_words(a)
    set_b = _normalize_words(b)
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    return 2 * len(intersection) / (len(set_a) + len(set_b))


# Backwards-compatible alias — kept for any external caller; uses normalized tokens now too.
def _jaccard(a: str, b: str) -> float:
    set_a = _normalize_words(a)
    set_b = _normalize_words(b)
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def align_claims(
    gold_claims: list[dict],
    pred_claims: list[dict],
    similarity_threshold: float = 0.5,
) -> list[tuple[dict | None, dict | None]]:
    """Greedily align predicted claims to gold claims by Sørensen-Dice overlap.

    Returns a list of (gold | None, pred | None) pairs:
    - (gold, pred)  → matched pair
    - (gold, None)  → missing (gold claim not predicted)
    - (None, pred)  → spurious (pred claim not in gold)

    Threshold default 0.5 on Dice ≈ Jaccard 0.33 — lenient enough to accept
    a verbatim sentence as a match for a trimmed gold claim that it contains.
    """
    unmatched_gold = list(gold_claims)
    unmatched_pred = list(pred_claims)
    pairs: list[tuple[dict | None, dict | None]] = []

    while unmatched_gold and unmatched_pred:
        best_sim = -1.0
        best_gi = best_pi = -1
        for gi, g in enumerate(unmatched_gold):
            for pi, p in enumerate(unmatched_pred):
                sim = _dice(g.get("claim_text", ""), p.get("claim_text", ""))
                if sim > best_sim:
                    best_sim = sim
                    best_gi, best_pi = gi, pi

        if best_sim >= similarity_threshold:
            pairs.append((unmatched_gold.pop(best_gi), unmatched_pred.pop(best_pi)))
        else:
            break

    for g in unmatched_gold:
        pairs.append((g, None))
    for p in unmatched_pred:
        pairs.append((None, p))

    return pairs
