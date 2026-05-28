"""Unit tests for app.intelligence.taxonomy — pure data, no DB or LLM."""
from __future__ import annotations

import pytest

from app.intelligence.taxonomy import (
    ALL_CATEGORIES,
    ALL_TYPES,
    CATEGORIES,
    category_of,
    is_valid,
    legacy_to_new,
    split_type,
)


def test_all_types_are_dotted_and_unique() -> None:
    assert len(ALL_TYPES) == len(set(ALL_TYPES))
    assert all("." in t for t in ALL_TYPES)
    # 24 subtypes total across 7 categories
    # (release=4 + performance=3 + research=4 + infra=3 + business=5 + governance=3 + forecast=2).
    assert len(ALL_TYPES) == 24
    assert len(ALL_CATEGORIES) == 7


def test_all_types_match_categories_dict() -> None:
    derived = {f"{cat}.{sub}" for cat, subs in CATEGORIES.items() for sub in subs}
    assert set(ALL_TYPES) == derived


@pytest.mark.parametrize(
    "dotted,expected",
    [
        ("release.model", True),
        ("performance.benchmark", True),
        ("governance.safety_incident", True),
        ("release.nonexistent", False),
        ("not_a_category.model", False),
        ("no_dot", False),
        ("", False),
    ],
)
def test_is_valid(dotted: str, expected: bool) -> None:
    assert is_valid(dotted) is expected


def test_category_of_returns_top_level() -> None:
    assert category_of("release.model") == "release"
    assert category_of("governance.regulation") == "governance"
    assert category_of("unknown.foo") == ""
    assert category_of("malformed") == ""


def test_split_type_round_trip() -> None:
    for t in ALL_TYPES:
        cat, sub = split_type(t)
        assert f"{cat}.{sub}" == t


def test_split_type_rejects_malformed() -> None:
    with pytest.raises(ValueError):
        split_type("no_dot_here")


def test_legacy_to_new_deterministic() -> None:
    assert legacy_to_new("model_release") == "release.model"
    assert legacy_to_new("benchmark_result") == "performance.benchmark"
    assert legacy_to_new("security_issue") == "governance.safety_incident"
    assert legacy_to_new("forecast") == "forecast.prediction"
    # 'other' has no deterministic mapping — must return None.
    assert legacy_to_new("other") is None
    # Unknown legacy returns None too.
    assert legacy_to_new("bogus") is None


def test_legacy_mapping_lands_in_valid_types() -> None:
    legacy = [
        "model_release",
        "benchmark_result",
        "product_launch",
        "pricing_change",
        "research_finding",
        "infrastructure_update",
        "security_issue",
        "funding_event",
        "regulation",
        "forecast",
    ]
    for legacy_key in legacy:
        new = legacy_to_new(legacy_key)
        assert new is not None
        assert is_valid(new)
