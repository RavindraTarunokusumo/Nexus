from __future__ import annotations

from datetime import datetime, timezone

_MIN = datetime(2025, 1, 1, tzinfo=timezone.utc)
_MAX = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _candidate(
    sem: float = 0.8,
    family: str = "technical_objects",
    salience: float = 0.7,
    created_at: datetime | None = None,
) -> dict:
    return {
        "semantic_sim": sem,
        "object_family": family,
        "salience": salience,
        "created_at": created_at or _MAX,
    }


def _weights(**kw: float) -> dict:
    base: dict[str, float] = {
        "semantic_similarity": 0.0,
        "domain_object_type_match": 0.0,
        "source_authority": 0.0,
        "recency": 0.0,
        "salience": 0.0,
        "relation_relevance": 0.0,
        "evidence_quality": 0.0,
    }
    base.update(kw)
    return base


def test_semantic_similarity_applied() -> None:
    from app.intelligence.chat import compute_hybrid_score

    score = compute_hybrid_score(
        _candidate(sem=0.9), _weights(semantic_similarity=1.0), [], _MIN, _MAX
    )
    assert abs(score - 0.9) < 1e-6


def test_object_family_boost_first_priority() -> None:
    from app.intelligence.chat import compute_hybrid_score

    score = compute_hybrid_score(
        _candidate(family="technical_objects"),
        _weights(domain_object_type_match=1.0),
        ["technical_objects", "market_objects"],
        _MIN,
        _MAX,
    )
    assert score == 1.0


def test_object_family_no_match_scores_zero() -> None:
    from app.intelligence.chat import compute_hybrid_score

    score = compute_hybrid_score(
        _candidate(family="other_family"),
        _weights(domain_object_type_match=1.0),
        ["technical_objects"],
        _MIN,
        _MAX,
    )
    assert score == 0.0


def test_stubbed_weights_contribute_zero() -> None:
    from app.intelligence.chat import compute_hybrid_score

    score = compute_hybrid_score(
        _candidate(sem=0.99, salience=0.99),
        _weights(relation_relevance=1.0, evidence_quality=1.0),
        [],
        _MIN,
        _MAX,
    )
    assert score == 0.0


def test_recency_newer_beats_older() -> None:
    from app.intelligence.chat import compute_hybrid_score

    w = _weights(recency=1.0)
    newer = compute_hybrid_score(_candidate(created_at=_MAX), w, [], _MIN, _MAX)
    older = compute_hybrid_score(_candidate(created_at=_MIN), w, [], _MIN, _MAX)
    assert newer > older
    assert 0.0 <= newer <= 1.0
    assert 0.0 <= older <= 1.0
