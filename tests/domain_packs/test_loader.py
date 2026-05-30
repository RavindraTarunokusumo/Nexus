"""Tests for app.domain_packs.loader (v3 telos-based domain pack loader)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

import app.domain_packs.loader as loader_module
from app.domain_packs.loader import (
    DomainPack,
    clear_cache,
    load_pack,
)

# ---------------------------------------------------------------------------
# Minimal valid pack fixture — covers required fields only; everything else
# exercises default values.
# ---------------------------------------------------------------------------

_MINIMAL_PACK: dict = {
    "metadata": {
        "pack_id": "test_pack",
        "domain": "testing",
        "version": "0.1.0",
        "supported_source_types": ["article"],
    },
    "telos": {
        "primary_purposes": ["extract test claims"],
    },
    "semantic_object_families": {
        "findings": {
            "purpose": "capture key findings",
            "object_types": ["finding", "result"],
            "core_type_mapping": {
                "finding": "observation",
                "result": "result",
            },
            "mvp_claim_type": {
                "finding": "research_finding",
                "result": "benchmark_result",
            },
        }
    },
    "relation_grammar": {
        "core_relations": ["supports", "contradicts"],
    },
    "model_routing_policy": {
        "default_route": {
            "segmenting": "T0",
            "basic_facets": "T1",
            "semantic_compression_easy": "T1",
            "semantic_compression_ambiguous": "T2",
            "relation_classification_easy": "T2",
            "synthesis": "T3",
            "audit_or_high_impact": "T4",
        }
    },
}


def _write_pack(tmp_path: Path, data: dict, pack_id: str = "test_pack") -> None:
    (tmp_path / f"{pack_id}.yaml").write_text(yaml.dump(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Autouse fixture: clear cache before and after each test to prevent leakage
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_loader_cache():
    clear_cache()
    yield
    clear_cache()


# ---------------------------------------------------------------------------
# 1. Valid load against a minimal in-tree fixture
# ---------------------------------------------------------------------------


class TestLoadValidPack:
    def test_required_fields_parse(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_pack(tmp_path, _MINIMAL_PACK)
        monkeypatch.setattr(loader_module, "_pack_dir", lambda: tmp_path)

        pack = load_pack("test_pack")

        assert isinstance(pack, DomainPack)
        assert pack.metadata.pack_id == "test_pack"
        assert pack.metadata.domain == "testing"
        assert pack.telos.primary_purposes == ["extract test claims"]

    def test_defaults_applied(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_pack(tmp_path, _MINIMAL_PACK)
        monkeypatch.setattr(loader_module, "_pack_dir", lambda: tmp_path)

        pack = load_pack("test_pack")

        # Telos optional fields
        assert pack.telos.secondary_purposes == []
        assert pack.telos.anti_purposes == []
        assert pack.telos.reader_goals == []
        assert pack.telos.producer_incentives == []

        # Metadata defaults
        assert pack.metadata.default_language == "en"
        assert pack.metadata.owner is None
        assert pack.metadata.model_policy_version is None

        # Budgets defaults
        assert pack.budgets.max_segments_per_source == 500
        assert pack.budgets.max_semantic_objects_per_source == 80
        assert pack.budgets.max_semantic_objects_per_segment == 5
        assert pack.budgets.max_facets_per_object == 24
        assert pack.budgets.max_t2_calls_per_source == 20
        assert pack.budgets.force_escalation_if_budget_exceeded is False

        # FacetPolicy defaults
        assert pack.facet_policy.generic_facets == ["people", "orgs", "places", "dates"]
        assert pack.facet_policy.preserve_unknown_salient_terms is True

        # Source type profiles defaults to empty
        assert pack.source_type_profiles == {}

        # SaliencePolicy defaults to empty lists
        assert pack.salience_policy.preserve_if == []

    def test_semantic_family_mvp_claim_type(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_pack(tmp_path, _MINIMAL_PACK)
        monkeypatch.setattr(loader_module, "_pack_dir", lambda: tmp_path)

        pack = load_pack("test_pack")

        family = pack.semantic_object_families["findings"]
        assert family.mvp_claim_type["finding"] == "research_finding"
        assert family.mvp_claim_type["result"] == "benchmark_result"

    def test_extra_top_level_keys_allowed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import copy

        pack_with_legacy = copy.deepcopy(_MINIMAL_PACK)
        pack_with_legacy["topics"] = ["ai", "llm"]
        pack_with_legacy["claim_types"] = ["model_release"]
        _write_pack(tmp_path, pack_with_legacy)
        monkeypatch.setattr(loader_module, "_pack_dir", lambda: tmp_path)

        # Must not raise — top-level extra="allow"
        pack = load_pack("test_pack")
        assert pack.metadata.pack_id == "test_pack"


# ---------------------------------------------------------------------------
# 2. Existing personal_ai_tech.yaml fails validation (xfail — rewritten in A2)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason="personal_ai_tech.yaml is rewritten to v3 in A2",
    strict=True,
)
def test_personal_ai_tech_yaml_loads_as_v3() -> None:
    """The legacy YAML lacks telos/semantic_object_families/relation_grammar/
    model_routing_policy — it will raise ValidationError until A2 rewrites it."""
    load_pack("personal_ai_tech")


# ---------------------------------------------------------------------------
# 3. Missing pack raises FileNotFoundError
# ---------------------------------------------------------------------------


class TestMissingPackRaisesFileNotFoundError:
    def test_raises_file_not_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(loader_module, "_pack_dir", lambda: tmp_path)

        with pytest.raises(FileNotFoundError, match="nonexistent_pack"):
            load_pack("nonexistent_pack")


# ---------------------------------------------------------------------------
# 4. Schema-invalid pack raises pydantic.ValidationError
# ---------------------------------------------------------------------------


class TestInvalidPackRaisesValidationError:
    def test_missing_required_field_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import copy

        bad_pack = copy.deepcopy(_MINIMAL_PACK)
        # Remove pack_id from metadata — required field
        del bad_pack["metadata"]["pack_id"]
        _write_pack(tmp_path, bad_pack)
        monkeypatch.setattr(loader_module, "_pack_dir", lambda: tmp_path)

        with pytest.raises(ValidationError):
            load_pack("test_pack")

    def test_missing_telos_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import copy

        bad_pack = copy.deepcopy(_MINIMAL_PACK)
        del bad_pack["telos"]
        _write_pack(tmp_path, bad_pack)
        monkeypatch.setattr(loader_module, "_pack_dir", lambda: tmp_path)

        with pytest.raises(ValidationError):
            load_pack("test_pack")


# ---------------------------------------------------------------------------
# 5. Cache hit — two calls return the same object identity
# ---------------------------------------------------------------------------


class TestCacheHit:
    def test_same_object_identity(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_pack(tmp_path, _MINIMAL_PACK)
        monkeypatch.setattr(loader_module, "_pack_dir", lambda: tmp_path)

        pack1 = load_pack("test_pack")
        pack2 = load_pack("test_pack")

        assert pack1 is pack2

    def test_clear_cache_forces_reload(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import copy

        _write_pack(tmp_path, _MINIMAL_PACK)
        monkeypatch.setattr(loader_module, "_pack_dir", lambda: tmp_path)

        pack1 = load_pack("test_pack")
        clear_cache()

        updated = copy.deepcopy(_MINIMAL_PACK)
        updated["telos"]["primary_purposes"] = ["updated purpose"]
        _write_pack(tmp_path, updated)

        pack2 = load_pack("test_pack")

        assert pack1 is not pack2
        assert pack2.telos.primary_purposes == ["updated purpose"]
