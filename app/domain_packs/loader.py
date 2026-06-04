"""Typed loader for v3 (telos-based) domain packs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# Pydantic v2 models — v3 minimal MVP subset
# ---------------------------------------------------------------------------


class Metadata(BaseModel):
    pack_id: str
    domain: str
    version: str
    description: str | None = None
    supported_source_types: list[str]
    default_language: str = "en"
    model_policy_version: str | None = None
    owner: str | None = None


class Telos(BaseModel):
    primary_purposes: list[str]
    secondary_purposes: list[str] = Field(default_factory=list)
    anti_purposes: list[str] = Field(default_factory=list)
    reader_goals: list[str] = Field(default_factory=list)
    producer_incentives: list[str] = Field(default_factory=list)


class SourceTypeProfile(BaseModel):
    structural_features: list[str] = Field(default_factory=list)
    high_value_sections: list[str] = Field(default_factory=list)
    low_value_sections: list[str] = Field(default_factory=list)
    expected_semantic_families: list[str] = Field(default_factory=list)
    default_processing_mode: Literal["cheap", "balanced", "deep"] = "balanced"
    telos_override: dict[str, Any] | None = None
    url_domains: list[str] = Field(default_factory=list)
    title_regex: list[str] = Field(default_factory=list)
    # Derived: compiled forms of title_regex. Built once on pack load so the
    # classifier never recompiles per document. Patterns are IGNORECASE by
    # default; embed "(?-i)" at the start to opt out and assert literal case.
    title_regex_compiled: list[re.Pattern] = Field(default_factory=list, exclude=True)

    @model_validator(mode="after")
    def _compile_title_regex(self) -> "SourceTypeProfile":
        compiled: list[re.Pattern] = []
        for pattern in self.title_regex:
            # "(?-i)" at the start opts out of IGNORECASE (legacy syntax;
            # Python's re doesn't accept a bare scope-less "(?-i)" so we
            # strip the prefix and compile without IGNORECASE).
            if pattern.startswith("(?-i)"):
                compiled.append(re.compile(pattern[5:]))
            else:
                compiled.append(re.compile(pattern, re.IGNORECASE))
        object.__setattr__(self, "title_regex_compiled", compiled)
        return self


class SemanticObjectFamily(BaseModel):
    purpose: str
    object_types: list[str]
    core_type_mapping: dict[str, str]
    mvp_claim_type: dict[str, str]
    required_fields: list[str] = Field(default_factory=list)
    optional_fields: list[str] = Field(default_factory=list)


class SaliencePolicy(BaseModel):
    min_floor: float = Field(default=0.3, ge=0.0, le=1.0)
    preserve_if: list[str] = Field(default_factory=list)
    ignore_if: list[str] = Field(default_factory=list)
    downgrade_if: list[str] = Field(default_factory=list)
    escalate_if: list[str] = Field(default_factory=list)


class FacetPolicy(BaseModel):
    generic_facets: list[str] = Field(default_factory=lambda: ["people", "orgs", "places", "dates"])
    domain_facets: list[str] = Field(default_factory=list)
    preserve_unknown_salient_terms: bool = True
    canonicalization_required: bool = False
    external_id_sources: list[str] = Field(default_factory=list)


class RelationGrammar(BaseModel):
    core_relations: list[str]
    domain_relations: list[str] = Field(default_factory=list)
    relation_constraints: dict[str, Any] = Field(default_factory=dict)
    escalation_rules: list[str] = Field(default_factory=list)


class EpistemicPolicy(BaseModel):
    source_authority_rules: dict[str, Any] = Field(default_factory=dict)
    status_rules: dict[str, Any] = Field(default_factory=dict)
    confidence_rules: dict[str, Any] = Field(default_factory=dict)
    contradiction_policy: dict[str, Any] = Field(default_factory=dict)
    uncertainty_policy: dict[str, Any] = Field(default_factory=dict)
    escalation_policy: dict[str, Any] = Field(default_factory=dict)


class ModelRoutingPolicy(BaseModel):
    default_route: dict[str, str]
    models: dict[str, Any] = Field(default_factory=dict)


class Budgets(BaseModel):
    max_segments_per_source: int = 500
    max_semantic_objects_per_source: int = 80
    max_semantic_objects_per_segment: int = 5
    max_relations_per_object: int = 8
    max_facets_per_object: int = 24
    max_t2_calls_per_source: int = 20
    max_t3_calls_per_source: int = 2
    force_escalation_if_budget_exceeded: bool = False
    per_source_type: dict[str, dict[str, Any]] = Field(default_factory=dict)


class RetentionPolicy(BaseModel):
    hot_window_hours: int = 168
    warm_window_days: int = 30
    cold_after_days: int = 180
    archive_after_days: int | None = None
    decay_by_object_type: dict[str, Any] = Field(default_factory=dict)
    refresh_triggers: list[str] = Field(default_factory=list)
    stale_conditions: list[str] = Field(default_factory=list)
    supersession_rules: list[str] = Field(default_factory=list)


class RetrievalPolicy(BaseModel):
    query_intents: dict[str, Any] = Field(default_factory=dict)
    hybrid_score_weights: dict[str, float] = Field(default_factory=dict)
    retrieval_priorities: dict[str, list[str]] = Field(default_factory=dict)


class ContextAssembly(BaseModel):
    include: list[str] = Field(default_factory=list)
    ordering: str = "evidence_strength"
    max_tokens_by_tier: dict[str, int] = Field(default_factory=dict)


class EvaluationContract(BaseModel):
    object_extraction_metrics: list[str] = Field(default_factory=list)
    relation_metrics: list[str] = Field(default_factory=list)
    epistemic_metrics: list[str] = Field(default_factory=list)
    retrieval_metrics: list[str] = Field(default_factory=list)
    minimum_thresholds: dict[str, str] = Field(default_factory=dict)


class DomainPack(BaseModel):
    """A v3 telos-based purpose-grammar domain pack (loaded from YAML)."""

    model_config = ConfigDict(extra="allow")

    metadata: Metadata
    telos: Telos
    source_type_profiles: dict[str, SourceTypeProfile] = Field(default_factory=dict)
    semantic_object_families: dict[str, SemanticObjectFamily]
    salience_policy: SaliencePolicy = Field(default_factory=SaliencePolicy)
    facet_policy: FacetPolicy = Field(default_factory=FacetPolicy)
    relation_grammar: RelationGrammar
    epistemic_policy: EpistemicPolicy = Field(default_factory=EpistemicPolicy)
    model_routing_policy: ModelRoutingPolicy
    budgets: Budgets = Field(default_factory=Budgets)
    retention_policy: RetentionPolicy = Field(default_factory=RetentionPolicy)
    retrieval_policy: RetrievalPolicy = Field(default_factory=RetrievalPolicy)
    context_assembly: ContextAssembly = Field(default_factory=ContextAssembly)
    evaluation_contract: EvaluationContract = Field(default_factory=EvaluationContract)


# ---------------------------------------------------------------------------
# Pack directory indirection (test-patchable via monkeypatch)
# ---------------------------------------------------------------------------


def _pack_dir() -> Path:
    """Return the directory that contains pack YAML files."""
    return Path(__file__).parent


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


# Mtime-keyed cache: maps pack_id -> (file_mtime, parsed_pack). On every
# load_pack call we stat the file and reload if the mtime changed, so an
# operator editing a pack YAML at runtime sees the new pack on the next call.
_CACHE: dict[str, tuple[float, DomainPack]] = {}


def load_pack(pack_id: str) -> DomainPack:
    """Load and validate a v3 domain pack from ``{pack_dir}/{pack_id}.yaml``.

    The result is cached per pack_id and invalidated automatically when the
    underlying YAML's mtime changes; call ``clear_cache()`` to drop all
    entries explicitly.

    Raises:
        FileNotFoundError: if the YAML file does not exist or the resolved path
            escapes the pack directory (path-traversal guard).
        pydantic.ValidationError: if the YAML fails schema validation.
    """
    pack_dir = _pack_dir().resolve()
    pack_path = (pack_dir / f"{pack_id}.yaml").resolve()
    if not pack_path.is_relative_to(pack_dir) or not pack_path.is_file():
        raise FileNotFoundError(f"Domain pack {pack_id!r} not found")

    mtime = pack_path.stat().st_mtime
    cached = _CACHE.get(pack_id)
    if cached is not None and cached[0] == mtime:
        return cached[1]

    data = yaml.safe_load(pack_path.read_text(encoding="utf-8"))
    pack = DomainPack.model_validate(data)
    _CACHE[pack_id] = (mtime, pack)
    return pack


def clear_cache() -> None:
    """Drop every cached pack (primarily for tests)."""
    _CACHE.clear()
