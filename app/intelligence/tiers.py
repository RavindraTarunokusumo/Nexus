"""Shared created_by_tier validation for writer modules that mirror the theses/decision_artefacts DB CHECK constraints (app/db/migrations/versions/0005_semantic_capsules.py: _THESIS_TIERS, _DECISION_TIERS)."""

from __future__ import annotations

WRITER_TIERS = ("t2", "t3", "t4")


def validate_writer_tier(created_by_tier: str) -> None:
    if created_by_tier not in WRITER_TIERS:
        raise ValueError(f"created_by_tier must be one of {WRITER_TIERS}, got {created_by_tier!r}")
