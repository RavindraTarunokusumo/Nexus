"""Typed loader for v3 (telos-based) domain packs."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

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


@functools.lru_cache(maxsize=None)
def load_pack(pack_id: str) -> DomainPack:
    """Load and validate a v3 domain pack from ``{pack_dir}/{pack_id}.yaml``.

    Raises:
        FileNotFoundError: if the YAML file does not exist.
        pydantic.ValidationError: if the YAML fails schema validation.
    """
    pack_path = _pack_dir() / f"{pack_id}.yaml"
    if not pack_path.exists():
        raise FileNotFoundError(f"Domain pack '{pack_id}' not found at '{pack_path}'")
    data = yaml.safe_load(pack_path.read_text(encoding="utf-8"))
    return DomainPack.model_validate(data)


def clear_cache() -> None:
    """Invalidate the load_pack LRU cache (primarily for tests)."""
    load_pack.cache_clear()
