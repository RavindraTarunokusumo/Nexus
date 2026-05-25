# tests/evaluation/test_datasets.py
"""Unit tests for gold-set dataset loading."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.evaluation.datasets import (
    ClaimExtractionExample,
    GoldClaim,
    SpanRetrievalExample,
    load_dataset,
)

# ── helpers ──────────────────────────────────────────────────────────────────


def _write_yaml(tmp_path: Path, data: dict, filename: str = "test.yaml") -> Path:
    p = tmp_path / filename
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


# ── GoldClaim ─────────────────────────────────────────────────────────────────


class TestGoldClaim:
    def test_minimal(self):
        c = GoldClaim(claim_type="model_release", claim_text="OpenAI released GPT-5")
        assert c.claim_type == "model_release"
        assert c.claim_text == "OpenAI released GPT-5"
        assert c.supporting_span is None
        assert c.notes is None

    def test_with_span(self):
        c = GoldClaim(claim_type="benchmark_result", claim_text="x", supporting_span=(0, 50))
        assert c.supporting_span == (0, 50)


# ── ClaimExtractionExample ────────────────────────────────────────────────────


class TestClaimExtractionExample:
    def test_with_document_text(self):
        ex = ClaimExtractionExample(
            example_id="ex1",
            document_text="Some text about AI.",
            gold_claims=[GoldClaim(claim_type="other", claim_text="AI exists")],
        )
        assert ex.example_id == "ex1"
        assert ex.document_text == "Some text about AI."
        assert len(ex.gold_claims) == 1

    def test_document_id_optional(self):
        ex = ClaimExtractionExample(
            example_id="ex2",
            gold_claims=[],
        )
        assert ex.document_text is None
        assert ex.document_id is None


# ── SpanRetrievalExample ──────────────────────────────────────────────────────


class TestSpanRetrievalExample:
    def test_minimal(self):
        ex = SpanRetrievalExample(
            example_id="q1",
            query="What did Anthropic release?",
            gold_span_texts=["Anthropic released Claude 4"],
        )
        assert ex.example_id == "q1"
        assert len(ex.gold_span_texts) == 1
        assert ex.negative_span_texts == []

    def test_with_negatives(self):
        ex = SpanRetrievalExample(
            example_id="q2",
            query="OpenAI pricing",
            gold_span_texts=["OpenAI cut prices"],
            negative_span_texts=["OpenAI raised prices"],
        )
        assert len(ex.negative_span_texts) == 1


# ── load_dataset ──────────────────────────────────────────────────────────────


class TestLoadDataset:
    def test_load_claim_extraction(self, tmp_path):
        data = {
            "name": "test_ds",
            "task": "claim_extraction",
            "version": 1,
            "description": "test",
            "examples": [
                {
                    "example_id": "ex1",
                    "document_text": "Anthropic released Claude 4.",
                    "gold_claims": [
                        {"claim_type": "model_release", "claim_text": "Anthropic released Claude 4"}
                    ],
                }
            ],
        }
        p = _write_yaml(tmp_path, data)
        ds = load_dataset(p)
        assert ds.name == "test_ds"
        assert ds.task == "claim_extraction"
        assert ds.version == 1
        assert len(ds.examples) == 1
        assert isinstance(ds.examples[0], ClaimExtractionExample)
        assert ds.examples[0].gold_claims[0].claim_type == "model_release"

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
            "task": "claim_extraction",
            "version": 1,
            "examples": [],
        }
        p = _write_yaml(tmp_path, data)
        ds = load_dataset(p)
        # checksum must be 64-char hex string
        assert len(ds.checksum) == 64
        assert all(c in "0123456789abcdef" for c in ds.checksum)

    def test_checksum_is_deterministic(self, tmp_path):
        data = {
            "name": "ds",
            "task": "claim_extraction",
            "version": 1,
            "examples": [],
        }
        p = _write_yaml(tmp_path, data)
        ds1 = load_dataset(p)
        ds2 = load_dataset(p)
        assert ds1.checksum == ds2.checksum

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
