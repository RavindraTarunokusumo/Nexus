"""Pure scoring functions for the memory benchmark runner (T-F35 / F5 metrics).

No I/O — every function takes plain dicts/lists and returns plain dicts so the
runner can serialize results directly and tests can exercise scoring in isolation.
"""

from __future__ import annotations

from typing import Any

METRIC_KEYS = (
    "answer_correctness",
    "forbidden_violation",
    "evidence_recall_at_k",
    "citation_precision",
    "citation_faithfulness",
    "temporal_correctness",
    "supersession_correctness",
    "abstention_accuracy",
)


def _keyword_fraction(keywords: list[str], answer_lower: str) -> float | None:
    if not keywords:
        return None
    hits = sum(1 for kw in keywords if kw in answer_lower)
    return hits / len(keywords)


def score_answer(
    question: dict[str, Any],
    answer: str,
    cited_doc_keys: list[str],
    retrieved_doc_keys: list[str],
    abstained: bool,
) -> dict[str, Any]:
    """Score one question/answer pair against its expected fixture fields."""
    expected_keywords: list[str] = question["expected_answer_keywords"]
    forbidden_keywords: list[str] = question["forbidden_keywords"]
    expected_doc_keys: set[str] = set(question["expected_doc_keys"])
    expected_abstain: bool = question["expected_abstain"]
    category: str = question["category"]

    answer_lower = answer.lower()
    cited = set(cited_doc_keys)
    retrieved = set(retrieved_doc_keys)

    if abstained and expected_abstain:
        answer_correctness = 1.0
    else:
        fraction = _keyword_fraction(expected_keywords, answer_lower)
        # No keywords to check (e.g. abstention questions): correct only if the
        # abstain decision itself matched expectations.
        answer_correctness = (
            fraction if fraction is not None else float(abstained == expected_abstain)
        )

    forbidden_violation = any(kw in answer_lower for kw in forbidden_keywords)

    evidence_recall_at_k = (
        len(cited & expected_doc_keys) / len(expected_doc_keys) if expected_doc_keys else None
    )
    citation_precision = len(cited & expected_doc_keys) / len(cited) if cited else None
    citation_faithfulness = cited <= retrieved

    is_fully_correct = answer_correctness == 1.0 and not forbidden_violation
    temporal_correctness = is_fully_correct if category == "timeline" else None
    supersession_correctness = is_fully_correct if category == "superseded" else None

    abstention_accuracy = abstained == expected_abstain

    return {
        "answer_correctness": answer_correctness,
        "forbidden_violation": forbidden_violation,
        "evidence_recall_at_k": evidence_recall_at_k,
        "citation_precision": citation_precision,
        "citation_faithfulness": citation_faithfulness,
        "temporal_correctness": temporal_correctness,
        "supersession_correctness": supersession_correctness,
        "abstention_accuracy": abstention_accuracy,
    }


def _mean(values: list[Any]) -> float | None:
    present = [float(v) for v in values if v is not None]
    return sum(present) / len(present) if present else None


def _aggregate_metrics(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    return {key: _mean([row.get(key) for row in rows]) for key in METRIC_KEYS}


def _percentile(sorted_values: list[float], pct: float) -> float:
    index = min(len(sorted_values) - 1, round(pct * (len(sorted_values) - 1)))
    return sorted_values[index]


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-question score rows into overall + per-category means.

    Rows are expected to carry the ``METRIC_KEYS`` fields plus ``category`` and
    optionally ``latency_s`` / ``tokens_used``. Missing/None metric values are
    excluded from the corresponding mean rather than treated as zero.
    """
    overall = _aggregate_metrics(rows)

    latencies = sorted(row["latency_s"] for row in rows if row.get("latency_s") is not None)
    if latencies:
        overall["latency_p50_s"] = _percentile(latencies, 0.5)
        overall["latency_p95_s"] = _percentile(latencies, 0.95)

    tokens = [row["tokens_used"] for row in rows if row.get("tokens_used") is not None]
    if tokens:
        overall["total_tokens_used"] = float(sum(tokens))

    categories = sorted({row["category"] for row in rows if "category" in row})
    by_category = {
        category: _aggregate_metrics([row for row in rows if row.get("category") == category])
        for category in categories
    }

    return {"n": len(rows), "overall": overall, "by_category": by_category}
