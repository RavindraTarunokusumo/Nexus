from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import CapsuleSegment, Document, SemanticCapsule, SemanticRelation, Span
from app.domain_packs.loader import load_pack
from app.intelligence.llm_client import LLMError, LLMNetworkError
from app.intelligence.prompts.chat_answer import SYSTEM_PROMPT, build_user_prompt
from app.intelligence.prompts.classify_intent import (
    SYSTEM_PROMPT as _INTENT_SYSTEM_PROMPT,
)
from app.intelligence.prompts.classify_intent import (
    IntentClassification,
    build_classify_prompt,
)
from app.intelligence.router import QUESTION_SHAPES, resolve_strategy
from app.observability.run_context import chat_run


class ChatAnswerOutput(BaseModel):
    answer: str
    citations: list[str]


class CitationEvidence(BaseModel):
    span_id: uuid.UUID
    span_index: int
    text: str


class ChatCitation(BaseModel):
    document_id: uuid.UUID
    capsule_id: uuid.UUID
    document_title: str | None
    url: str | None
    score: float
    object_type: str | None
    object_family: str | None
    lifecycle_state: str | None
    summary: str
    evidence: list[CitationEvidence] = []
    role: str | None = None
    epistemic_note: str | None = None


class ChatState(TypedDict):
    question: str
    top_k: int
    model: str
    run_id: uuid.UUID | None
    query_intent: str
    question_shape: str
    pack: Any
    context_blocks: list[dict[str, Any]]
    answer: str
    citation_labels: list[str]
    citations: list[dict[str, Any]]
    tokens_used: int
    error: str | None


INSUFFICIENT_EVIDENCE_ANSWER = (
    "I do not have enough evidence to answer that from the current corpus."
)

_PRIORITY_SCORES = [1.0, 0.5, 0.25, 0.1]
_MAX_EVIDENCE_SPANS = 5
_EVIDENCE_EXCERPT_CHARS = 280
_LIFECYCLE_RETRIEVAL_STATES = ("active", "confirmed", "qualified")
_AUTHORITY_SCORES = {"primary": 1.0, "secondary": 0.66, "tertiary": 0.33}
_EVIDENCE_QUALITY_SCORES = {"high": 1.0, "medium": 0.6, "low": 0.3}
_MAX_COUNTER_EVIDENCE = 2
_MAX_SUPERSESSION = 2


def estimate_tokens(text: str) -> int:
    """Cheap char-based token estimate (~4 chars/token). Sufficient for a soft budget gate."""
    return (len(text) + 3) // 4


def _authority_score(epistemic_state: dict) -> float:
    authority = epistemic_state.get("source_authority", "unknown")
    return _AUTHORITY_SCORES.get(authority, 0.5)


def _evidence_quality_score(epistemic_state: dict) -> float:
    quality = epistemic_state.get("evidence_quality", "unknown")
    return _EVIDENCE_QUALITY_SCORES.get(quality, 0.5)


def _relation_relevance_score(relation_count: int) -> float:
    return min(1.0, relation_count / 4)


def _evidence_strength_key(block: dict[str, Any]) -> float:
    epistemic = block.get("epistemic_state") or {}
    confidence = block.get("confidence", 0.5)
    return (
        0.5 * _evidence_quality_score(epistemic)
        + 0.3 * _authority_score(epistemic)
        + 0.2 * confidence
    )


def _format_epistemic_note(
    epistemic_state: dict,
    lifecycle_state: str,
    *,
    suffix: str = "",
) -> str:
    authority = epistemic_state.get("source_authority", "unknown")
    status = epistemic_state.get("status", "unknown")
    evidence_quality = epistemic_state.get("evidence_quality", "unknown")
    note = (
        f"authority={authority}; status={status}; "
        f"evidence_quality={evidence_quality}; lifecycle={lifecycle_state}"
    )
    if suffix:
        note = f"{note}; {suffix}"
    return note


def _count_relations_per_capsule(
    capsule_ids: set[uuid.UUID],
    relation_rows: list[Any],
) -> dict[uuid.UUID, int]:
    counts = dict.fromkeys(capsule_ids, 0)
    for src, tgt, _rel_type, _polarity in relation_rows:
        if src in counts:
            counts[src] += 1
        if tgt is not None and tgt in counts:
            counts[tgt] += 1
    return counts


def _is_counter_evidence_relation(relation_type: str, polarity: str | None) -> bool:
    return relation_type == "contradicts" or polarity == "negative"


def _discover_counter_evidence_ids(
    selected_ids: set[uuid.UUID],
    relation_rows: list[Any],
) -> list[uuid.UUID]:
    linked: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for src, tgt, rel_type, polarity in relation_rows:
        if tgt is None or not _is_counter_evidence_relation(rel_type, polarity):
            continue
        for anchor, other in ((src, tgt), (tgt, src)):
            if anchor in selected_ids and other not in selected_ids and other not in seen:
                linked.append(other)
                seen.add(other)
                if len(linked) >= _MAX_COUNTER_EVIDENCE:
                    return linked
    return linked


def _discover_supersession_links(
    selected_ids: set[uuid.UUID],
    relation_rows: list[Any],
) -> list[tuple[uuid.UUID, str]]:
    """Return (linked_capsule_id, direction) where direction is superseding or superseded."""
    links: list[tuple[uuid.UUID, str]] = []
    seen: set[tuple[uuid.UUID, str]] = set()
    for src, tgt, rel_type, _polarity in relation_rows:
        if rel_type != "supersedes" or tgt is None:
            continue
        if src in selected_ids and tgt not in selected_ids:
            key = (tgt, "superseded")
            if key not in seen:
                links.append(key)
                seen.add(key)
        if tgt in selected_ids and src not in selected_ids:
            key = (src, "superseding")
            if key not in seen:
                links.append(key)
                seen.add(key)
        if len(links) >= _MAX_SUPERSESSION:
            return links
    return links


def _order_context_blocks(
    primary_blocks: list[dict[str, Any]],
    auxiliary_blocks: list[dict[str, Any]],
    ordering: str,
    *,
    primary_scores: list[float] | None = None,
) -> list[dict[str, Any]]:
    if ordering == "evidence_strength":
        primary_sorted = sorted(
            primary_blocks,
            key=_evidence_strength_key,
            reverse=True,
        )
        auxiliary_sorted = sorted(
            auxiliary_blocks,
            key=_evidence_strength_key,
            reverse=True,
        )
        return primary_sorted + auxiliary_sorted
    if primary_scores is not None and len(primary_scores) == len(primary_blocks):
        indexed = sorted(
            zip(primary_blocks, primary_scores, strict=True),
            key=lambda item: item[1],
            reverse=True,
        )
        return [block for block, _ in indexed] + auxiliary_blocks
    return primary_blocks + auxiliary_blocks


def _build_context_block(
    cand: dict[str, Any],
    score: float,
    *,
    role: str | None,
    use_epistemic_notes: bool,
    use_evidence: bool,
    evidence_map: dict[uuid.UUID, list[dict[str, Any]]],
    epistemic_suffix: str = "",
) -> dict[str, Any]:
    epistemic = cand.get("epistemic_state") or {}
    block: dict[str, Any] = {
        "document_id": cand["document_id"],
        "capsule_id": cand["id"],
        "document_title": cand["title"],
        "url": cand["url"],
        "score": score,
        "text": cand["text"],
        "object_type": cand["object_type"],
        "object_family": cand["object_family"],
        "lifecycle_state": cand["lifecycle_state"],
        "epistemic_state": epistemic,
        "confidence": cand.get("confidence", 0.5),
    }
    if role is not None:
        block["role"] = role
    if use_epistemic_notes:
        block["epistemic_note"] = _format_epistemic_note(
            epistemic,
            cand["lifecycle_state"],
            suffix=epistemic_suffix,
        )
    if use_evidence:
        block["evidence"] = evidence_map.get(cand["id"], [])
    return block


def _assemble_context_blocks(
    top: list[tuple[dict[str, Any], float]],
    *,
    include: list[str],
    ordering: str,
    evidence_map: dict[uuid.UUID, list[dict[str, Any]]],
    relation_rows: list[Any],
    auxiliary_candidates: dict[uuid.UUID, dict[str, Any]],
) -> list[dict[str, Any]]:
    include_set = set(include)
    flags = {
        "epistemic": "epistemic_notes" in include_set,
        "evidence": "source_refs_and_excerpts" in include_set,
        "primary_role": "highest_salience_relevant_objects" in include_set,
        "counter": "counter_evidence_and_caveats" in include_set,
        "supersession": "superseding_or_superseded_objects" in include_set,
    }

    selected_ids = {c["id"] for c, _ in top}
    primary_blocks: list[dict[str, Any]] = []
    primary_scores: list[float] = []
    for cand, score in top:
        role = "primary" if flags["primary_role"] else None
        primary_blocks.append(
            _build_context_block(
                cand,
                score,
                role=role,
                use_epistemic_notes=flags["epistemic"],
                use_evidence=flags["evidence"],
                evidence_map=evidence_map,
            )
        )
        primary_scores.append(score)

    auxiliary_blocks: list[dict[str, Any]] = []
    if flags["counter"]:
        for linked_id in _discover_counter_evidence_ids(selected_ids, relation_rows):
            aux_cand = auxiliary_candidates.get(linked_id)
            if aux_cand is None:
                continue
            auxiliary_blocks.append(
                _build_context_block(
                    aux_cand,
                    0.0,
                    role="counter_evidence",
                    use_epistemic_notes=flags["epistemic"],
                    use_evidence=flags["evidence"],
                    evidence_map=evidence_map,
                )
            )

    if flags["supersession"]:
        for linked_id, direction in _discover_supersession_links(selected_ids, relation_rows):
            aux_cand = auxiliary_candidates.get(linked_id)
            if aux_cand is None:
                continue
            auxiliary_blocks.append(
                _build_context_block(
                    aux_cand,
                    0.0,
                    role="supersession",
                    use_epistemic_notes=flags["epistemic"],
                    use_evidence=flags["evidence"],
                    evidence_map=evidence_map,
                    epistemic_suffix=f"supersession={direction}",
                )
            )

    ordered = _order_context_blocks(
        primary_blocks,
        auxiliary_blocks,
        ordering,
        primary_scores=primary_scores,
    )
    for i, block in enumerate(ordered, start=1):
        block["label"] = f"C{i}"
    return ordered


def _assemble_within_budget(
    scored: list[tuple[dict, float]],
    top_k: int,
    token_budget: int | None,
) -> list[tuple[dict, float]]:
    """Pick score-ordered blocks under a token budget; top_k caps the count.

    Always includes the highest-scored block even if it alone exceeds the budget.
    token_budget=None falls back to the flat top_k slice.
    """
    if token_budget is None:
        return scored[:top_k]
    selected: list[tuple[dict, float]] = []
    running = 0
    for cand, score in scored:
        if len(selected) >= top_k:
            break
        est = estimate_tokens(cand["text"])
        if selected and running + est > token_budget:
            break
        selected.append((cand, score))
        running += est
    return selected


def _build_evidence_map(
    rows: list,
    max_spans: int,
    excerpt_chars: int,
) -> dict[uuid.UUID, list[dict[str, Any]]]:
    """Shape (capsule_id, span_id, span_index, text) rows into per-capsule excerpts.

    Rows must arrive ordered by capsule_id then span_index. Keeps up to max_spans per
    capsule and caps each excerpt at excerpt_chars total characters (when cut, a trailing
    ellipsis replaces the final character, so the result is exactly excerpt_chars long).
    """
    out: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for capsule_id, span_id, span_index, text in rows:
        bucket = out.setdefault(capsule_id, [])
        if len(bucket) >= max_spans:
            continue
        excerpt = text if len(text) <= excerpt_chars else text[: excerpt_chars - 1] + "…"
        bucket.append({"span_id": span_id, "span_index": span_index, "text": excerpt})
    return out


def _normalize_citation_label(label: str) -> str:
    return label.strip().removeprefix("[").removesuffix("]").strip()


def _row_to_candidate(row: Any, relation_count: int) -> dict[str, Any]:
    return {
        "id": row.id,
        "document_id": row.document_id,
        "text": row.text,
        "object_type": row.domain_object_type,
        "object_family": row.object_family,
        "lifecycle_state": row.lifecycle_state,
        "salience": row.salience,
        "created_at": row.created_at,
        "semantic_sim": float(row.semantic_sim),
        "title": row.title,
        "url": row.url,
        "epistemic_state": row.epistemic_state or {},
        "confidence": row.confidence,
        "relation_count": relation_count,
    }


async def _fetch_capsules_by_ids(
    session: Any,
    capsule_ids: list[uuid.UUID],
) -> dict[uuid.UUID, dict[str, Any]]:
    if not capsule_ids:
        return {}
    rows = (
        await session.execute(
            select(
                SemanticCapsule.id,
                SemanticCapsule.document_id,
                SemanticCapsule.text,
                SemanticCapsule.domain_object_type,
                SemanticCapsule.object_family,
                SemanticCapsule.lifecycle_state,
                SemanticCapsule.salience,
                SemanticCapsule.created_at,
                SemanticCapsule.epistemic_state,
                SemanticCapsule.confidence,
                Document.title.label("title"),
                Document.url.label("url"),
            )
            .join(Document, SemanticCapsule.document_id == Document.id)
            .where(SemanticCapsule.id.in_(capsule_ids))
        )
    ).all()
    return {
        row.id: {
            "id": row.id,
            "document_id": row.document_id,
            "text": row.text,
            "object_type": row.domain_object_type,
            "object_family": row.object_family,
            "lifecycle_state": row.lifecycle_state,
            "salience": row.salience,
            "created_at": row.created_at,
            "title": row.title,
            "url": row.url,
            "epistemic_state": row.epistemic_state or {},
            "confidence": row.confidence,
        }
        for row in rows
    }


def compute_hybrid_score(
    candidate: dict,
    weights: dict[str, float],
    retrieval_priorities: list[str],
    recency_min: datetime,
    recency_max: datetime,
) -> float:
    """Telos-aware hybrid score using epistemic_state and relation_count when present."""
    sem = candidate["semantic_sim"] * weights.get("semantic_similarity", 0.0)

    if not retrieval_priorities:
        dom_score = 0.5
    else:
        family = candidate["object_family"]
        try:
            rank = retrieval_priorities.index(family)
            dom_score = _PRIORITY_SCORES[rank] if rank < len(_PRIORITY_SCORES) else 0.1
        except ValueError:
            dom_score = 0.0
    dom = dom_score * weights.get("domain_object_type_match", 0.0)

    epistemic = candidate.get("epistemic_state") or {}
    auth = _authority_score(epistemic) * weights.get("source_authority", 0.0)

    created_at = candidate["created_at"]
    if recency_min == recency_max:
        rec_score = 0.5
    else:
        span = (recency_max - recency_min).total_seconds()
        rec_score = (created_at - recency_min).total_seconds() / span
        rec_score = max(0.0, min(1.0, rec_score))
    rec = rec_score * weights.get("recency", 0.0)

    sal = candidate["salience"] * weights.get("salience", 0.0)

    rel_count = candidate.get("relation_count", 0)
    rel = _relation_relevance_score(rel_count) * weights.get("relation_relevance", 0.0)

    evid = _evidence_quality_score(epistemic) * weights.get("evidence_quality", 0.0)

    return sem + dom + auth + rec + sal + rel + evid


def _validate_shape(shape: str) -> str:
    return shape if shape in QUESTION_SHAPES else "general"


async def _run_classify_intent(state: dict, client: Any) -> dict:
    pack = state.get("pack")
    if pack is None:
        return {"query_intent": "general", "question_shape": "general"}
    intent_names = list(pack.retrieval_policy.query_intents.keys())
    try:
        result, _ = await client.complete_json(
            model=state["model"],
            system=_INTENT_SYSTEM_PROMPT,
            user=build_classify_prompt(state["question"], intent_names),
            response_model=IntentClassification,
            run_type="chat_classify_intent",
        )
        intent = result.intent if result.intent in intent_names else "general"
        shape = _validate_shape(result.shape)
    except LLMError:
        intent = "general"
        shape = "general"
    return {"query_intent": intent, "question_shape": shape}


async def _run_retrieve_capsules(
    state: dict,
    session_factory: async_sessionmaker,
    embedder: Any,
) -> dict:
    pack = state.get("pack")
    query_intent = state.get("query_intent", "general")
    retrieval_priorities: list[str] = []
    if pack is not None and query_intent != "general":
        intent_cfg = pack.retrieval_policy.query_intents.get(query_intent, {})
        retrieval_priorities = intent_cfg.get("retrieval_priorities", [])

    weights: dict[str, float] = {}
    token_budget: int | None = None
    include: list[str] = []
    ordering = "evidence_strength"
    if pack is not None:
        weights = dict(pack.retrieval_policy.hybrid_score_weights)
        token_budget = pack.context_assembly.max_tokens_by_tier.get("T2")
        include = list(pack.context_assembly.include)
        ordering = pack.context_assembly.ordering

    strategy = resolve_strategy(state.get("question_shape", "general"))
    weights.update(strategy.weight_overrides)
    effective_top_k = max(1, state["top_k"] + strategy.top_k_delta)
    fetch_k = effective_top_k * strategy.fetch_k_multiplier

    async with session_factory() as session:
        sentinel = await session.scalar(
            select(SemanticCapsule).where(SemanticCapsule.embedding.isnot(None)).limit(1)
        )
        if sentinel is None:
            return {"context_blocks": []}

        query_vec = embedder.embed_one(state["question"])
        distance = SemanticCapsule.embedding.cosine_distance(query_vec)
        rows = (
            await session.execute(
                select(
                    SemanticCapsule.id,
                    SemanticCapsule.document_id,
                    SemanticCapsule.text,
                    SemanticCapsule.domain_object_type,
                    SemanticCapsule.object_family,
                    SemanticCapsule.lifecycle_state,
                    SemanticCapsule.salience,
                    SemanticCapsule.created_at,
                    SemanticCapsule.epistemic_state,
                    SemanticCapsule.confidence,
                    (1 - distance).label("semantic_sim"),
                    Document.title.label("title"),
                    Document.url.label("url"),
                )
                .join(Document, SemanticCapsule.document_id == Document.id)
                .where(SemanticCapsule.embedding.isnot(None))
                .where(SemanticCapsule.lifecycle_state.in_(_LIFECYCLE_RETRIEVAL_STATES))
                .order_by(distance)
                .limit(fetch_k)
            )
        ).all()

        if not rows:
            return {"context_blocks": []}

        candidate_ids = {r.id for r in rows}
        relation_rows = (
            await session.execute(
                select(
                    SemanticRelation.source_capsule_id,
                    SemanticRelation.target_capsule_id,
                    SemanticRelation.relation_type,
                    SemanticRelation.polarity,
                ).where(
                    or_(
                        SemanticRelation.source_capsule_id.in_(candidate_ids),
                        SemanticRelation.target_capsule_id.in_(candidate_ids),
                    )
                )
            )
        ).all()
        relation_counts = _count_relations_per_capsule(candidate_ids, relation_rows)

        created_ats = [r.created_at for r in rows]
        recency_min: datetime = min(created_ats)
        recency_max: datetime = max(created_ats)

        candidates = [_row_to_candidate(r, relation_counts.get(r.id, 0)) for r in rows]

        scored = sorted(
            [
                (
                    c,
                    compute_hybrid_score(
                        c, weights, retrieval_priorities, recency_min, recency_max
                    ),
                )
                for c in candidates
            ],
            key=lambda x: x[1],
            reverse=True,
        )
        top = _assemble_within_budget(scored, effective_top_k, token_budget)

        selected_ids = {c["id"] for c, _ in top}
        auxiliary_ids: list[uuid.UUID] = []
        if "counter_evidence_and_caveats" in include:
            auxiliary_ids.extend(_discover_counter_evidence_ids(selected_ids, relation_rows))
        if "superseding_or_superseded_objects" in include:
            auxiliary_ids.extend(
                linked_id
                for linked_id, _direction in _discover_supersession_links(
                    selected_ids,
                    relation_rows,
                )
            )
        auxiliary_ids = list(dict.fromkeys(auxiliary_ids))

        auxiliary_candidates = await _fetch_capsules_by_ids(session, auxiliary_ids)

        evidence_capsule_ids = list(selected_ids | set(auxiliary_ids))
        evidence_map: dict[uuid.UUID, list[dict[str, Any]]] = {}
        if evidence_capsule_ids and "source_refs_and_excerpts" in include:
            evidence_rows = (
                await session.execute(
                    select(
                        CapsuleSegment.capsule_id,
                        Span.id,
                        Span.span_index,
                        Span.text,
                    )
                    .join(Span, CapsuleSegment.segment_id == Span.id)
                    .where(CapsuleSegment.capsule_id.in_(evidence_capsule_ids))
                    .order_by(CapsuleSegment.capsule_id, Span.span_index)
                )
            ).all()
            evidence_map = _build_evidence_map(
                evidence_rows, _MAX_EVIDENCE_SPANS, _EVIDENCE_EXCERPT_CHARS
            )

        blocks = _assemble_context_blocks(
            top,
            include=include,
            ordering=ordering,
            evidence_map=evidence_map,
            relation_rows=relation_rows,
            auxiliary_candidates=auxiliary_candidates,
        )

    return {"context_blocks": blocks}


def make_chat_graph(session_factory: async_sessionmaker, client: Any, embedder: Any):
    async def classify_intent(state: ChatState) -> dict:
        return await _run_classify_intent(state, client)

    async def retrieve_capsules(state: ChatState) -> dict:
        return await _run_retrieve_capsules(state, session_factory, embedder)

    async def generate_answer(state: ChatState) -> dict:
        if not state.get("context_blocks"):
            return {"answer": INSUFFICIENT_EVIDENCE_ANSWER, "citation_labels": [], "tokens_used": 0}
        strategy = resolve_strategy(state.get("question_shape", "general"))
        user = build_user_prompt(
            state["question"],
            state["context_blocks"],
            hint=strategy.answer_hint,
        )
        try:
            result, tokens = await client.complete_json(
                model=state["model"],
                system=SYSTEM_PROMPT,
                user=user,
                response_model=ChatAnswerOutput,
                run_type="chat_answer",
            )
        except LLMNetworkError as exc:
            return {"error": str(exc), "tokens_used": 0}
        return {"answer": result.answer, "citation_labels": result.citations, "tokens_used": tokens}

    async def format_result(state: ChatState) -> dict:
        blocks_by_label = {block["label"]: block for block in state.get("context_blocks", [])}
        citation_labels = list(
            dict.fromkeys(
                _normalize_citation_label(lbl) for lbl in state.get("citation_labels", [])
            )
        )
        citations: list[dict[str, Any]] = []
        for label in citation_labels:
            block = blocks_by_label.get(label)
            if block is None:
                continue
            citations.append(
                ChatCitation(
                    document_id=block["document_id"],
                    capsule_id=block["capsule_id"],
                    document_title=block.get("document_title"),
                    url=block.get("url"),
                    score=block["score"],
                    object_type=block.get("object_type"),
                    object_family=block.get("object_family"),
                    lifecycle_state=block.get("lifecycle_state"),
                    summary=block["text"],
                    evidence=block.get("evidence", []),
                    role=block.get("role"),
                    epistemic_note=block.get("epistemic_note"),
                ).model_dump()
            )
        if state.get("context_blocks") and not citations:
            return {"answer": INSUFFICIENT_EVIDENCE_ANSWER, "citations": []}
        return {
            "answer": state.get("answer") or INSUFFICIENT_EVIDENCE_ANSWER,
            "citations": citations,
        }

    def route_after_retrieve(state: ChatState) -> str:
        return "generate_answer" if state.get("context_blocks") else "format_result"

    builder = StateGraph(ChatState)
    builder.add_node("classify_intent", classify_intent)
    builder.add_node("retrieve_capsules", retrieve_capsules)
    builder.add_node("generate_answer", generate_answer)
    builder.add_node("format_result", format_result)

    builder.set_entry_point("classify_intent")
    builder.add_edge("classify_intent", "retrieve_capsules")
    builder.add_conditional_edges(
        "retrieve_capsules",
        route_after_retrieve,
        {"generate_answer": "generate_answer", "format_result": "format_result"},
    )
    builder.add_edge("generate_answer", "format_result")
    builder.add_edge("format_result", END)

    return builder.compile()


async def run_chat_with_context(
    graph: Any,
    question: str,
    model: str,
    *,
    top_k: int,
    pack: Any = None,
) -> dict:
    if pack is None:
        from app.config import settings

        pack = load_pack(settings.default_pack_id)
    async with chat_run() as run_id:
        final = await graph.ainvoke(
            {
                "question": question,
                "top_k": top_k,
                "model": model,
                "run_id": run_id,
                "query_intent": "general",
                "question_shape": "general",
                "pack": pack,
                "context_blocks": [],
                "answer": "",
                "citation_labels": [],
                "citations": [],
                "tokens_used": 0,
                "error": None,
            }
        )
    final["run_id"] = run_id
    return final
