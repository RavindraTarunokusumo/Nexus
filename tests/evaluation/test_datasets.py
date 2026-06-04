# tests/evaluation/test_datasets.py
"""Unit tests for gold-set dataset loading (v0.7 semantic-object path)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.evaluation.datasets import (
    GoldSemanticObject,
    SemanticObjectExtractionExample,
    SpanRetrievalExample,
    load_dataset,
)


def _write_yaml(tmp_path: Path, data: dict, filename: str = "test.yaml") -> Path:
    p = tmp_path / filename
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


def _minimal_gold_object(text: str = "x", **overrides) -> dict:
    base = {
        "text": text,
        "core_type": "event",
        "domain_family": "model_system",
        "domain_object_type": "model_release",
        "mvp_claim_type": "model_release",
    }
    base.update(overrides)
    return base


class TestGoldSemanticObject:
    def test_minimal(self):
        o = GoldSemanticObject(**_minimal_gold_object("OpenAI released GPT-5"))
        assert o.text == "OpenAI released GPT-5"
        assert o.core_type == "event"
        assert o.mvp_claim_type == "model_release"
        assert o.salience == 0.5  # default

    def test_with_facets_and_epistemic(self):
        o = GoldSemanticObject(
            **_minimal_gold_object(
                facets={"orgs": ["X"]},
                epistemic={"status": "asserted_by_source"},
                salience=0.9,
            )
        )
        assert o.facets == {"orgs": ["X"]}
        assert o.epistemic["status"] == "asserted_by_source"
        assert o.salience == 0.9


class TestSemanticObjectExtractionExample:
    def test_with_document_text(self):
        ex = SemanticObjectExtractionExample(
            example_id="ex1",
            document_text="Some text about AI.",
            gold_objects=[GoldSemanticObject(**_minimal_gold_object())],
        )
        assert ex.example_id == "ex1"
        assert len(ex.gold_objects) == 1

    def test_document_id_optional(self):
        ex = SemanticObjectExtractionExample(example_id="ex2", gold_objects=[])
        assert ex.document_text is None
        assert ex.document_id is None


class TestSpanRetrievalExample:
    def test_minimal(self):
        ex = SpanRetrievalExample(
            example_id="q1",
            query="What did Anthropic release?",
            gold_span_texts=["Anthropic released Claude 4"],
        )
        assert ex.example_id == "q1"
        assert ex.negative_span_texts == []


class TestLoadDataset:
    def test_load_semantic_object_extraction(self, tmp_path):
        data = {
            "name": "test_ds",
            "task": "semantic_object_extraction",
            "version": 1,
            "examples": [
                {
                    "example_id": "ex1",
                    "document_text": "Anthropic released Claude 4.",
                    "gold_objects": [
                        _minimal_gold_object("Anthropic released Claude 4"),
                    ],
                }
            ],
        }
        p = _write_yaml(tmp_path, data)
        ds = load_dataset(p)
        assert ds.name == "test_ds"
        assert ds.task == "semantic_object_extraction"
        assert ds.version == 1
        assert len(ds.examples) == 1
        assert isinstance(ds.examples[0], SemanticObjectExtractionExample)
        assert ds.examples[0].gold_objects[0].mvp_claim_type == "model_release"

    def test_load_span_retrieval(self, tmp_path):
        data = {
            "name": "queries_v1",
            "task": "span_retrieval",
            "version": 1,
            "examples": [
                {
                    "example_id": "q1",
                    "query": "What did Anthropic release?",
                    "gold_span_texts": ["Anthropic released Claude 4"],
                }
            ],
        }
        p = _write_yaml(tmp_path, data)
        ds = load_dataset(p)
        assert ds.task == "span_retrieval"
        assert isinstance(ds.examples[0], SpanRetrievalExample)

    def test_checksum_is_sha256_hex(self, tmp_path):
        data = {
            "name": "ds",
            "task": "semantic_object_extraction",
            "version": 1,
            "examples": [],
        }
        p = _write_yaml(tmp_path, data)
        ds = load_dataset(p)
        assert len(ds.checksum) == 64
        assert all(c in "0123456789abcdef" for c in ds.checksum)

    def test_unknown_task_raises(self, tmp_path):
        data = {
            "name": "ds",
            "task": "unknown_task",
            "version": 1,
            "examples": [],
        }
        p = _write_yaml(tmp_path, data)
        with pytest.raises(ValueError, match="unknown_task"):
            load_dataset(p)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_dataset(tmp_path / "nonexistent.yaml")

    def test_loads_ai_tech_v3_gold_set(self):
        """End-to-end smoke: the committed v3 gold set parses and covers ≥4 mvp_claim_types."""
        path = (
            Path(__file__).resolve().parents[2]
            / "evals"
            / "gold"
            / "semantic_objects"
            / "ai_tech_v3.yaml"
        )
        ds = load_dataset(path)
        assert ds.name == "ai_tech_v3"
        assert ds.version == 3
        assert len(ds.examples) >= 5
        claim_types = {
            o.mvp_claim_type
            for ex in ds.examples
            if isinstance(ex, SemanticObjectExtractionExample)
            for o in ex.gold_objects
        }
        assert len(claim_types) >= 4, f"Expected ≥4 mvp_claim_types, got: {claim_types}"
