from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import delete, select, text
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
from app.intelligence.entities import extract_entities
from app.intelligence.llm_client import LLMNetworkError, LLMSchemaError
from app.intelligence.prompts.chat_answer import (
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_INFERENCE,
    build_user_prompt,
)

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

    entity_lists: list[list[str]] | None = None
    if settings.sentence_window_entity_anchoring:
        entity_lists = extract_entities(sentences)
    vectors = embedder.embed(sentences)

    async with session_factory() as session:
        # Idempotent re-ingest: drop any prior spans for this document so a re-index
        # (API re-ingest, partial resume) doesn't duplicate spans and corrupt windows.
        await session.execute(delete(Span).where(Span.document_id == document_id))
        for index, (sentence, vector) in enumerate(zip(sentences, vectors, strict=True)):
            metadata: dict[str, Any] | None = None
            if speaker is not None or entity_lists is not None:
                metadata = {}
                if speaker is not None:
                    metadata["speaker"] = speaker
                if entity_lists is not None:
                    metadata["entities"] = entity_lists[index]
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
    scope: str | None = None,
) -> list[Any]:
    distance = Span.embedding.cosine_distance(query_vec)
    stmt = (
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
    )
    if scope is not None:
        stmt = stmt.where(Document.scope == scope)
    rows = (await session.execute(stmt.order_by(distance).limit(fetch_k))).all()
    return list(rows)


_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def _lexical_tsquery(question: str) -> str:
    """OR-of-terms tsquery string from question tokens (recall-oriented, injection-safe)."""
    seen: dict[str, None] = {}
    for tok in _WORD_RE.findall(question.lower()):
        if len(tok) > 2:
            seen.setdefault(tok, None)
    return " | ".join(seen)


async def _fetch_lexical_hits(
    session: AsyncSession,
    question: str,
    fetch_k: int,
    scope: str | None = None,
) -> list[Any]:
    tsq = _lexical_tsquery(question)
    if not tsq:
        return []
    params: dict[str, Any] = {"tsq": tsq, "k": fetch_k}
    # ponytail: on-the-fly to_tsvector (LoCoMo corpora are ~hundreds of spans); add a
    # GIN index on to_tsvector('english', text) if this ever runs on large corpora.
    if scope is not None:
        params["scope"] = scope
        stmt = text(
            """
            SELECT s.id, s.document_id, s.span_index, s.text,
                   ts_rank(to_tsvector('english', s.text), to_tsquery('english', :tsq)) AS semantic_sim,
                   d.title AS title, d.url AS url, d.published_at AS published_at, d.fetched_at AS fetched_at
            FROM spans s JOIN documents d ON s.document_id = d.id
            WHERE s.embedding IS NOT NULL
              AND to_tsvector('english', s.text) @@ to_tsquery('english', :tsq)
              AND d.scope = :scope
            ORDER BY semantic_sim DESC
            LIMIT :k
            """
        )
    else:
        stmt = text(
            """
            SELECT s.id, s.document_id, s.span_index, s.text,
                   ts_rank(to_tsvector('english', s.text), to_tsquery('english', :tsq)) AS semantic_sim,
                   d.title AS title, d.url AS url, d.published_at AS published_at, d.fetched_at AS fetched_at
            FROM spans s JOIN documents d ON s.document_id = d.id
            WHERE s.embedding IS NOT NULL
              AND to_tsvector('english', s.text) @@ to_tsquery('english', :tsq)
            ORDER BY semantic_sim DESC
            LIMIT :k
            """
        )
    try:
        rows = (await session.execute(stmt, params)).all()
    except Exception:  # noqa: BLE001 - malformed tsquery falls back to semantic-only
        return []
    return list(rows)


async def _fetch_entity_hits(
    session: AsyncSession,
    entities: list[str],
    fetch_k: int,
    scope: str | None = None,
) -> list[Any]:
    if not entities:
        return []
    params: dict[str, Any] = {"ents": entities, "k": fetch_k}
    if scope is not None:
        params["scope"] = scope
        stmt = text(
            """
            SELECT s.id, s.document_id, s.span_index, s.text,
                   (
                     SELECT count(*)::int
                     FROM jsonb_array_elements_text(s.metadata_json->'entities') ent
                     WHERE ent = ANY(:ents)
                   ) AS match_count,
                   d.title AS title, d.url AS url,
                   d.published_at AS published_at, d.fetched_at AS fetched_at
            FROM spans s JOIN documents d ON s.document_id = d.id
            WHERE s.embedding IS NOT NULL
              AND s.metadata_json->'entities' ?| :ents
              AND d.scope = :scope
            ORDER BY match_count DESC, s.span_index
            LIMIT :k
            """
        )
    else:
        stmt = text(
            """
            SELECT s.id, s.document_id, s.span_index, s.text,
                   (
                     SELECT count(*)::int
                     FROM jsonb_array_elements_text(s.metadata_json->'entities') ent
                     WHERE ent = ANY(:ents)
                   ) AS match_count,
                   d.title AS title, d.url AS url,
                   d.published_at AS published_at, d.fetched_at AS fetched_at
            FROM spans s JOIN documents d ON s.document_id = d.id
            WHERE s.embedding IS NOT NULL
              AND s.metadata_json->'entities' ?| :ents
            ORDER BY match_count DESC, s.span_index
            LIMIT :k
            """
        )
    try:
        rows = (await session.execute(stmt, params)).all()
    except Exception:  # noqa: BLE001 - malformed entity query falls back to other channels
        return []
    return list(rows)


def _rrf_fuse(ranked_lists: list[list[Any]], k: int, *, k_rrf: int = 60) -> list[Any]:
    """Reciprocal-rank fusion across ranked hit lists; dedup by span id, return top-k hits."""
    scores: dict[uuid.UUID, float] = {}
    hit_by_id: dict[uuid.UUID, Any] = {}
    for ranked in ranked_lists:
        for rank, hit in enumerate(ranked):
            scores[hit.id] = scores.get(hit.id, 0.0) + 1.0 / (k_rrf + rank)
            hit_by_id.setdefault(hit.id, hit)
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [hit_by_id[hid] for hid, _ in ordered[:k]]


class _SubQueries(BaseModel):
    subqueries: list[str]


_DECOMPOSE_SYSTEM = (
    "Break the user's question into 2-3 short, focused sub-questions that each "
    "retrieve one fact needed to answer it. If the question is already atomic, "
    'return it unchanged as a single item. Return JSON: {"subqueries": [...]}.'
)


async def _decompose_question(client: Any, model: str, question: str) -> tuple[list[str], int]:
    try:
        result, tokens = await client.complete_json(
            model=model,
            system=_DECOMPOSE_SYSTEM,
            user=question,
            response_model=_SubQueries,
            run_type="chat_answer",
            max_tokens=300,
        )
    except (LLMSchemaError, LLMNetworkError):
        return [], 0
    subs = [s.strip() for s in result.subqueries if s.strip()][:3]
    return subs, tokens


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


async def _build_blocks(
    session: AsyncSession,
    hits: list[Any],
    scores: list[float],
    window: int,
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    label_index = 0
    for hit, score in zip(hits, scores, strict=True):
        neighbors = await _fetch_neighbor_spans(session, hit.document_id, hit.span_index, window)
        if not neighbors:
            continue
        label_index += 1
        blocks.append(
            {
                "label": f"C{label_index}",
                "text": " ".join(row.text for row in neighbors),
                "published_at": hit.published_at,
                "span_ids": [row.id for row in neighbors],
                "document_id": hit.document_id,
                "document_title": hit.title,
                "url": hit.url,
                "score": score,
                "first_span_index": neighbors[0].span_index,
            }
        )
    return _order_context_blocks(blocks)


async def retrieve_windows(
    session: AsyncSession,
    embedder: Any,
    question: str,
    *,
    fetch_k: int,
    window: int,
    k: int,
    as_of: datetime | None,
    queries: list[str] | None = None,
    hybrid: bool = False,
    scope: str | None = None,
) -> list[dict[str, Any]]:
    del as_of  # reserved for prompt assembly in answer_sentence_window
    sentinel = await session.scalar(select(Span).where(Span.embedding.isnot(None)).limit(1))
    if sentinel is None:
        return []

    all_queries = queries or [question]
    use_rrf = hybrid or len(all_queries) > 1 or settings.sentence_window_entity_anchoring
    if use_rrf:
        # RRF fusion across per-query semantic (and lexical) ranked lists. A span
        # appearing in several lists is rewarded, surfacing cross-query/cross-modal hits.
        ranked_lists: list[list[Any]] = []
        for q in all_queries:
            ranked_lists.append(
                await _fetch_ann_hits(session, embedder.embed_one(q), fetch_k, scope)
            )
            if hybrid:
                lexical = await _fetch_lexical_hits(session, q, fetch_k, scope)
                if lexical:
                    ranked_lists.append(lexical)
        if settings.sentence_window_entity_anchoring:
            question_entities = extract_entities([question])[0]
            ranked_lists.append(
                await _fetch_entity_hits(session, question_entities, fetch_k, scope)
            )
        fused = _rrf_fuse(ranked_lists, k)
        if not fused:
            return []
        return await _build_blocks(session, fused, [0.0] * len(fused), window)

    hits = await _fetch_ann_hits(session, embedder.embed_one(question), fetch_k, scope)
    if not hits:
        return []
    selected = rank_hit_windows(hits, k=k)
    return await _build_blocks(session, [h for h, _ in selected], [s for _, s in selected], window)


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
    scope: str | None = None,
) -> dict[str, Any]:
    del pack  # sentence-window path does not use pack retrieval policy in the MVP
    tokens = 0
    queries = [question]
    if settings.sentence_window_subqueries:
        subs, decompose_tokens = await _decompose_question(client, model, question)
        tokens += decompose_tokens
        queries = [question, *subs]

    async with session_factory() as session:
        blocks = await retrieve_windows(
            session,
            embedder,
            question,
            fetch_k=fetch_k,
            window=window,
            k=k,
            as_of=as_of,
            queries=queries,
            hybrid=settings.sentence_window_hybrid,
            scope=scope,
        )

    if not blocks:
        return {
            "answer": INSUFFICIENT_EVIDENCE_ANSWER,
            "citation_labels": [],
            "tokens_used": tokens,
            "context_blocks": [],
            "question_shape": "sentence_window",
        }

    user = build_user_prompt(question, blocks, as_of=as_of)
    system_prompt = (
        SYSTEM_PROMPT_INFERENCE if settings.sentence_window_permit_inference else SYSTEM_PROMPT
    )
    try:
        try:
            result, answer_tokens = await client.complete_json(
                model=model,
                system=system_prompt,
                user=user,
                response_model=ChatAnswerOutput,
                run_type="chat_answer",
                max_tokens=4000,
            )
            tokens += answer_tokens
        except LLMSchemaError:
            result, retry_tokens = await client.complete_json(
                model=model,
                system=system_prompt + _SCHEMA_RETRY_SUFFIX,
                user=user,
                response_model=ChatAnswerOutput,
                run_type="chat_answer",
                max_tokens=4000,
            )
            tokens += retry_tokens
    except (LLMNetworkError, LLMSchemaError) as exc:
        # A second schema failure after the one-shot retry degrades to the same
        # error-shaped abstention as a network failure rather than bubbling up.
        return {
            "answer": INSUFFICIENT_EVIDENCE_ANSWER,
            "citation_labels": [],
            "tokens_used": tokens,
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
