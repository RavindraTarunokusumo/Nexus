"""LangGraph extraction graph: per-span semantic-object extraction (v0.7),
validate-and-project against the source's domain pack, and write the
projected claims into the legacy claims/claim_evidence tables.

B2 dual-write: store_claims also writes SemanticCapsule + CapsuleSegment rows
in the same transaction as Claim + ClaimEvidence. validate_and_project threads
live SemanticObject instances alongside ProjectedClaims via the new
`semantic_objects` state field so store_claims has both without extending
ProjectedClaim (option b — keeps projection layer clean).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, TypedDict
from urllib.parse import SplitResult, urlsplit

from langgraph.graph import END, StateGraph
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import (
    Claim,
    ClaimEvidence,
    Document,
    SemanticCapsule,
    SemanticRelation,
    Source,
    Span,
)
from app.domain_packs.loader import DomainPack, load_pack
from app.intelligence.capsules import build_capsule_row, get_embedder
from app.intelligence.llm_client import (
    LLMError,
    LLMNetworkError,
    LLMSchemaError,
    SemanticExtractionOutput,
    SemanticObject,
)
from app.intelligence.projection import (
    ProjectedClaim,
    enforce_budgets,
    project,
    validate_object,
)
from app.intelligence.prompts.classify_relations import (
    SYSTEM_PROMPT as CLASSIFY_SYSTEM_PROMPT,
)
from app.intelligence.prompts.classify_relations import (
    RelationClassification,
    build_relation_prompt,
)
from app.intelligence.prompts.extract_semantic_objects import (
    SYSTEM_PROMPT as SEMANTIC_SYSTEM_PROMPT,
)
from app.intelligence.prompts.extract_semantic_objects import (
    build_correction_prompt as build_semantic_correction_prompt,
)
from app.intelligence.prompts.extract_semantic_objects import (
    build_source_prompt_prefix as build_semantic_source_prefix,
)
from app.intelligence.prompts.extract_semantic_objects import (
    build_user_prompt as build_semantic_user_prompt,
)
from app.intelligence.prompts.judge_semantic_object import (
    SYSTEM_PROMPT as JUDGE_SYSTEM_PROMPT,
)
from app.intelligence.prompts.judge_semantic_object import (
    JudgeVerdict,
    build_judge_prompt,
)
from app.observability.run_context import extraction_run, span_scope
from app.observability.tracer import mark_document_timestamp, record_span_extraction

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2


def _url_matches_domain(parsed: SplitResult | None, hint: str) -> bool:
    """Return True if the pre-parsed URL matches *hint* without suffix spoofing.

    hint may be:
    - a bare hostname          e.g. "arxiv.org"
    - hostname + path prefix   e.g. "openai.com/blog"

    Matching rules:
    - hostname must equal host_hint or end with "." + host_hint
      (so "notarxiv.org" does NOT match "arxiv.org").
    - when hint includes a path, the URL path must start with "/" + path_hint.

    Callers pre-parse with ``urlsplit`` once per document and pass the result
    in; pass ``None`` when there is no URL to match.
    """
    if parsed is None:
        return False
    if "/" in hint:
        host_hint, path_hint = hint.split("/", 1)
    else:
        host_hint, path_hint = hint, None

    hostname = (parsed.hostname or "").lower()
    host_hint = host_hint.lower()

    host_ok = hostname == host_hint or hostname.endswith("." + host_hint)
    if not host_ok:
        return False
    if path_hint is not None:
        return parsed.path.startswith("/" + path_hint)
    return True


def _load_spans_failure(error_msg: str) -> dict:
    """Return a uniform failure dict for the load_spans node early-exit paths."""
    return {
        "error": error_msg,
        "run_id": None,
        "pack": None,
        "source_type": None,
        "source_id": None,
    }


def _resolve_t2_model(pack: DomainPack, fallback: str) -> str:
    """Extract the T2 model string from pack.model_extra['models']['t2'].

    Falls back to fallback when the pack has no top-level 'models' key
    or the T2 entry is missing.  Handles both string values and dict values
    (dict: use 'extractor' or 'model' sub-key).
    """
    extra = getattr(pack, "model_extra", {}) or {}
    top_models = extra.get("models") or {}
    if isinstance(top_models, dict):
        t2 = top_models.get("t2") or top_models.get("T2")
        if isinstance(t2, str):
            return t2
        if isinstance(t2, dict):
            return t2.get("extractor") or t2.get("model") or fallback
    return fallback


def _capsule_to_obj_for_judge(capsule: SemanticCapsule) -> SemanticObject:
    """Reconstruct a minimal SemanticObject from capsule columns for T2 judge input.

    ``source_refs`` (min-length-1 validator) and ``mvp_claim_type`` are not
    used by ``build_judge_prompt``; they receive safe placeholder values so
    SemanticObject validates correctly without an extra DB query.
    """
    epistemic = dict(capsule.epistemic_state or {})
    epistemic.setdefault("status", "asserted_by_source")
    epistemic.setdefault("source_authority", "unknown")
    epistemic.setdefault("confidence", float(capsule.confidence or 0.5))
    epistemic.setdefault("evidence_quality", "unknown")
    epistemic.setdefault("needs_escalation", capsule.escalation_state == "flagged")
    return SemanticObject.model_validate(
        {
            "core_type": capsule.core_type,
            "domain_family": capsule.object_family,
            "domain_object_type": capsule.domain_object_type,
            "function": capsule.function or "",
            "text": capsule.text,
            "facets": capsule.facets or {},
            "salience": float(capsule.salience or 0.5),
            "source_refs": ["00000000-0000-0000-0000-000000000000"],
            "epistemic": epistemic,
            "mvp_claim_type": "other",
        }
    )


# Document status lifecycle constants (extends the ingestion statuses with the
# extraction outcomes; centralised here so routes_claims and tests can import them).
STATUS_EMBEDDED = "embedded"
STATUS_CLAIMS_EXTRACTED = "claims_extracted"
STATUS_EXTRACTION_PARTIAL = "extraction_partial"
STATUS_EXTRACTION_FAILED = "extraction_failed"

POST_EXTRACTION_STATUSES = (
    STATUS_EMBEDDED,
    STATUS_CLAIMS_EXTRACTED,
    STATUS_EXTRACTION_PARTIAL,
    STATUS_EXTRACTION_FAILED,
)


class ExtractionState(TypedDict):
    document_id: uuid.UUID
    run_id: uuid.UUID | None
    model: str
    pack: DomainPack | None  # set in load_spans
    source_type: str | None  # set in load_spans
    source_id: uuid.UUID | None  # set in load_spans; needed by store_claims for capsule.source_id
    spans: list[dict]
    results: list[dict]  # {span_id, objects, tokens, error} — status/error per span
    projected_claims: list[ProjectedClaim]
    # B2: live SemanticObject instances parallel to projected_claims (same index mapping).
    # Allows store_claims to build SemanticCapsule rows without extending ProjectedClaim.
    semantic_objects: list[SemanticObject]
    stored_claim_ids: list[uuid.UUID]
    stored_capsule_ids: list[uuid.UUID]  # C1: parallel to stored_claim_ids; set by store_claims
    judge_results: list[dict]  # C1: [{capsule_id, verdict_dict, relation_id}]
    relation_ids: list[uuid.UUID]  # C2: SemanticRelation PKs from classify_relations
    t2_calls_used: int  # C1/C2: running T2 budget counter
    total_tokens: int
    error: str | None


def _resolve_pack_and_source_type(source: Source, document: Document) -> tuple[DomainPack, str]:
    """Resolve the domain pack and v3 source-type profile name for a document.

    Resolution order:
    1. Match document URL (or source URL if document URL is null) against each
       profile's ``url_domains`` entries.  First matching profile wins.
    2. Else match document title (or source name) against each profile's
       ``title_regex`` entries (case-insensitive).  First matching profile wins.
    3. Else fall back to ``pack.metadata.supported_source_types[0]``.
    4. Else (empty list) fall back to ``"ai_news_article"`` (safety net).

    Profiles are iterated in pack declaration order; first match wins on both
    URL-domain and title-regex passes.
    """
    pack = load_pack(source.domain_pack)

    url = (document.url or source.url) or ""
    title = (document.title or source.name) or ""

    # Pass 1 — URL-domain matching (parse URL once, not per profile)
    parsed_url: SplitResult | None = None
    if url:
        parsed_url = urlsplit(url if "://" in url else "https://" + url)
        for profile_name, profile in pack.source_type_profiles.items():
            for domain_hint in profile.url_domains:
                if _url_matches_domain(parsed_url, domain_hint):
                    return pack, profile_name

    # Pass 2 — title regex matching against pre-compiled patterns.
    # Patterns prefixed with "(?-i)" opt out of IGNORECASE (handled at
    # compile time in SourceTypeProfile).
    if title:
        for profile_name, profile in pack.source_type_profiles.items():
            for pattern in profile.title_regex_compiled:
                if pattern.search(title):
                    return pack, profile_name

    # Pass 3 — pack default
    if pack.metadata.supported_source_types:
        return pack, pack.metadata.supported_source_types[0]

    # Pass 4 — absolute safety net
    return pack, "ai_news_article"


async def _extract_one_span(
    span: dict,
    client: Any,
    model: str,
    session_factory: async_sessionmaker,
    run_id: uuid.UUID,
    document_id: uuid.UUID,
    source_prefix: str,
) -> dict:
    """Extract semantic objects from one span with correction-prompt retry (max _MAX_RETRIES).

    Binds span_id in run_context for the duration so all log lines and the
    agent_runs row carry the correct span correlation.

    ``source_prefix`` is the pre-built static portion of the user prompt
    (pack id, telos, families, salience, facets, budget) shared across all
    spans of the same document — computed once in ``extract_spans``.
    """
    span_id = uuid.UUID(span["id"])
    metadata = dict(span.get("metadata_json") or {})
    metadata["segment_id"] = str(span_id)
    user = build_semantic_user_prompt(span["text"], metadata, source_prefix=source_prefix)
    total_tokens = 0
    attempts = 0

    async with span_scope(span_id):
        try:
            for attempt in range(_MAX_RETRIES + 1):
                attempts += 1
                try:
                    result, tokens = await client.complete_json(
                        model=model,
                        system=SEMANTIC_SYSTEM_PROMPT,
                        user=user,
                        response_model=SemanticExtractionOutput,
                    )
                    total_tokens += tokens
                    await record_span_extraction(
                        session_factory,
                        run_id=run_id,
                        span_id=span_id,
                        document_id=document_id,
                        status="success",
                        attempts=attempts,
                    )
                    return {
                        "span_id": span["id"],
                        "objects": [obj.model_dump() for obj in result.objects],
                        "tokens": total_tokens,
                        "error": None,
                    }
                except LLMNetworkError:
                    raise  # abort the entire graph
                except LLMSchemaError as exc:
                    if attempt < _MAX_RETRIES:
                        user = build_semantic_correction_prompt(user, exc.raw_output, str(exc))
                        continue
                    await record_span_extraction(
                        session_factory,
                        run_id=run_id,
                        span_id=span_id,
                        document_id=document_id,
                        status="schema_error",
                        attempts=attempts,
                        error=str(exc),
                    )
                    return {
                        "span_id": span["id"],
                        "objects": [],
                        "tokens": total_tokens,
                        "error": str(exc),
                    }
                except LLMError as exc:
                    await record_span_extraction(
                        session_factory,
                        run_id=run_id,
                        span_id=span_id,
                        document_id=document_id,
                        status="llm_error",
                        attempts=attempts,
                        error=str(exc),
                    )
                    return {
                        "span_id": span["id"],
                        "objects": [],
                        "tokens": total_tokens,
                        "error": str(exc),
                    }
        except asyncio.CancelledError:
            # This task is being cancelled mid-flight — sibling failure,
            # request abort, timeout, or shutdown. Shield the audit write so
            # the row reaches the DB before cancellation propagates, then
            # re-raise to preserve cancellation semantics.
            await asyncio.shield(
                record_span_extraction(
                    session_factory,
                    run_id=run_id,
                    span_id=span_id,
                    document_id=document_id,
                    status="cancelled",
                    attempts=attempts,
                    error="cancelled",
                )
            )
            raise
    raise AssertionError("unreachable: retry loop should have returned")


def make_extraction_graph(session_factory: async_sessionmaker, client: Any):  # noqa: C901
    """Build and compile the LangGraph extraction graph bound to session_factory and client.

    Cyclomatic complexity is C90-flagged because the factory defines five nested node
    functions; each is simple individually but the count aggregates in the outer scope.
    Keeping them nested preserves the closure over `session_factory` and `client`.
    """

    async def load_spans(state: ExtractionState) -> dict:
        async with session_factory() as session:
            doc = await session.get(Document, state["document_id"])
            if doc is None:
                return _load_spans_failure(f"Document {state['document_id']} not found")
            if doc.status != STATUS_EMBEDDED:
                return _load_spans_failure(f"Document status is '{doc.status}'; must be 'embedded'")

            # Load the source row to resolve pack + source-type profile
            source = (
                await session.execute(select(Source).where(Source.id == doc.source_id))
            ).scalar_one_or_none()
            if source is None:
                return _load_spans_failure(f"Source for document {state['document_id']} not found")

            try:
                pack, v3_source_type = _resolve_pack_and_source_type(source, doc)
            except (FileNotFoundError, ValidationError) as exc:
                return _load_spans_failure(
                    f"Failed to load domain pack '{source.domain_pack}': {exc}"
                )

            rows = (
                (
                    await session.execute(
                        select(Span)
                        .where(Span.document_id == state["document_id"])
                        .order_by(Span.span_index)
                    )
                )
                .scalars()
                .all()
            )
            spans = [
                {
                    "id": str(s.id),
                    "text": s.text,
                    "token_count": s.token_count,
                    "metadata_json": s.metadata_json,
                }
                for s in rows
            ]

        await mark_document_timestamp(
            session_factory, state["document_id"], "extraction_started_at"
        )
        return {
            "spans": spans,
            "pack": pack,
            "source_type": v3_source_type,
            "source_id": doc.source_id,
        }

    async def extract_spans(state: ExtractionState) -> dict:
        if state.get("error"):
            return {}

        run_id = state.get("run_id") or uuid.uuid4()
        semaphore = asyncio.Semaphore(5)
        # pack and source_type are guaranteed non-None here: load_spans sets error
        # and returns early if either cannot be resolved, and the conditional edge
        # routes to update_status (not here) when state["error"] is set.
        pack: DomainPack = state["pack"]  # type: ignore[assignment]
        source_type: str = state["source_type"]  # type: ignore[assignment]

        # Build the static prefix once for all spans of this document; avoids
        # O(spans × families) rebuild on every span call.
        source_prefix = build_semantic_source_prefix(pack, source_type)

        async def bounded(span: dict) -> dict:
            async with semaphore:
                return await _extract_one_span(
                    span,
                    client,
                    state["model"],
                    session_factory,
                    run_id=run_id,  # type: ignore[arg-type]
                    document_id=state["document_id"],
                    source_prefix=source_prefix,
                )

        # Default gather semantics: when one task raises LLMNetworkError,
        # asyncio cancels the siblings immediately. Each cancelled task hits
        # the CancelledError branch in _extract_one_span which shields its
        # audit write before re-raising.
        try:
            results: list[dict] = await asyncio.gather(*[bounded(s) for s in state["spans"]])
        except LLMNetworkError as exc:
            return {"error": str(exc), "results": []}

        total = sum(r.get("tokens", 0) for r in results)
        return {"run_id": run_id, "results": results, "total_tokens": total}

    async def validate_and_project(state: ExtractionState) -> dict:
        """Validate semantic objects against the pack, enforce budgets, and project.

        Drops objects that fail validate_object (logged at DEBUG). Spans with LLM errors
        are skipped. A span where every object is rejected is not counted as a span error.
        """
        if state.get("error"):
            return {}
        # pack and source_type are guaranteed non-None here (same guarantee as extract_spans).
        pack: DomainPack = state["pack"]  # type: ignore[assignment]
        source_type: str = state["source_type"]  # type: ignore[assignment]

        # Collect all accepted SemanticObject instances from successful spans
        accepted_objects: list[SemanticObject] = []
        for result in state.get("results", []):
            if result.get("error"):
                continue
            for obj_dict in result.get("objects", []):
                try:
                    obj = SemanticObject.model_validate(obj_dict)
                except (ValueError, ValidationError) as exc:
                    logger.debug("Skipping invalid object dict: %s", exc)
                    continue
                ok, reason = validate_object(obj, pack)
                if not ok:
                    logger.debug(
                        "Object rejected (span=%s, family=%s, type=%s): %s",
                        obj_dict.get("source_refs"),
                        obj_dict.get("domain_family"),
                        obj_dict.get("domain_object_type"),
                        reason,
                    )
                    continue
                accepted_objects.append(obj)

        # Apply source-level budgets
        budgeted_objects = enforce_budgets(accepted_objects, pack, source_type)

        # Project to ProjectedClaim form; span ids are inside ProjectedClaim.evidence_span_ids.
        # B2: keep the live SemanticObject parallel to each ProjectedClaim so store_claims
        # can build SemanticCapsule rows without re-parsing the _v0_7 stash.
        projected: list[ProjectedClaim] = []
        semantic_objects: list[SemanticObject] = []
        for obj in budgeted_objects:
            projected.append(project(obj))
            semantic_objects.append(obj)

        return {"projected_claims": projected, "semantic_objects": semantic_objects}

    async def store_claims(state: ExtractionState) -> dict:
        """Write Claim + ClaimEvidence + SemanticCapsule + CapsuleSegment in one transaction.

        B2 dual-write: every accepted SemanticObject lands as both a legacy Claim row
        and a SemanticCapsule row.  All four ORM types are added in a single session
        and committed atomically.  If the commit fails, both Claims and Capsules roll
        back — there is no partial state.

        Re-extraction safety: if a capsule with the same idempotency_key already exists
        (e.g. ?force=true re-extraction) the INSERT raises IntegrityError and the entire
        transaction is rolled back.  Idempotent upsert is B3's responsibility; B2 lets
        the failure propagate.
        """
        if state.get("error"):
            return {}

        projected_claims: list[ProjectedClaim] = state.get("projected_claims", [])
        semantic_objects: list[SemanticObject] = state.get("semantic_objects", [])

        if not projected_claims:
            return {"stored_claim_ids": [], "stored_capsule_ids": []}

        # Embed all capsule texts in one batch call to avoid repeated model init overhead.
        embedder = get_embedder()
        texts = [obj.text for obj in semantic_objects]
        embeddings: list[list[float]] = embedder.embed(texts) if texts else []

        # Resolve pack telos snapshot once for the whole batch.
        pack: DomainPack | None = state.get("pack")
        source_telos: str | None = None
        if pack is not None and pack.telos.primary_purposes:
            source_telos = pack.telos.primary_purposes[0]

        domain: str = pack.metadata.pack_id if pack is not None else ""
        document_id: uuid.UUID = state["document_id"]
        source_id: uuid.UUID | None = state.get("source_id")
        model_name: str | None = state.get("model")

        async with session_factory() as session:
            all_rows: list[Any] = []
            stored_ids: list[uuid.UUID] = []
            capsule_ids: list[uuid.UUID] = []

            for idx, (projected, obj) in enumerate(
                zip(projected_claims, semantic_objects, strict=True)
            ):
                claim_id = uuid.uuid4()
                capsule_id = uuid.uuid4()

                # --- legacy Claim + ClaimEvidence ---
                all_rows.append(
                    Claim(
                        id=claim_id,
                        document_id=document_id,
                        claim_text=projected.claim_text,
                        claim_type=projected.claim_type,
                        entities_json=projected.entities_json,
                        topics_json=projected.topics_json,
                        confidence=projected.confidence,
                        status="active",
                    )
                )
                for ev_span in projected.evidence_span_ids:
                    all_rows.append(
                        ClaimEvidence(
                            claim_id=claim_id,
                            span_id=uuid.UUID(ev_span),
                            evidence_role="support",
                            confidence=projected.confidence,
                        )
                    )

                # --- SemanticCapsule + CapsuleSegment (shared assembly) ---
                capsule, segments = build_capsule_row(
                    capsule_id=capsule_id,
                    source_id=source_id,
                    document_id=document_id,
                    claim_id=claim_id,
                    obj=obj,
                    domain=domain,
                    source_telos=source_telos,
                    embedding=embeddings[idx],
                    created_by_tier="t2",
                    created_by_model=model_name,
                )
                all_rows.append(capsule)
                all_rows.extend(segments)

                stored_ids.append(claim_id)
                capsule_ids.append(capsule_id)

            session.add_all(all_rows)
            await session.commit()

        return {"stored_claim_ids": stored_ids, "stored_capsule_ids": capsule_ids}

    async def judge_capsules(state: ExtractionState) -> dict:
        """Run the T2 evidence-sufficiency judge on flagged capsules (C1).

        Gated by:
        - state["stored_capsule_ids"] non-empty
        - remaining T2 budget > 0
        - capsule.escalation_state == "flagged"

        Writes one SemanticRelation row per judged capsule (target_capsule_id=None;
        unary quality annotation). Updates capsule.escalation_state to
        "escalated" or "reviewed".
        """
        if state.get("error") or not state.get("stored_capsule_ids"):
            return {}

        pack: DomainPack = state["pack"]  # type: ignore[assignment]
        t2_calls_used: int = state.get("t2_calls_used", 0)
        remaining_budget = pack.budgets.max_t2_calls_per_source - t2_calls_used
        if remaining_budget <= 0:
            return {}

        t2_model = _resolve_t2_model(pack, state["model"])
        capsule_ids = state["stored_capsule_ids"]

        async with session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(SemanticCapsule).where(SemanticCapsule.id.in_(capsule_ids))
                    )
                )
                .scalars()
                .all()
            )

        flagged = [c for c in rows if c.escalation_state == "flagged"]
        to_judge = flagged[:remaining_budget]

        judge_results: list[dict] = []
        calls_made = 0

        for capsule in to_judge:
            obj = _capsule_to_obj_for_judge(capsule)
            try:
                verdict, _ = await client.complete_json(
                    model=t2_model,
                    system=JUDGE_SYSTEM_PROMPT,
                    user=build_judge_prompt(obj, pack),
                    response_model=JudgeVerdict,
                    run_type="judge_capsule",
                )
            except LLMError as exc:
                logger.warning("Judge failed for capsule %s: %s", capsule.id, exc)
                continue

            calls_made += 1
            relation_id = uuid.uuid4()
            relation_type = "judge_escalated" if verdict.escalate else "judge_cleared"
            new_escalation = "escalated" if verdict.escalate else "reviewed"

            async with session_factory() as session:
                session.add(
                    SemanticRelation(
                        id=relation_id,
                        source_capsule_id=capsule.id,
                        target_capsule_id=None,
                        target_thesis_id=None,
                        relation_type=relation_type,
                        domain_relation_type=None,
                        polarity=None,
                        strength=verdict.recommended_confidence,
                        confidence=verdict.recommended_confidence,
                        evidence_capsule_ids=[],
                        rationale=verdict.rationale,
                        epistemic_state=verdict.model_dump(),
                        created_by_tier="t2",
                        created_by_model=t2_model,
                    )
                )
                cap_row = await session.get(SemanticCapsule, capsule.id)
                if cap_row:
                    cap_row.escalation_state = new_escalation
                await session.commit()

            judge_results.append(
                {
                    "capsule_id": str(capsule.id),
                    "verdict": verdict.model_dump(),
                    "relation_id": str(relation_id),
                }
            )

        return {"judge_results": judge_results, "t2_calls_used": t2_calls_used + calls_made}

    async def classify_relations(state: ExtractionState) -> dict:
        """Classify semantic relations between same-family capsule pairs (C2).

        For each group of capsules sharing the same object_family, generates
        unordered pairs (A, B) with A.id < B.id and calls the T2 classifier.
        Pairs are capped by the remaining T2 budget after judge_capsules.
        Writes one SemanticRelation row per non-"none" classification.
        """
        capsule_ids = state.get("stored_capsule_ids", [])
        if state.get("error") or len(capsule_ids) < 2:
            return {}

        pack: DomainPack = state["pack"]  # type: ignore[assignment]
        t2_calls_used: int = state.get("t2_calls_used", 0)
        remaining_budget = pack.budgets.max_t2_calls_per_source - t2_calls_used
        if remaining_budget <= 0:
            return {}

        t2_model = _resolve_t2_model(pack, state["model"])

        async with session_factory() as session:
            caps = (
                (
                    await session.execute(
                        select(SemanticCapsule).where(SemanticCapsule.id.in_(capsule_ids))
                    )
                )
                .scalars()
                .all()
            )

        from collections import defaultdict

        by_family: dict[str, list] = defaultdict(list)
        for cap in caps:
            by_family[cap.object_family].append(cap)

        pairs = []
        for fam_caps in by_family.values():
            sorted_caps = sorted(fam_caps, key=lambda c: c.id)
            for i, cap_a in enumerate(sorted_caps):
                for cap_b in sorted_caps[i + 1 :]:
                    pairs.append((cap_a, cap_b))

        pairs = pairs[:remaining_budget]

        domain_relations_set = set(pack.relation_grammar.domain_relations)
        relation_ids: list[uuid.UUID] = []

        for cap_a, cap_b in pairs:
            try:
                classification, _ = await client.complete_json(
                    model=t2_model,
                    system=CLASSIFY_SYSTEM_PROMPT,
                    user=build_relation_prompt(cap_a, cap_b, pack),
                    response_model=RelationClassification,
                    run_type="classify_relation",
                )
            except LLMError as exc:
                logger.warning(
                    "Relation classification failed (%s → %s): %s",
                    cap_a.id,
                    cap_b.id,
                    exc,
                )
                continue

            if not classification.relation_type or classification.relation_type == "none":
                continue

            relation_id = uuid.uuid4()
            domain_relation_type = (
                classification.relation_type
                if classification.relation_type in domain_relations_set
                else None
            )

            async with session_factory() as session:
                session.add(
                    SemanticRelation(
                        id=relation_id,
                        source_capsule_id=cap_a.id,
                        target_capsule_id=cap_b.id,
                        target_thesis_id=None,
                        relation_type=classification.relation_type,
                        domain_relation_type=domain_relation_type,
                        polarity=classification.polarity,
                        strength=classification.strength,
                        confidence=classification.strength,
                        evidence_capsule_ids=[],
                        rationale=classification.rationale,
                        epistemic_state={},
                        created_by_tier="t2",
                        created_by_model=t2_model,
                    )
                )
                await session.commit()

            relation_ids.append(relation_id)

        return {"relation_ids": relation_ids}

    async def update_status(state: ExtractionState) -> dict:
        if state.get("error"):
            new_status = STATUS_EXTRACTION_FAILED
        else:
            results = state.get("results", [])
            # Empty results with no error = document had zero extractable spans;
            # this is a successful no-op extraction, not a failure.
            if not results:
                new_status = STATUS_CLAIMS_EXTRACTED
            else:
                failed = sum(1 for r in results if r.get("error"))
                if failed == 0:
                    new_status = STATUS_CLAIMS_EXTRACTED
                elif failed < len(results):
                    new_status = STATUS_EXTRACTION_PARTIAL
                else:
                    new_status = STATUS_EXTRACTION_FAILED

        async with session_factory() as session:
            doc = await session.get(Document, state["document_id"])
            if doc:
                doc.status = new_status
                await session.commit()

        await mark_document_timestamp(
            session_factory, state["document_id"], "extraction_completed_at"
        )
        return {}

    def _route_after_extract(state: ExtractionState) -> str:
        return "update_status" if state.get("error") else "validate_and_project"

    builder = StateGraph(ExtractionState)
    builder.add_node("load_spans", load_spans)
    builder.add_node("extract_spans", extract_spans)
    builder.add_node("validate_and_project", validate_and_project)
    builder.add_node("store_claims", store_claims)
    builder.add_node("judge_capsules", judge_capsules)
    builder.add_node("classify_relations", classify_relations)
    builder.add_node("update_status", update_status)

    builder.set_entry_point("load_spans")
    builder.add_edge("load_spans", "extract_spans")
    builder.add_conditional_edges(
        "extract_spans",
        _route_after_extract,
        {"validate_and_project": "validate_and_project", "update_status": "update_status"},
    )
    builder.add_edge("validate_and_project", "store_claims")
    builder.add_edge("store_claims", "judge_capsules")
    builder.add_edge("judge_capsules", "classify_relations")
    builder.add_edge("classify_relations", "update_status")
    builder.add_edge("update_status", END)

    return builder.compile()


async def run_with_context(graph, document_id: uuid.UUID, model: str) -> dict:
    """Enter extraction_run context, invoke the graph, return final state with run_id."""
    async with extraction_run(document_id) as run_id:
        final = await graph.ainvoke(
            {
                "document_id": document_id,
                "run_id": run_id,
                "model": model,
                "pack": None,
                "source_type": None,
                "source_id": None,
                "spans": [],
                "results": [],
                "projected_claims": [],
                "semantic_objects": [],
                "stored_claim_ids": [],
                "stored_capsule_ids": [],
                "judge_results": [],
                "relation_ids": [],
                "t2_calls_used": 0,
                "total_tokens": 0,
                "error": None,
            }
        )
    final["run_id"] = run_id
    return final
