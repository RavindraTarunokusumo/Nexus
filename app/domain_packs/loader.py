"""Typed loader for v3 (telos-based) domain packs."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Literal

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
    secondary_purposes: list[str] = []
    anti_purposes: list[str] = []
    reader_goals: list[str] = []
    producer_incentives: list[str] = []


class SourceTypeProfile(BaseModel):
    structural_features: list[str] = []
    high_value_sections: list[str] = []
    low_value_sections: list[str] = []
    expected_semantic_families: list[str] = []
    default_processing_mode: Literal["cheap", "balanced", "deep"] = "balanced"
    telos_override: dict | None = None  # type: ignore[type-arg]


class SemanticObjectFamily(BaseModel):
    purpose: str
    object_types: list[str]
    core_type_mapping: dict[str, str]
    mvp_claim_type: dict[str, str]
    required_fields: list[str] = []
    optional_fields: list[str] = []


class SaliencePolicy(BaseModel):
    preserve_if: list[str] = []
    ignore_if: list[str] = []
    downgrade_if: list[str] = []
    escalate_if: list[str] = []


class FacetPolicy(BaseModel):
    generic_facets: list[str] = ["people", "orgs", "places", "dates"]
    domain_facets: list[str] = []
    preserve_unknown_salient_terms: bool = True
    canonicalization_required: bool = False
    external_id_sources: list[str] = []


class RelationGrammar(BaseModel):
    core_relations: list[str]
    domain_relations: list[str] = []
    relation_constraints: dict = {}  # type: ignore[type-arg]
    escalation_rules: list[str] = []


class EpistemicPolicy(BaseModel):
    source_authority_rules: dict = {}  # type: ignore[type-arg]
    status_rules: dict = {}  # type: ignore[type-arg]
    confidence_rules: dict = {}  # type: ignore[type-arg]
    contradiction_policy: dict = {}  # type: ignore[type-arg]
    uncertainty_policy: dict = {}  # type: ignore[type-arg]
    escalation_policy: dict = {}  # type: ignore[type-arg]


class ModelRoutingPolicy(BaseModel):
    default_route: dict[str, str]
    models: dict = {}  # type: ignore[type-arg]


class Budgets(BaseModel):
    max_segments_per_source: int = 500
    max_semantic_objects_per_source: int = 80
    max_semantic_objects_per_segment: int = 5
    max_relations_per_object: int = 8
    max_facets_per_object: int = 24
    max_t2_calls_per_source: int = 20
    max_t3_calls_per_source: int = 2
    force_escalation_if_budget_exceeded: bool = False
    per_source_type: dict[str, dict] = Field(default_factory=dict)  # type: ignore[type-arg]


class RetentionPolicy(BaseModel):
    hot_window_hours: int = 168
    warm_window_days: int = 30
    cold_after_days: int = 180
    archive_after_days: int | None = None
    decay_by_object_type: dict = {}  # type: ignore[type-arg]
    refresh_triggers: list[str] = []
    stale_conditions: list[str] = []
    supersession_rules: list[str] = []


class RetrievalPolicy(BaseModel):
    query_intents: dict = {}  # type: ignore[type-arg]
    hybrid_score_weights: dict[str, float] = {}
    retrieval_priorities: dict[str, list[str]] = {}


class ContextAssembly(BaseModel):
    include: list[str] = []
    ordering: str = "evidence_strength"
    max_tokens_by_tier: dict[str, int] = {}


class EvaluationContract(BaseModel):
    object_extraction_metrics: list[str] = []
    relation_metrics: list[str] = []
    epistemic_metrics: list[str] = []
    retrieval_metrics: list[str] = []
    minimum_thresholds: dict[str, str] = {}


class DomainPack(BaseModel):
    model_config = ConfigDict(extra="allow")

    metadata: Metadata
    telos: Telos
    source_type_profiles: dict[str, SourceTypeProfile] = {}
    semantic_object_families: dict[str, SemanticObjectFamily]
    salience_policy: SaliencePolicy = SaliencePolicy()
    facet_policy: FacetPolicy = FacetPolicy()
    relation_grammar: RelationGrammar
    epistemic_policy: EpistemicPolicy = EpistemicPolicy()
    model_routing_policy: ModelRoutingPolicy
    budgets: Budgets = Budgets()
    retention_policy: RetentionPolicy = RetentionPolicy()
    retrieval_policy: RetrievalPolicy = RetrievalPolicy()
    context_assembly: ContextAssembly = ContextAssembly()
    evaluation_contract: EvaluationContract = EvaluationContract()


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
