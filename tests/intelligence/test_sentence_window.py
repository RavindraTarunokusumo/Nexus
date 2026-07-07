from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.intelligence.prompts.chat_answer import build_user_prompt
from app.intelligence.sentence_window import (
    _fetch_entity_hits,
    _lexical_tsquery,
    _order_context_blocks,
    _rrf_fuse,
    rank_hit_windows,
    split_sentences,
)


def test_split_sentences_abbreviation_guard() -> None:
    sentences = split_sentences("Dr. Smith went home. He was tired.")
    assert sentences == ["Dr. Smith went home.", "He was tired."]


def test_split_sentences_boundaries_and_whitespace() -> None:
    sentences = split_sentences("First sentence!   Second one?  Third here.")
    assert sentences == ["First sentence!", "Second one?", "Third here."]


def test_split_sentences_collapses_internal_whitespace() -> None:
    sentences = split_sentences("One line.  Another   line.")
    assert sentences == ["One line.", "Another line."]


def _hit(
    hit_id: uuid.UUID,
    semantic_sim: float,
    published_at: datetime,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=hit_id,
        semantic_sim=semantic_sim,
        published_at=published_at,
        fetched_at=published_at,
    )


def test_rank_hit_windows_dedup_and_ordering() -> None:
    when = datetime(2024, 1, 1, tzinfo=timezone.utc)
    duplicate_id = uuid.uuid4()
    stale_duplicate = _hit(duplicate_id, 0.5, when)
    fresh_unique = _hit(uuid.uuid4(), 0.7, when)
    best_duplicate = _hit(duplicate_id, 0.95, when)

    ranked = rank_hit_windows(
        [stale_duplicate, fresh_unique, best_duplicate],
        k=2,
    )

    assert len(ranked) == 2
    assert ranked[0][0].id == best_duplicate.id
    assert ranked[1][0].id == fresh_unique.id
    assert ranked[0][1] >= ranked[1][1]


def test_rrf_fuse_rewards_cross_list_agreement_and_dedups() -> None:
    a, b, c = (uuid.uuid4() for _ in range(3))
    list1 = [SimpleNamespace(id=a), SimpleNamespace(id=b)]
    list2 = [SimpleNamespace(id=b), SimpleNamespace(id=c)]  # b appears in both
    fused = _rrf_fuse([list1, list2], k=3)
    ids = [h.id for h in fused]
    assert ids[0] == b  # agreement across both lists ranks it first
    assert len(ids) == len(set(ids)) == 3  # deduped, all present


def test_rrf_fuse_entity_channel_agreement_wins_over_single_channel() -> None:
    semantic_only, entity_only, shared = (uuid.uuid4() for _ in range(3))
    semantic = [SimpleNamespace(id=semantic_only), SimpleNamespace(id=shared)]
    entity = [SimpleNamespace(id=entity_only), SimpleNamespace(id=shared)]
    fused = _rrf_fuse([semantic, entity], k=3)
    assert fused[0].id == shared


@pytest.mark.asyncio
async def test_fetch_entity_hits_empty_entities_returns_empty() -> None:
    session = AsyncMock()
    assert await _fetch_entity_hits(session, [], fetch_k=10) == []
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_entity_hits_returns_rows_in_query_order() -> None:
    when = datetime(2024, 1, 1, tzinfo=timezone.utc)
    hit_a = SimpleNamespace(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        span_index=1,
        text="John and Maria volunteered.",
        match_count=2,
        title="Conv",
        url=None,
        published_at=when,
        fetched_at=when,
    )
    hit_b = SimpleNamespace(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        span_index=0,
        text="John went home.",
        match_count=1,
        title="Conv",
        url=None,
        published_at=when,
        fetched_at=when,
    )
    session = AsyncMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(all=lambda: [hit_a, hit_b]))

    rows = await _fetch_entity_hits(session, ["john", "maria"], fetch_k=5)

    assert rows == [hit_a, hit_b]
    assert rows[0].match_count >= rows[1].match_count


def test_lexical_tsquery_ors_dedups_and_drops_short_tokens() -> None:
    q = _lexical_tsquery("When did Joanna watch watch it in 2019?")
    terms = q.split(" | ")
    assert "joanna" in terms and "2019" in terms and "watch" in terms
    assert "it" not in terms  # short tokens dropped
    assert terms.count("watch") == 1  # deduped
    assert _lexical_tsquery("a of it") == ""  # all-short -> empty


def test_order_context_blocks_by_published_at_then_span_index() -> None:
    early = datetime(2024, 1, 1, tzinfo=timezone.utc)
    late = datetime(2024, 6, 1, tzinfo=timezone.utc)
    blocks = [
        {"label": "C2", "text": "late early index", "published_at": late, "first_span_index": 1},
        {"label": "C1", "text": "early late index", "published_at": early, "first_span_index": 5},
        {"label": "C3", "text": "late late index", "published_at": late, "first_span_index": 3},
    ]

    ordered = _order_context_blocks(blocks)

    assert [block["label"] for block in ordered] == ["C1", "C2", "C3"]


def test_assembled_block_renders_through_build_user_prompt() -> None:
    published_at = datetime(2024, 3, 10, tzinfo=timezone.utc)
    blocks = [
        {
            "label": "C1",
            "text": "User bought a red car. It was parked outside.",
            "published_at": published_at,
            "span_ids": [uuid.uuid4()],
        }
    ]

    prompt = build_user_prompt("What car did I buy?", blocks)

    assert "[C1]" in prompt
    assert "Date: 2024-03-10 (Sun)" in prompt
    assert "User bought a red car. It was parked outside." in prompt
