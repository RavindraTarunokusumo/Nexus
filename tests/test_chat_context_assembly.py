from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

_MIN = datetime(2025, 1, 1, tzinfo=timezone.utc)
_MAX = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _weights(**kw: float) -> dict[str, float]:
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


def _candidate(
    *,
    epistemic_state: dict | None = None,
    relation_count: int = 0,
    sem: float = 0.0,
) -> dict:
    return {
        "semantic_sim": sem,
        "object_family": "technical_objects",
        "salience": 0.5,
        "created_at": _MAX,
        "epistemic_state": epistemic_state or {},
        "relation_count": relation_count,
    }


def test_authority_score_mapping() -> None:
    from app.intelligence.chat import compute_hybrid_score

    w = _weights(source_authority=1.0)
    primary = compute_hybrid_score(
        _candidate(epistemic_state={"source_authority": "primary"}),
        w,
        [],
        _MIN,
        _MAX,
    )
    secondary = compute_hybrid_score(
        _candidate(epistemic_state={"source_authority": "secondary"}),
        w,
        [],
        _MIN,
        _MAX,
    )
    tertiary = compute_hybrid_score(
        _candidate(epistemic_state={"source_authority": "tertiary"}),
        w,
        [],
        _MIN,
        _MAX,
    )
    unknown = compute_hybrid_score(_candidate(), w, [], _MIN, _MAX)

    assert abs(primary - 1.0) < 1e-6
    assert abs(secondary - 0.66) < 1e-6
    assert abs(tertiary - 0.33) < 1e-6
    assert abs(unknown - 0.5) < 1e-6


def test_evidence_quality_score_mapping() -> None:
    from app.intelligence.chat import compute_hybrid_score

    w = _weights(evidence_quality=1.0)
    high = compute_hybrid_score(
        _candidate(epistemic_state={"evidence_quality": "high"}),
        w,
        [],
        _MIN,
        _MAX,
    )
    medium = compute_hybrid_score(
        _candidate(epistemic_state={"evidence_quality": "medium"}),
        w,
        [],
        _MIN,
        _MAX,
    )
    low = compute_hybrid_score(
        _candidate(epistemic_state={"evidence_quality": "low"}),
        w,
        [],
        _MIN,
        _MAX,
    )
    missing = compute_hybrid_score(_candidate(), w, [], _MIN, _MAX)

    assert abs(high - 1.0) < 1e-6
    assert abs(medium - 0.6) < 1e-6
    assert abs(low - 0.3) < 1e-6
    assert abs(missing - 0.5) < 1e-6


def test_relation_relevance_score_mapping() -> None:
    from app.intelligence.chat import compute_hybrid_score

    w = _weights(relation_relevance=1.0)
    none = compute_hybrid_score(_candidate(relation_count=0), w, [], _MIN, _MAX)
    two = compute_hybrid_score(_candidate(relation_count=2), w, [], _MIN, _MAX)
    four = compute_hybrid_score(_candidate(relation_count=4), w, [], _MIN, _MAX)
    many = compute_hybrid_score(_candidate(relation_count=10), w, [], _MIN, _MAX)

    assert abs(none - 0.0) < 1e-6
    assert abs(two - 0.5) < 1e-6
    assert abs(four - 1.0) < 1e-6
    assert abs(many - 1.0) < 1e-6


def test_evidence_strength_ordering_primary_before_auxiliary() -> None:
    from app.intelligence.chat import _order_context_blocks

    weak_primary = {
        "epistemic_state": {"evidence_quality": "low", "source_authority": "tertiary"},
        "confidence": 0.2,
        "label": "C1",
    }
    strong_primary = {
        "epistemic_state": {"evidence_quality": "high", "source_authority": "primary"},
        "confidence": 0.95,
        "label": "C2",
    }
    aux = {
        "epistemic_state": {"evidence_quality": "high", "source_authority": "primary"},
        "confidence": 1.0,
        "label": "C3",
        "role": "counter_evidence",
    }
    ordered = _order_context_blocks(
        [weak_primary, strong_primary],
        [aux],
        "evidence_strength",
    )
    assert ordered[0] is strong_primary
    assert ordered[1] is weak_primary
    assert ordered[2] is aux


def test_hybrid_score_ordering_preserved_when_not_evidence_strength() -> None:
    from app.intelligence.chat import _order_context_blocks

    first = {"epistemic_state": {}, "confidence": 0.1, "label": "C1"}
    second = {"epistemic_state": {}, "confidence": 0.9, "label": "C2"}
    ordered = _order_context_blocks(
        [first, second],
        [],
        "hybrid_score",
        primary_scores=[0.9, 0.1],
    )
    assert ordered[0] is first
    assert ordered[1] is second


def _capsule(
    capsule_id: uuid.UUID,
    *,
    text: str = "capsule text",
    epistemic_state: dict | None = None,
    confidence: float = 0.5,
    lifecycle_state: str = "active",
) -> dict:
    return {
        "id": capsule_id,
        "document_id": uuid.uuid4(),
        "text": text,
        "object_type": "model_release",
        "object_family": "technical_objects",
        "lifecycle_state": lifecycle_state,
        "title": "Doc",
        "url": "https://example.com",
        "epistemic_state": epistemic_state or {},
        "confidence": confidence,
    }


def test_assemble_context_blocks_counter_evidence_and_supersession() -> None:
    from app.intelligence.chat import _assemble_context_blocks

    primary_id = uuid.uuid4()
    counter_id = uuid.uuid4()
    superseding_id = uuid.uuid4()
    primary = _capsule(primary_id, text="Primary fact")
    counter = _capsule(counter_id, text="Counter fact")
    superseding = _capsule(superseding_id, text="Newer fact")

    relation_rows = [
        (primary_id, counter_id, "contradicts", None),
        (superseding_id, primary_id, "supersedes", None),
    ]
    top = [(primary, 0.9)]
    blocks = _assemble_context_blocks(
        top,
        include=[
            "highest_salience_relevant_objects",
            "counter_evidence_and_caveats",
            "superseding_or_superseded_objects",
            "epistemic_notes",
        ],
        ordering="hybrid_score",
        evidence_map={},
        relation_rows=relation_rows,
        auxiliary_candidates={
            counter_id: counter,
            superseding_id: superseding,
        },
    )

    assert len(blocks) == 3
    assert blocks[0]["role"] == "primary"
    assert blocks[1]["role"] == "counter_evidence"
    assert blocks[1]["capsule_id"] == counter_id
    assert blocks[2]["role"] == "supersession"
    assert blocks[2]["capsule_id"] == superseding_id
    assert "supersession=superseding" in blocks[2]["epistemic_note"]
    assert blocks[0]["label"] == "C1"
    assert blocks[1]["label"] == "C2"
    assert blocks[2]["label"] == "C3"


def test_assemble_skips_categories_not_in_include() -> None:
    from app.intelligence.chat import _assemble_context_blocks

    primary_id = uuid.uuid4()
    counter_id = uuid.uuid4()
    primary = _capsule(primary_id)
    counter = _capsule(counter_id)
    relation_rows = [(primary_id, counter_id, "contradicts", None)]

    blocks = _assemble_context_blocks(
        [(primary, 0.8)],
        include=["highest_salience_relevant_objects"],
        ordering="hybrid_score",
        evidence_map={},
        relation_rows=relation_rows,
        auxiliary_candidates={counter_id: counter},
    )

    assert len(blocks) == 1
    assert "role" in blocks[0]
    assert "epistemic_note" not in blocks[0]


def test_assemble_caps_counter_evidence_at_two() -> None:
    from app.intelligence.chat import _assemble_context_blocks

    primary_id = uuid.uuid4()
    counter_ids = [uuid.uuid4() for _ in range(4)]
    primary = _capsule(primary_id)
    relation_rows = [(primary_id, counter_ids[i], "contradicts", None) for i in range(4)]
    aux = {cid: _capsule(cid, text=f"counter {i}") for i, cid in enumerate(counter_ids)}

    blocks = _assemble_context_blocks(
        [(primary, 0.9)],
        include=[
            "highest_salience_relevant_objects",
            "counter_evidence_and_caveats",
        ],
        ordering="hybrid_score",
        evidence_map={},
        relation_rows=relation_rows,
        auxiliary_candidates=aux,
    )

    counter_blocks = [b for b in blocks if b.get("role") == "counter_evidence"]
    assert len(counter_blocks) == 2


@pytest.mark.asyncio
async def test_retrieve_capsules_with_relations_mocked_session() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from app.intelligence.chat import _run_retrieve_capsules

    primary_id = uuid.uuid4()
    counter_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    row = MagicMock()
    row.id = primary_id
    row.document_id = doc_id
    row.text = "Primary capsule"
    row.domain_object_type = "model_release"
    row.object_family = "technical_objects"
    row.lifecycle_state = "confirmed"
    row.salience = 0.7
    row.created_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    row.epistemic_state = {"source_authority": "primary", "evidence_quality": "high"}
    row.confidence = 0.9
    row.semantic_sim = 0.85
    row.title = "Article"
    row.url = "https://example.com/a"

    counter_row = MagicMock()
    counter_row.id = counter_id
    counter_row.document_id = uuid.uuid4()
    counter_row.text = "Counter capsule"
    counter_row.domain_object_type = "model_release"
    counter_row.object_family = "technical_objects"
    counter_row.lifecycle_state = "superseded"
    counter_row.salience = 0.4
    counter_row.created_at = datetime(2026, 2, 1, tzinfo=timezone.utc)
    counter_row.epistemic_state = {"source_authority": "secondary"}
    counter_row.confidence = 0.6
    counter_row.title = "Counter doc"
    counter_row.url = "https://example.com/c"

    candidate_result = MagicMock()
    candidate_result.all.return_value = [row]
    relation_result = MagicMock()
    relation_result.all.return_value = [
        (primary_id, counter_id, "contradicts", None),
    ]
    aux_result = MagicMock()
    aux_result.all.return_value = [counter_row]

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.scalar = AsyncMock(return_value=MagicMock())
    mock_session.execute = AsyncMock(side_effect=[candidate_result, relation_result, aux_result])

    sf = MagicMock()
    sf.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    sf.return_value.__aexit__ = AsyncMock(return_value=False)

    embedder = MagicMock()
    embedder.embed_one.return_value = [0.1] * 384

    pack = MagicMock()
    pack.retrieval_policy.query_intents = {}
    pack.retrieval_policy.hybrid_score_weights = {
        "semantic_similarity": 0.35,
        "domain_object_type_match": 0.20,
        "source_authority": 0.12,
        "recency": 0.12,
        "salience": 0.11,
        "relation_relevance": 0.07,
        "evidence_quality": 0.03,
    }
    pack.context_assembly.max_tokens_by_tier = {}
    pack.context_assembly.include = [
        "highest_salience_relevant_objects",
        "counter_evidence_and_caveats",
        "epistemic_notes",
    ]
    pack.context_assembly.ordering = "evidence_strength"

    state = {"question": "test", "top_k": 1, "query_intent": "general", "pack": pack}
    result = await _run_retrieve_capsules(state, sf, embedder)

    blocks = result["context_blocks"]
    assert len(blocks) == 2
    assert blocks[0]["role"] == "primary"
    assert blocks[0]["epistemic_note"] is not None
    assert blocks[1]["role"] == "counter_evidence"
    assert blocks[1]["capsule_id"] == counter_id
