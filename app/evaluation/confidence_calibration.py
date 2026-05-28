"""S8 — calibrate self-reported claim confidence against judge verdicts.

Pulls (sut_output.claims[i].confidence, judge_verdict_for_that_pair.match_status)
pairs from past EvalResult rows, fits a logistic (sigmoid) mapping from raw
confidence to P(judge says exact|partial), and persists the parameters as JSON.

At inference, callers can load the calibration and apply
calibrated_p = sigmoid(a * raw_confidence + b) before thresholding.

This is a lightweight one-file utility — no external sklearn dependency.
"""

from __future__ import annotations

import json
import math
import statistics
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EvalResult


def sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _fit_logistic(
    xs: list[float], ys: list[int], *, n_iter: int = 2000, lr: float = 0.1
) -> tuple[float, float]:
    """Tiny gradient-descent logistic fit. Returns (a, b) where p = sigmoid(a*x + b)."""
    if not xs:
        return 1.0, 0.0
    a, b = 1.0, 0.0
    for _ in range(n_iter):
        ga, gb = 0.0, 0.0
        for x, y in zip(xs, ys, strict=False):
            p = sigmoid(a * x + b)
            err = p - y
            ga += err * x
            gb += err
        n = len(xs)
        a -= lr * ga / n
        b -= lr * gb / n
    return a, b


async def collect_calibration_pairs(
    session: AsyncSession, *, run_ids: list[uuid.UUID] | None = None
) -> list[tuple[float, int]]:
    """Pull (confidence, label) pairs from EvalResult rows.

    Label = 1 if any predicted claim was judged exact/partial; 0 otherwise.
    """
    stmt = select(EvalResult).where(EvalResult.sut_output.isnot(None))
    if run_ids:
        stmt = stmt.where(EvalResult.run_id.in_(run_ids))
    res = await session.execute(stmt)
    rows = res.scalars().all()

    pairs: list[tuple[float, int]] = []
    for r in rows:
        sut_out = r.sut_output or {}
        verdict = r.judge_verdict or {}
        per_pair = verdict.get("per_pair_verdicts") or []
        pred_claims = sut_out.get("claims") if isinstance(sut_out, dict) else None
        if not pred_claims:
            continue
        # Align by index — judge alignment is greedy in metrics.align_claims, so
        # the i-th per-pair verdict corresponds roughly to the i-th pred claim.
        for i, pred in enumerate(pred_claims):
            try:
                conf = float(pred.get("confidence", 0.0))
            except (TypeError, ValueError):
                continue
            if i >= len(per_pair):
                pairs.append((conf, 0))
                continue
            verd = per_pair[i]
            ms = verd.get("match_status", "")
            label = 1 if ms in ("exact", "partial") else 0
            pairs.append((conf, label))
    return pairs


def fit_and_summarize(pairs: list[tuple[float, int]]) -> dict[str, Any]:
    if not pairs:
        return {"n": 0, "error": "no pairs"}
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    a, b = _fit_logistic(xs, ys)

    pos = [x for x, y in pairs if y == 1]
    neg = [x for x, y in pairs if y == 0]
    raw_threshold = 0.7
    raw_above = [y for x, y in pairs if x >= raw_threshold]
    raw_precision_at_0_7 = sum(raw_above) / len(raw_above) if raw_above else None

    return {
        "n": len(pairs),
        "n_positive": sum(ys),
        "n_negative": len(ys) - sum(ys),
        "raw_confidence_mean_pos": round(statistics.mean(pos), 3) if pos else None,
        "raw_confidence_mean_neg": round(statistics.mean(neg), 3) if neg else None,
        "logistic_a": round(a, 4),
        "logistic_b": round(b, 4),
        "raw_p_at_threshold_0_7": (
            round(raw_precision_at_0_7, 3) if raw_precision_at_0_7 is not None else None
        ),
        "calibrated_p_at_raw_0_5": round(sigmoid(a * 0.5 + b), 3),
        "calibrated_p_at_raw_0_7": round(sigmoid(a * 0.7 + b), 3),
        "calibrated_p_at_raw_0_9": round(sigmoid(a * 0.9 + b), 3),
    }


def save_calibration(params: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(params, indent=2), encoding="utf-8")
