from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db.models import Document, Span
from app.intelligence.chat import (
    _CHAT_ANSWER_SCHEMA_RETRY_SUFFIX as _SCHEMA_RETRY_SUFFIX,
)
from app.intelligence.chat import (
    INSUFFICIENT_EVIDENCE_ANSWER,
    ChatAnswerOutput,
    estimate_tokens,
)
from app.intelligence.llm_client import LLMNetworkError, LLMSchemaError
from app.intelligence.prompts.chat_answer import SYSTEM_PROMPT, build_user_prompt

_ABBREVIATIONS = (
    "Mr.",
    "Mrs.",
    "Ms.",
    "Dr.",
    "Prof.",
    "Sr.",
    "Jr.",
    "e.g.",
    "i.e.",
    "etc.",
    "vs.",
)
_RECENCY_WEIGHT = settings.sentence_window_recency_weight
_SEMANTIC_WEIGHT = 1.0 - _RECENCY_WEIGHT


def split_sentences(text: str) -> list[str]:
    """Split text on sentence boundaries with a guard for common abbreviations."""
    collapsed = re.sub(r"\s+", " ", text.strip())
    if not collapsed:
        return []

    placeholders: dict[str, str] = {}
    working = collapsed
    for index, abbr in enumerate(_ABBREVIATIONS):
        token = f"__ABBR{index}__"
        placeholders[token] = abbr
        working = working.replace(abbr, token)

    parts = re.split(r"(?<=[.?!])\s+", working)
    sentences: list[str] = []
    for part in parts:
        sentence = part.strip()
        if not sentence:
            continue
        for token, abbr in placeholders.items():
            sentence = sentence.replace(token, abbr)
        sentences.append(sentence)
    return sentences


def _recency_score(
    event_at: datetime,
    recency_min: datetime,
    recency_max: datetime,
) -> float:
    if recency_min == recency_max:
        return 0.5
    span_seconds = (recency_max - recency_min).total_seconds()
    if span_seconds <= 0:
        return 0.5
    score = (event_at - recency_min).total_seconds() / span_seconds
    return max(0.0, min(1.0, score))


def _hybrid_hit_score(
    semantic_sim: float,
    published_at: datetime | None,
    fetched_at: datetime,
    recency_min: datetime,
    recency_max: datetime,
) -> float:
    event_at = published_at or fetched_at
    rec_score = _recency_score(event_at, recency_min, recency_max)
    return _SEMANTIC_WEIGHT * semantic_sim + _RECENCY_WEIGHT * rec_score


async def ingest_sentence_spans(
    session_factory: async_sessionmaker,
    embedder: Any,
    document_id: uuid.UUID,
    text: str,
    *,
    speaker: str | None = None,
) -> int:
    sentences = split_sentences(text)
    if not sentences:
        return 0

    metadata: dict[str, str] | None = {"speaker": speaker} if speaker else None
    vectors = embedder.embed(sentences)

    async with session_factory() as session:
        for index, (sentence, vector) in enumerate(zip(sentences, vectors, strict=True)):
            session.add(
                Span(
                    document_id=document_id,
                    span_index=index,
                    text=sentence,
                    token_count=estimate_tokens(sentence),
                    embedding=vector,
                    metadata_json=metadata,
                )
            )
        doc = await session.get(Document, document_id)
        if doc is not None:
            doc.status = "embedded"
        await session.commit()

    return len(sentences)


async def _fetch_ann_hits(
    session: AsyncSession,
    query_vec: list[float],
    fetch_k: int,
) -> list[Any]:
    distance = Span.embedding.cosine_distance(query_vec)
    rows = (
        await session.execute(
            select(
                Span.id,
                Span.document_id,
                Span.span_index,
                Span.text,
                (1 - distance).label("semantic_sim"),
                Document.title.label("title"),
                Document.url.label("url"),
                Document.published_at.label("published_at"),
                Document.fetched_at.label("fetched_at"),
            )
            .join(Document, Span.document_id == Document.id)
            .where(Span.embedding.isnot(None))
            .order_by(distance)
            .limit(fetch_k)
        )
    ).all()
    return list(rows)


async def _fetch_neighbor_spans(
    session: AsyncSession,
    document_id: uuid.UUID,
    center_index: int,
    window: int,
) -> list[Any]:
    low = max(0, center_index - window)
    high = center_index + window
    rows = (
        await session.execute(
            select(Span.id, Span.span_index, Span.text)
            .where(Span.document_id == document_id)
            .where(Span.span_index >= low)
            .where(Span.span_index <= high)
            .order_by(Span.span_index)
        )
    ).all()
    return list(rows)


def _order_context_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def sort_key(block: dict[str, Any]) -> tuple[float, int]:
        published_at = block.get("published_at")
        first_index = block.get("first_span_index", 0)
        timestamp = published_at.timestamp() if published_at is not None else float("-inf")
        return (timestamp, first_index)

    return sorted(blocks, key=sort_key)


async def retrieve_windows(
    session: AsyncSession,
    embedder: Any,
    question: str,
    *,
    fetch_k: int,
    window: int,
    k: int,
    as_of: datetime | None,
) -> list[dict[str, Any]]:
    del as_of  # reserved for prompt assembly in answer_sentence_window
    sentinel = await session.scalar(select(Span).where(Span.embedding.isnot(None)).limit(1))
    if sentinel is None:
        return []

    query_vec = embedder.embed_one(question)
    hits = await _fetch_ann_hits(session, query_vec, fetch_k)
    if not hits:
        return []

    effective_dates = [hit.published_at or hit.fetched_at for hit in hits]
    recency_min = min(effective_dates)
    recency_max = max(effective_dates)

    scored_hits = [
        (
            hit,
            _hybrid_hit_score(
                float(hit.semantic_sim),
                hit.published_at,
                hit.fetched_at,
                recency_min,
                recency_max,
            ),
        )
        for hit in hits
    ]
    scored_hits.sort(key=lambda item: item[1], reverse=True)

    seen_hit_ids: set[uuid.UUID] = set()
    selected_hits: list[tuple[Any, float]] = []
    for hit, score in scored_hits:
        if hit.id in seen_hit_ids:
            continue
        seen_hit_ids.add(hit.id)
        selected_hits.append((hit, score))
        if len(selected_hits) >= k:
            break

    blocks: list[dict[str, Any]] = []
    for label_index, (hit, score) in enumerate(selected_hits, start=1):
        neighbors = await _fetch_neighbor_spans(session, hit.document_id, hit.span_index, window)
        if not neighbors:
            continue
        span_ids = [row.id for row in neighbors]
        block_text = " ".join(row.text for row in neighbors)
        blocks.append(
            {
                "label": f"C{label_index}",
                "text": block_text,
                "published_at": hit.published_at,
                "span_ids": span_ids,
                "document_id": hit.document_id,
                "document_title": hit.title,
                "url": hit.url,
                "score": score,
                "first_span_index": neighbors[0].span_index,
            }
        )

    return _order_context_blocks(blocks)


async def answer_sentence_window(
    session_factory: async_sessionmaker,
    client: Any,
    embedder: Any,
    question: str,
    model: str,
    *,
    fetch_k: int,
    window: int,
    k: int,
    as_of: datetime | None,
    pack: Any,
) -> dict[str, Any]:
    del pack  # sentence-window path does not use pack retrieval policy in the MVP
    async with session_factory() as session:
        blocks = await retrieve_windows(
            session,
            embedder,
            question,
            fetch_k=fetch_k,
            window=window,
            k=k,
            as_of=as_of,
        )

    if not blocks:
        return {
            "answer": INSUFFICIENT_EVIDENCE_ANSWER,
            "citation_labels": [],
            "tokens_used": 0,
            "context_blocks": [],
            "question_shape": "sentence_window",
        }

    user = build_user_prompt(question, blocks, as_of=as_of)
    tokens = 0
    try:
        try:
            result, tokens = await client.complete_json(
                model=model,
                system=SYSTEM_PROMPT,
                user=user,
                response_model=ChatAnswerOutput,
                run_type="chat_answer",
                max_tokens=4000,
            )
        except LLMSchemaError:
            result, retry_tokens = await client.complete_json(
                model=model,
                system=SYSTEM_PROMPT + _SCHEMA_RETRY_SUFFIX,
                user=user,
                response_model=ChatAnswerOutput,
                run_type="chat_answer",
                max_tokens=4000,
            )
            tokens += retry_tokens
    except LLMNetworkError as exc:
        return {
            "answer": INSUFFICIENT_EVIDENCE_ANSWER,
            "citation_labels": [],
            "tokens_used": 0,
            "context_blocks": blocks,
            "question_shape": "sentence_window",
            "error": str(exc),
        }

    return {
        "answer": result.answer,
        "citation_labels": result.citations,
        "tokens_used": tokens,
        "context_blocks": blocks,
        "question_shape": "sentence_window",
    }


def rank_hit_windows(
    hits: Sequence[Any],
    *,
    k: int,
) -> list[tuple[Any, float]]:
    """Rank ANN hits by hybrid score and deduplicate by span id (test helper)."""
    if not hits:
        return []

    effective_dates = [hit.published_at or hit.fetched_at for hit in hits]
    recency_min = min(effective_dates)
    recency_max = max(effective_dates)

    scored_hits = [
        (
            hit,
            _hybrid_hit_score(
                float(hit.semantic_sim),
                hit.published_at,
                hit.fetched_at,
                recency_min,
                recency_max,
            ),
        )
        for hit in hits
    ]
    scored_hits.sort(key=lambda item: item[1], reverse=True)

    seen_hit_ids: set[uuid.UUID] = set()
    selected: list[tuple[Any, float]] = []
    for hit, score in scored_hits:
        if hit.id in seen_hit_ids:
            continue
        seen_hit_ids.add(hit.id)
        selected.append((hit, score))
        if len(selected) >= k:
            break
    return selected
