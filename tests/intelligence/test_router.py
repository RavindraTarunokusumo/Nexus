from __future__ import annotations

from app.intelligence.router import QUESTION_SHAPES, STRATEGIES, resolve_strategy


def test_resolve_strategy_known_shapes() -> None:
    assert resolve_strategy("factoid") is STRATEGIES["factoid"]
    assert resolve_strategy("multi_doc") is STRATEGIES["multi_doc"]
    assert resolve_strategy("current_state") is STRATEGIES["current_state"]
    assert resolve_strategy("conflict") is STRATEGIES["conflict"]
    assert resolve_strategy("temporal") is STRATEGIES["temporal"]
    assert resolve_strategy("general") is STRATEGIES["general"]


def test_resolve_strategy_unknown_shape_returns_general() -> None:
    assert resolve_strategy("unknown") is STRATEGIES["general"]
    assert resolve_strategy("") is STRATEGIES["general"]


def test_general_strategy_is_all_defaults() -> None:
    general = STRATEGIES["general"]
    assert general.weight_overrides == {}
    assert general.fetch_k_multiplier == 3
    assert general.top_k_delta == 0
    assert general.answer_hint == ""


def test_weight_merge_preserves_unoverridden_pack_keys() -> None:
    pack_weights = {
        "semantic_similarity": 0.35,
        "domain_object_type_match": 0.20,
        "source_authority": 0.12,
        "recency": 0.12,
        "salience": 0.11,
        "relation_relevance": 0.07,
        "evidence_quality": 0.03,
    }
    weights = dict(pack_weights)
    weights.update(resolve_strategy("factoid").weight_overrides)
    assert weights["semantic_similarity"] == 0.6
    assert weights["salience"] == 0.05
    assert weights["recency"] == 0.05
    assert weights["domain_object_type_match"] == 0.20
    assert weights["source_authority"] == 0.12
    assert weights["relation_relevance"] == 0.07
    assert weights["evidence_quality"] == 0.03


def test_temporal_strategy_present() -> None:
    assert "temporal" in STRATEGIES
    assert "temporal" in QUESTION_SHAPES
    temporal = STRATEGIES["temporal"]
    assert temporal.top_k_delta == 7
    assert temporal.fetch_k_multiplier == 6
    assert "Date:" in temporal.answer_hint
    assert QUESTION_SHAPES.index("temporal") < QUESTION_SHAPES.index("general")


def test_effective_top_k_floors_at_one() -> None:
    strategy = resolve_strategy("general")
    top_k = 1
    effective_top_k = max(1, top_k + strategy.top_k_delta)
    assert effective_top_k == 1

    multi_doc = resolve_strategy("multi_doc")
    effective_top_k = max(1, 0 + multi_doc.top_k_delta)
    assert effective_top_k == 5

    effective_top_k = max(1, -7 + multi_doc.top_k_delta)
    assert effective_top_k == 1
