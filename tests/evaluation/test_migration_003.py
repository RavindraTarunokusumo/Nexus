# tests/evaluation/test_migration_003.py
"""Smoke tests: EvalDataset, EvalRun, EvalResult ORM models are importable and well-formed."""
import uuid

import pytest

from app.db.models import EvalDataset, EvalResult, EvalRun


class TestEvalDataset:
    def test_tablename(self):
        assert EvalDataset.__tablename__ == "eval_datasets"

    def test_required_columns(self):
        cols = {c.key for c in EvalDataset.__table__.columns}
        assert {"id", "name", "task", "version", "checksum", "example_count", "path", "created_at"} <= cols


class TestEvalRun:
    def test_tablename(self):
        assert EvalRun.__tablename__ == "eval_runs"

    def test_required_columns(self):
        cols = {c.key for c in EvalRun.__table__.columns}
        required = {
            "id", "dataset_id", "sut_model", "sut_prompt_version",
            "judge_name", "judge_model", "judge_prompt_version",
            "started_at", "status", "aggregate_scores", "total_cost_usd",
        }
        assert required <= cols


class TestEvalResult:
    def test_tablename(self):
        assert EvalResult.__tablename__ == "eval_results"

    def test_required_columns(self):
        cols = {c.key for c in EvalResult.__table__.columns}
        required = {
            "id", "run_id", "example_id", "sut_output",
            "judge_verdict", "deterministic_metrics", "status", "created_at",
        }
        assert required <= cols

    def test_run_id_has_fk(self):
        fks = {fk.column.table.name for fk in EvalResult.__table__.foreign_keys}
        assert "eval_runs" in fks
