from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.models import SemanticCapsule, SemanticRelation
from app.intelligence.cross_relations import (
    OrderedCapsulePair,
    build_cross_doc_pairs,
    classify_cross_document_relations,
)
from app.intelligence.llm_client import LLMError

_DOMAIN = "personal_ai_tech"
_NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _cap(
    *,
    cap_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    family: str = "model_release_event",
    facets: dict | None = None,
    created_at: datetime | None = None,
) -> SemanticCapsule:
    return SemanticCapsule(
        id=cap_id or uuid.uuid4(),
        source_id=uuid.uuid4(),
        document_id=document_id or uuid.uuid4(),
        idempotency_key=str(uuid.uuid4()),
        core_type="claim",
        text="t",
        domain=_DOMAIN,
        object_family=family,
        domain_object_type="model_release",
        facets=facets or {"orgs": ["OpenAI"]},
        lifecycle_state="active",
        created_by_tier="t2",
        created_at=created_at or _NOW,
    )


def _pair_ids(pairs: list[OrderedCapsulePair]) -> list[tuple[uuid.UUID, uuid.UUID]]:
    return [(p.newer.id, p.older.id) for p in pairs]


def test_build_cross_doc_pairs_same_family_same_actor_only() -> None:
    doc_a, doc_b, doc_c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    openai_a = _cap(document_id=doc_a, facets={"orgs": ["OpenAI"]})
    openai_b = _cap(document_id=doc_b, facets={"orgs": ["OpenAI"]})
    anthropic = _cap(document_id=doc_c, facets={"orgs": ["Anthropic"]})
    other_family = _cap(
        document_id=doc_a,
        family="benchmark_result",
        facets={"orgs": ["OpenAI"]},
    )

    pairs, skipped = build_cross_doc_pairs(
        [openai_a, openai_b, anthropic, other_family],
        set(),
    )

    assert skipped == 0
    assert len(pairs) == 1
    assert {openai_a.id, openai_b.id} == {pairs[0].newer.id, pairs[0].older.id}


def test_build_cross_doc_pairs_excludes_same_document() -> None:
    doc = uuid.uuid4()
    cap_a = _cap(document_id=doc)
    cap_b = _cap(document_id=doc)

    pairs, skipped = build_cross_doc_pairs([cap_a, cap_b], set())

    assert pairs == []
    assert skipped == 0


def test_build_cross_doc_pairs_excludes_no_actor() -> None:
    doc_a, doc_b = uuid.uuid4(), uuid.uuid4()
    cap_a = _cap(document_id=doc_a, facets={})
    cap_b = _cap(document_id=doc_b, facets={"people": ["Alice"]})

    pairs, skipped = build_cross_doc_pairs([cap_a, cap_b], set())

    assert pairs == []
    assert skipped == 0


def test_build_cross_doc_pairs_dedup_existing_either_direction() -> None:
    doc_a, doc_b = uuid.uuid4(), uuid.uuid4()
    cap_a = _cap(document_id=doc_a)
    cap_b = _cap(document_id=doc_b)
    key = (min(cap_a.id, cap_b.id), max(cap_a.id, cap_b.id))

    pairs, skipped = build_cross_doc_pairs([cap_a, cap_b], {key})

    assert pairs == []
    assert skipped == 1


def test_build_cross_doc_pairs_deterministic_ordering() -> None:
    doc_a, doc_b, doc_c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    older = _cap(
        cap_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        document_id=doc_a,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    mid = _cap(
        cap_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        document_id=doc_b,
        created_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )
    newest = _cap(
        cap_id=uuid.UUID("00000000-0000-0000-0000-000000000003"),
        document_id=doc_c,
        created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )

    pairs, _ = build_cross_doc_pairs([older, mid, newest], set())

    assert len(pairs) == 3
    assert _pair_ids(pairs) == [
        (newest.id, older.id),
        (newest.id, mid.id),
        (mid.id, older.id),
    ]


def test_build_cross_doc_pairs_newer_first_direction() -> None:
    doc_a, doc_b = uuid.uuid4(), uuid.uuid4()
    older = _cap(
        document_id=doc_a,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    newer = _cap(
        document_id=doc_b,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )

    pairs, _ = build_cross_doc_pairs([older, newer], set())

    assert len(pairs) == 1
    assert pairs[0].newer.id == newer.id
    assert pairs[0].older.id == older.id


def _make_session_factory(
    capsules: list[SemanticCapsule],
    existing_rels: list[SemanticRelation] | None = None,
    published_at_by_id: dict[uuid.UUID, datetime] | None = None,
) -> MagicMock:
    published_at_by_id = published_at_by_id or {}
    state: dict = {"exec_n": 0, "added": []}

    class SessionCM:
        async def __aenter__(self):
            session = AsyncMock()
            session.add = lambda obj: state["added"].append(obj)
            session.commit = AsyncMock()

            async def execute(stmt):
                state["exec_n"] += 1
                state.setdefault("stmts", []).append(stmt)
                result = MagicMock()
                if state["exec_n"] == 1:
                    result.all.return_value = [
                        (cap, published_at_by_id.get(cap.id)) for cap in capsules
                    ]
                elif state["exec_n"] == 2:
                    result.scalars.return_value.all.return_value = existing_rels or []
                else:
                    result.scalars.return_value.all.return_value = []
                return result

            session.execute = execute
            return session

        async def __aexit__(self, *_args):
            return False

    sf = MagicMock(return_value=SessionCM())
    sf._state = state
    return sf


def _make_pack() -> MagicMock:
    pack = MagicMock()
    pack.metadata.pack_id = "personal_ai_tech"
    pack.relation_grammar.core_relations = ["supports", "contradicts", "supersedes"]
    pack.relation_grammar.domain_relations = []
    return pack


@pytest.mark.asyncio
async def test_classify_dry_run_writes_nothing_and_calls_no_llm() -> None:
    doc_a, doc_b = uuid.uuid4(), uuid.uuid4()
    cap_a = _cap(document_id=doc_a)
    cap_b = _cap(document_id=doc_b)
    sf = _make_session_factory([cap_a, cap_b])
    client = AsyncMock()

    report = await classify_cross_document_relations(
        sf,
        client,
        domain=_DOMAIN,
        pack=_make_pack(),
        model="test-model",
        dry_run=True,
    )

    assert report.candidate_pairs == 1
    assert report.skipped_existing == 0
    assert report.classified_pairs == 0
    assert report.relations_created == 0
    assert report.relation_ids == []
    client.complete_json.assert_not_called()
    assert sf._state["added"] == []


@pytest.mark.asyncio
async def test_classify_max_pairs_zero_classifies_nothing() -> None:
    doc_a, doc_b = uuid.uuid4(), uuid.uuid4()
    cap_a = _cap(document_id=doc_a)
    cap_b = _cap(document_id=doc_b)
    sf = _make_session_factory([cap_a, cap_b])
    client = AsyncMock()

    report = await classify_cross_document_relations(
        sf,
        client,
        domain=_DOMAIN,
        pack=_make_pack(),
        model="test-model",
        max_pairs=0,
    )

    assert report.candidate_pairs == 1
    assert report.classified_pairs == 0
    assert report.relations_created == 0
    client.complete_json.assert_not_called()


@pytest.mark.asyncio
async def test_classify_max_pairs_cap() -> None:
    doc_a, doc_b, doc_c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    caps = [
        _cap(document_id=doc_a, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        _cap(document_id=doc_b, created_at=datetime(2026, 2, 1, tzinfo=timezone.utc)),
        _cap(document_id=doc_c, created_at=datetime(2026, 3, 1, tzinfo=timezone.utc)),
    ]
    sf = _make_session_factory(caps)
    client = AsyncMock()
    none_result = MagicMock()
    none_result.relation_type = "none"
    none_result.polarity = None
    none_result.strength = 0.5
    none_result.rationale = "no relation"
    client.complete_json = AsyncMock(return_value=(none_result, 10))

    report = await classify_cross_document_relations(
        sf,
        client,
        domain=_DOMAIN,
        pack=_make_pack(),
        model="test-model",
        max_pairs=1,
    )

    assert report.candidate_pairs == 3
    assert report.classified_pairs == 1
    assert client.complete_json.await_count == 1


@pytest.mark.asyncio
async def test_classify_none_writes_no_row() -> None:
    doc_a, doc_b = uuid.uuid4(), uuid.uuid4()
    cap_a = _cap(document_id=doc_a)
    cap_b = _cap(document_id=doc_b)
    sf = _make_session_factory([cap_a, cap_b])
    client = AsyncMock()
    none_result = MagicMock()
    none_result.relation_type = "none"
    none_result.polarity = None
    none_result.strength = 0.5
    none_result.rationale = "unrelated"
    client.complete_json = AsyncMock(return_value=(none_result, 10))

    report = await classify_cross_document_relations(
        sf,
        client,
        domain=_DOMAIN,
        pack=_make_pack(),
        model="test-model",
    )

    assert report.classified_pairs == 1
    assert report.relations_created == 0
    assert sf._state["added"] == []


@pytest.mark.asyncio
async def test_classify_llm_error_on_one_pair_does_not_abort_rest() -> None:
    doc_a, doc_b, doc_c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    newer = _cap(
        document_id=doc_a,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    mid = _cap(
        document_id=doc_b,
        created_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )
    oldest = _cap(
        document_id=doc_c,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    sf = _make_session_factory([newer, mid, oldest])

    supports = MagicMock()
    supports.relation_type = "supports"
    supports.polarity = "positive"
    supports.strength = 0.8
    supports.rationale = "supports"

    client = AsyncMock()
    client.complete_json = AsyncMock(
        side_effect=[
            LLMError("fail"),
            (supports, 10),
            (supports, 10),
        ]
    )

    report = await classify_cross_document_relations(
        sf,
        client,
        domain=_DOMAIN,
        pack=_make_pack(),
        model="test-model",
        max_pairs=3,
    )

    assert report.classified_pairs == 3
    assert report.relations_created == 2
    assert len(sf._state["added"]) == 2


@pytest.mark.asyncio
async def test_classify_source_is_newer_capsule() -> None:
    doc_a, doc_b = uuid.uuid4(), uuid.uuid4()
    older = _cap(
        document_id=doc_a,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    newer = _cap(
        document_id=doc_b,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    sf = _make_session_factory([older, newer])
    client = AsyncMock()
    result = MagicMock()
    result.relation_type = "supersedes"
    result.polarity = None
    result.strength = 0.9
    result.rationale = "newer supersedes older"
    client.complete_json = AsyncMock(return_value=(result, 10))

    report = await classify_cross_document_relations(
        sf,
        client,
        domain=_DOMAIN,
        pack=_make_pack(),
        model="test-model",
    )

    assert report.relations_created == 1
    rel = sf._state["added"][0]
    assert rel.source_capsule_id == newer.id
    assert rel.target_capsule_id == older.id
    assert rel.created_by_tier == "t2"


@pytest.mark.asyncio
async def test_classify_skipped_existing_from_db() -> None:
    doc_a, doc_b = uuid.uuid4(), uuid.uuid4()
    cap_a = _cap(document_id=doc_a)
    cap_b = _cap(document_id=doc_b)
    existing = SemanticRelation(
        source_capsule_id=cap_b.id,
        target_capsule_id=cap_a.id,
        relation_type="supports",
        strength=0.8,
        confidence=0.8,
        created_by_tier="t2",
    )
    sf = _make_session_factory([cap_a, cap_b], [existing])
    client = AsyncMock()

    report = await classify_cross_document_relations(
        sf,
        client,
        domain=_DOMAIN,
        pack=_make_pack(),
        model="test-model",
    )

    assert report.candidate_pairs == 0
    assert report.skipped_existing == 1
    client.complete_json.assert_not_called()


def test_build_cross_doc_pairs_publication_date_overrides_ingestion_order() -> None:
    doc_a, doc_b = uuid.uuid4(), uuid.uuid4()
    ingested_late_but_published_early = _cap(
        document_id=doc_a,
        created_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
    )
    ingested_early_but_published_late = _cap(
        document_id=doc_b,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    effective_ts = {
        ingested_late_but_published_early.id: datetime(2025, 11, 1, tzinfo=timezone.utc),
        ingested_early_but_published_late.id: datetime(2026, 2, 1, tzinfo=timezone.utc),
    }

    pairs, _ = build_cross_doc_pairs(
        [ingested_late_but_published_early, ingested_early_but_published_late],
        set(),
        effective_ts,
    )

    assert len(pairs) == 1
    assert pairs[0].newer.id == ingested_early_but_published_late.id
    assert pairs[0].older.id == ingested_late_but_published_early.id


@pytest.mark.asyncio
async def test_classify_uses_published_at_for_direction() -> None:
    doc_a, doc_b = uuid.uuid4(), uuid.uuid4()
    ingested_first = _cap(
        document_id=doc_a,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    ingested_second = _cap(
        document_id=doc_b,
        created_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
    )
    sf = _make_session_factory(
        [ingested_first, ingested_second],
        published_at_by_id={
            ingested_first.id: datetime(2026, 2, 1, tzinfo=timezone.utc),
            ingested_second.id: datetime(2025, 11, 1, tzinfo=timezone.utc),
        },
    )
    client = AsyncMock()
    result = MagicMock()
    result.relation_type = "supersedes"
    result.polarity = None
    result.strength = 0.9
    result.rationale = "newer supersedes older"
    client.complete_json = AsyncMock(return_value=(result, 10))

    await classify_cross_document_relations(
        sf,
        client,
        domain=_DOMAIN,
        pack=_make_pack(),
        model="test-model",
    )

    rel = sf._state["added"][0]
    assert rel.source_capsule_id == ingested_first.id
    assert rel.target_capsule_id == ingested_second.id


@pytest.mark.asyncio
async def test_classify_capsule_query_filters_non_terminal_states() -> None:
    sf = _make_session_factory([])
    client = AsyncMock()

    await classify_cross_document_relations(
        sf,
        client,
        domain=_DOMAIN,
        pack=_make_pack(),
        model="test-model",
    )

    load_stmt = str(sf._state["stmts"][0])
    assert "lifecycle_state IN" in load_stmt
    from app.intelligence.cross_relations import _NON_TERMINAL_STATES

    assert _NON_TERMINAL_STATES == frozenset({"candidate", "active", "confirmed", "qualified"})
