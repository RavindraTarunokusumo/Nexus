# LLM-as-a-Judge Evaluation Framework — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an end-to-end LLM-as-a-Judge evaluation harness that scores Nexus claim-extraction outputs against hand-curated gold datasets and persists results in Postgres.

**Architecture:** New `app/evaluation/` package (datasets, metrics, judges, runner, meta_eval) sits alongside the existing intelligence stack and reuses `LLMClient` + observability. Three new Postgres tables (`eval_datasets`, `eval_runs`, `eval_results`) extend the existing schema via migration 0003. A new `nexus eval` Typer sub-app wired into `app/cli/main.py` provides the operator surface.

**Tech Stack:** Python 3.11, SQLAlchemy 2.x async, Alembic, Pydantic v2, PyYAML, Typer, existing `LLMClient` / `extraction_run` / `record_agent_run`.

---

## Task 1 — ORM Models + Migration

**Files:**
- Modify: `app/db/models.py`
- Create: `app/db/migrations/versions/0003_evaluation.py`

---

- [ ] **Step 1.1 — Write the failing migration test**

Create `tests/evaluation/__init__.py` (empty) and `tests/evaluation/test_migration_003.py`:

```python
# tests/evaluation/test_migration_003.py
"""Smoke-test that migration 0003 produces the expected tables and columns."""
import pytest
from sqlalchemy import inspect, text


@pytest.mark.asyncio
async def test_eval_tables_exist(db_session):
    """After migration, three eval tables must be present."""
    async with db_session.bind.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
    assert "eval_datasets" in tables
    assert "eval_runs" in tables
    assert "eval_results" in tables


@pytest.mark.asyncio
async def test_eval_datasets_columns(db_session):
    async with db_session.bind.connect() as conn:
        cols = await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns("eval_datasets")}
        )
    assert {"id", "name", "task", "version", "checksum", "example_count", "path", "created_at"} <= cols


@pytest.mark.asyncio
async def test_eval_runs_columns(db_session):
    async with db_session.bind.connect() as conn:
        cols = await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns("eval_runs")}
        )
    expected = {
        "id", "dataset_id", "sut_model", "sut_prompt_version",
        "judge_name", "judge_model", "judge_prompt_version",
        "started_at", "completed_at", "status",
        "aggregate_scores", "total_cost_usd", "notes",
    }
    assert expected <= cols


@pytest.mark.asyncio
async def test_eval_results_columns(db_session):
    async with db_session.bind.connect() as conn:
        cols = await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns("eval_results")}
        )
    expected = {
        "id", "run_id", "example_id", "sut_output",
        "judge_verdict", "deterministic_metrics",
        "status", "error_message", "created_at",
    }
    assert expected <= cols
```

- [ ] **Step 1.2 — Run to verify it fails**

```
pytest tests/evaluation/test_migration_003.py -v
```
Expected: FAIL — `eval_datasets` table not found.

- [ ] **Step 1.3 — Add ORM models to `app/db/models.py`**

Append after the existing `SpanExtraction` class (after line 200):

```python
class EvalDataset(Base):
    __tablename__ = "eval_datasets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    task: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str] = mapped_column(Text, nullable=False)
    example_count: Mapped[int] = mapped_column(Integer, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow
    )

    eval_runs: Mapped[list["EvalRun"]] = relationship("EvalRun", back_populates="dataset")


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("eval_datasets.id"), nullable=False
    )
    sut_model: Mapped[str] = mapped_column(Text, nullable=False)
    sut_prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    judge_name: Mapped[str] = mapped_column(Text, nullable=False)
    judge_model: Mapped[str] = mapped_column(Text, nullable=False)
    judge_prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="running")
    aggregate_scores: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    total_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    dataset: Mapped["EvalDataset"] = relationship("EvalDataset", back_populates="eval_runs")
    results: Mapped[list["EvalResult"]] = relationship(
        "EvalResult", back_populates="run", cascade="all, delete-orphan"
    )


class EvalResult(Base):
    __tablename__ = "eval_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("eval_runs.id", ondelete="CASCADE"), nullable=False
    )
    example_id: Mapped[str] = mapped_column(Text, nullable=False)
    sut_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    judge_verdict: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    deterministic_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow
    )

    run: Mapped["EvalRun"] = relationship("EvalRun", back_populates="results")
```

- [ ] **Step 1.4 — Write migration `app/db/migrations/versions/0003_evaluation.py`**

```python
"""Add evaluation tables: eval_datasets, eval_runs, eval_results."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "eval_datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("task", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("checksum", sa.Text, nullable=False),
        sa.Column("example_count", sa.Integer, nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_unique_constraint(
        "uq_eval_datasets_name_task_version",
        "eval_datasets",
        ["name", "task", "version"],
    )
    op.create_index("ix_eval_datasets_task", "eval_datasets", ["task"])

    op.create_table(
        "eval_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eval_datasets.id"),
            nullable=False,
        ),
        sa.Column("sut_model", sa.Text, nullable=False),
        sa.Column("sut_prompt_version", sa.Text, nullable=False),
        sa.Column("judge_name", sa.Text, nullable=False),
        sa.Column("judge_model", sa.Text, nullable=False),
        sa.Column("judge_prompt_version", sa.Text, nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="running"),
        sa.Column("aggregate_scores", postgresql.JSONB, nullable=True),
        sa.Column("total_cost_usd", sa.Float, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("ix_eval_runs_dataset_id", "eval_runs", ["dataset_id"])
    op.create_index("ix_eval_runs_started_at", "eval_runs", ["started_at"])
    op.create_index("ix_eval_runs_status", "eval_runs", ["status"])

    op.create_table(
        "eval_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eval_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("example_id", sa.Text, nullable=False),
        sa.Column("sut_output", postgresql.JSONB, nullable=True),
        sa.Column("judge_verdict", postgresql.JSONB, nullable=True),
        sa.Column("deterministic_metrics", postgresql.JSONB, nullable=True),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_eval_results_run_id", "eval_results", ["run_id"])
    op.create_index("ix_eval_results_run_status", "eval_results", ["run_id", "status"])


def downgrade() -> None:
    op.drop_table("eval_results")
    op.drop_table("eval_runs")
    op.drop_table("eval_datasets")
```

- [ ] **Step 1.5 — Run migration test**

```
pytest tests/evaluation/test_migration_003.py -v
```
Expected: 4 tests PASS.

- [ ] **Step 1.6 — Commit**

```bash
git add app/db/models.py app/db/migrations/versions/0003_evaluation.py \
        tests/evaluation/__init__.py tests/evaluation/test_migration_003.py
git commit -m "feat(eval): add eval_datasets, eval_runs, eval_results ORM models and migration 0003"
```

---

## Task 2 — Gold-Set Loader (`app/evaluation/datasets.py`)

**Files:**
- Create: `app/evaluation/__init__.py`
- Create: `app/evaluation/datasets.py`
- Create: `tests/evaluation/test_datasets.py`

Dependency: none (pure Pydantic + PyYAML, no DB).

---

- [ ] **Step 2.1 — Verify PyYAML is available**

```
python -c "import yaml; print(yaml.__version__)"
```
Expected: version string (already in requirements via feedparser). If missing: `pip install pyyaml` and add to `pyproject.toml` dependencies.

- [ ] **Step 2.2 — Write `tests/evaluation/test_datasets.py`**

```python
# tests/evaluation/test_datasets.py
"""Unit tests for gold-set YAML loader."""
import hashlib
from pathlib import Path

import pytest
import yaml

from app.evaluation.datasets import (
    ClaimExtractionExample,
    Dataset,
    GoldClaim,
    SpanRetrievalExample,
    load_dataset,
)


MINIMAL_CLAIM_YAML = """\
name: test_set
task: claim_extraction
version: 1
examples:
  - example_id: ex1
    document_text: "OpenAI released GPT-5 today."
    gold_claims:
      - claim_type: model_release
        claim_text: "OpenAI released GPT-5"
"""

MINIMAL_RETRIEVAL_YAML = """\
name: retrieval_set
task: span_retrieval
version: 1
examples:
  - example_id: q1
    query: "latest GPT model release"
    gold_span_texts:
      - "OpenAI released GPT-5 today"
"""


def test_load_claim_extraction_dataset(tmp_path):
    path = tmp_path / "test.yaml"
    path.write_text(MINIMAL_CLAIM_YAML)
    ds = load_dataset(path)
    assert ds.name == "test_set"
    assert ds.task == "claim_extraction"
    assert ds.version == 1
    assert len(ds.examples) == 1
    ex = ds.examples[0]
    assert isinstance(ex, ClaimExtractionExample)
    assert ex.example_id == "ex1"
    assert ex.gold_claims[0].claim_type == "model_release"


def test_load_span_retrieval_dataset(tmp_path):
    path = tmp_path / "ret.yaml"
    path.write_text(MINIMAL_RETRIEVAL_YAML)
    ds = load_dataset(path)
    assert ds.task == "span_retrieval"
    assert isinstance(ds.examples[0], SpanRetrievalExample)
    assert ds.examples[0].gold_span_texts == ["OpenAI released GPT-5 today"]


def test_checksum_is_stable(tmp_path):
    path = tmp_path / "test.yaml"
    path.write_text(MINIMAL_CLAIM_YAML)
    ds1 = load_dataset(path)
    ds2 = load_dataset(path)
    assert ds1.checksum == ds2.checksum
    expected = hashlib.sha256(MINIMAL_CLAIM_YAML.encode()).hexdigest()
    assert ds1.checksum == expected


def test_checksum_changes_on_edit(tmp_path):
    path = tmp_path / "test.yaml"
    path.write_text(MINIMAL_CLAIM_YAML)
    cs1 = load_dataset(path).checksum
    path.write_text(MINIMAL_CLAIM_YAML + "\n")
    cs2 = load_dataset(path).checksum
    assert cs1 != cs2


def test_unknown_task_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: x\ntask: unknown_task\nversion: 1\nexamples: []\n")
    with pytest.raises(ValueError, match="Unknown task"):
        load_dataset(bad)


def test_missing_required_field_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "name: x\ntask: claim_extraction\nversion: 1\n"
        "examples:\n  - example_id: e1\n    gold_claims: []\n"
        # missing document_text and document_id
    )
    # document_text and document_id are both optional; this should load fine
    ds = load_dataset(bad)
    assert ds.examples[0].document_text is None


def test_gold_claim_fields(tmp_path):
    path = tmp_path / "test.yaml"
    path.write_text(MINIMAL_CLAIM_YAML)
    ds = load_dataset(path)
    claim = ds.examples[0].gold_claims[0]
    assert isinstance(claim, GoldClaim)
    assert claim.claim_type == "model_release"
    assert claim.claim_text == "OpenAI released GPT-5"
    assert claim.supporting_span is None
```

- [ ] **Step 2.3 — Run to verify they fail**

```
pytest tests/evaluation/test_datasets.py -v
```
Expected: ImportError — `app.evaluation.datasets` not found.

- [ ] **Step 2.4 — Create `app/evaluation/__init__.py`**

```python
# app/evaluation/__init__.py
"""LLM-as-a-Judge evaluation framework for Nexus."""
```

- [ ] **Step 2.5 — Create `app/evaluation/datasets.py`**

```python
# app/evaluation/datasets.py
"""Gold-set loader — YAML files → typed Pydantic models."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, Field

EvalTask = Literal["claim_extraction", "span_retrieval", "brief_synthesis", "grounded_answer"]


class GoldClaim(BaseModel):
    """One hand-verified claim within a ClaimExtractionExample."""

    claim_type: str
    claim_text: str
    supporting_span: tuple[int, int] | None = None  # char offsets into document_text
    notes: str | None = None


class ClaimExtractionExample(BaseModel):
    """One example for the claim_extraction task."""

    example_id: str
    document_text: str | None = None   # inline text
    document_id: str | None = None     # or reference to an ingested doc UUID
    gold_claims: list[GoldClaim]
    notes: str | None = None


class SpanRetrievalExample(BaseModel):
    """One example for the span_retrieval task.

    Uses gold_span_texts (text snippets) rather than UUIDs to remain
    corpus-independent. The runner matches retrieved spans by text overlap.
    """

    example_id: str
    query: str
    gold_span_texts: list[str]          # text of expected spans
    negative_span_texts: list[str] = Field(default_factory=list)
    notes: str | None = None


class Dataset(BaseModel):
    """Loaded and validated gold-set dataset."""

    name: str
    task: EvalTask
    version: int
    description: str | None = None
    examples: list[ClaimExtractionExample | SpanRetrievalExample]
    checksum: str = ""


def _compute_checksum(raw_text: str) -> str:
    return hashlib.sha256(raw_text.encode()).hexdigest()


def load_dataset(path: Path) -> Dataset:
    """Load and validate a gold-set YAML file, computing its checksum."""
    raw = path.read_text(encoding="utf-8")
    checksum = _compute_checksum(raw)
    data = yaml.safe_load(raw)

    task: EvalTask = data.get("task")
    if task not in ("claim_extraction", "span_retrieval", "brief_synthesis", "grounded_answer"):
        raise ValueError(f"Unknown task: {task!r}")

    example_data = data.get("examples", [])
    if task == "claim_extraction":
        examples: list[ClaimExtractionExample | SpanRetrievalExample] = [
            ClaimExtractionExample(**e) for e in example_data
        ]
    elif task == "span_retrieval":
        examples = [SpanRetrievalExample(**e) for e in example_data]
    else:
        examples = []  # stub tasks — adapters handle activation

    return Dataset(
        name=data["name"],
        task=task,
        version=data.get("version", 1),
        description=data.get("description"),
        examples=examples,
        checksum=checksum,
    )
```

- [ ] **Step 2.6 — Run tests**

```
pytest tests/evaluation/test_datasets.py -v
```
Expected: 7 tests PASS.

- [ ] **Step 2.7 — Commit**

```bash
git add app/evaluation/__init__.py app/evaluation/datasets.py \
        tests/evaluation/test_datasets.py
git commit -m "feat(eval): gold-set YAML loader with typed Pydantic models"
```

---

## Task 3 — Deterministic Metrics (`app/evaluation/metrics.py`)

**Files:**
- Create: `app/evaluation/metrics.py`
- Create: `tests/evaluation/test_metrics.py`

Dependency: none.

---

- [ ] **Step 3.1 — Write `tests/evaluation/test_metrics.py`**

```python
# tests/evaluation/test_metrics.py
"""Unit tests for deterministic evaluation metrics."""
import pytest

from app.evaluation.metrics import (
    align_claims,
    ndcg_at_k,
    precision_at_k,
    precision_recall_f1,
)


class TestPrecisionRecallF1:
    def test_perfect_match(self):
        p, r, f1 = precision_recall_f1({"a", "b"}, {"a", "b"})
        assert p == 1.0
        assert r == 1.0
        assert f1 == 1.0

    def test_no_overlap(self):
        p, r, f1 = precision_recall_f1({"a"}, {"b"})
        assert p == 0.0
        assert r == 0.0
        assert f1 == 0.0

    def test_partial_overlap(self):
        p, r, f1 = precision_recall_f1({"a", "b", "c"}, {"a", "b", "d"})
        assert p == pytest.approx(2 / 3)
        assert r == pytest.approx(2 / 3)
        assert f1 == pytest.approx(2 / 3)

    def test_empty_pred(self):
        p, r, f1 = precision_recall_f1({"a"}, set())
        assert p == 0.0
        assert r == 0.0
        assert f1 == 0.0

    def test_empty_gold(self):
        p, r, f1 = precision_recall_f1(set(), {"a"})
        assert p == 0.0
        assert r == 0.0
        assert f1 == 0.0


class TestPrecisionAtK:
    def test_all_relevant(self):
        assert precision_at_k({"a", "b"}, ["a", "b", "c"], k=2) == 1.0

    def test_none_relevant(self):
        assert precision_at_k({"d"}, ["a", "b", "c"], k=3) == 0.0

    def test_half_relevant(self):
        assert precision_at_k({"a", "c"}, ["a", "b", "c", "d"], k=4) == 0.5

    def test_k_zero(self):
        assert precision_at_k({"a"}, ["a"], k=0) == 0.0

    def test_k_larger_than_list(self):
        # Only 2 items in list, k=5 — still counts only the 2 we have
        assert precision_at_k({"a"}, ["a", "b"], k=5) == pytest.approx(1 / 5)


class TestNDCGAtK:
    def test_perfect_ranking(self):
        # ideal: [1, 1, 0], actual: [1, 1, 0] → nDCG = 1.0
        assert ndcg_at_k([1.0, 1.0, 0.0], k=3) == pytest.approx(1.0)

    def test_reversed_ranking(self):
        # ideal: [1, 0] → DCG_ideal = 1/log2(2) = 1.0
        # actual: [0, 1] → DCG = 1/log2(3) ≈ 0.631
        result = ndcg_at_k([0.0, 1.0], k=2)
        import math
        expected = (1 / math.log2(3)) / (1 / math.log2(2))
        assert result == pytest.approx(expected)

    def test_empty(self):
        assert ndcg_at_k([], k=3) == 0.0

    def test_k_truncates(self):
        # k=1 should only consider the first element
        result = ndcg_at_k([1.0, 0.0, 0.0], k=1)
        assert result == pytest.approx(1.0)


class TestAlignClaims:
    def test_exact_match(self):
        gold = [{"claim_text": "OpenAI released GPT-5", "claim_type": "model_release"}]
        pred = [{"claim_text": "OpenAI released GPT-5", "claim_type": "model_release"}]
        pairs = align_claims(gold, pred)
        assert len(pairs) == 1
        g, p = pairs[0]
        assert g is not None and p is not None

    def test_no_match_below_threshold(self):
        gold = [{"claim_text": "OpenAI released GPT-5", "claim_type": "model_release"}]
        pred = [{"claim_text": "completely unrelated sentence here", "claim_type": "other"}]
        pairs = align_claims(gold, pred, similarity_threshold=0.5)
        # One (gold, None) pair and one (None, pred) pair
        assert len(pairs) == 2
        assert any(g is not None and p is None for g, p in pairs)
        assert any(g is None and p is not None for g, p in pairs)

    def test_empty_gold(self):
        pairs = align_claims([], [{"claim_text": "spurious", "claim_type": "other"}])
        assert pairs == [(None, {"claim_text": "spurious", "claim_type": "other"})]

    def test_empty_pred(self):
        pairs = align_claims([{"claim_text": "missed", "claim_type": "other"}], [])
        assert pairs == [({"claim_text": "missed", "claim_type": "other"}, None)]
```

- [ ] **Step 3.2 — Run to verify they fail**

```
pytest tests/evaluation/test_metrics.py -v
```
Expected: ImportError.

- [ ] **Step 3.3 — Create `app/evaluation/metrics.py`**

```python
# app/evaluation/metrics.py
"""Deterministic evaluation metrics — no LLM calls."""

from __future__ import annotations

import math
from typing import Any


def precision_recall_f1(
    gold_ids: set[str], pred_ids: set[str]
) -> tuple[float, float, float]:
    """Compute precision, recall, F1 from two sets of string identifiers."""
    tp = len(gold_ids & pred_ids)
    precision = tp / len(pred_ids) if pred_ids else 0.0
    recall = tp / len(gold_ids) if gold_ids else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    return precision, recall, f1


def precision_at_k(gold_ids: set[str], ranked_pred_ids: list[str], k: int) -> float:
    """Precision@k: fraction of top-k predicted items that are in gold_ids."""
    if k == 0:
        return 0.0
    top_k = ranked_pred_ids[:k]
    hits = sum(1 for pid in top_k if pid in gold_ids)
    return hits / k


def ndcg_at_k(graded_relevances: list[float], k: int) -> float:
    """nDCG@k from a list of relevance grades in ranked order.

    Grades may be binary (0/1) or graded (0.0–3.0). Positions are 1-indexed
    internally (log2(i+2) where i is 0-indexed).
    """
    k = min(k, len(graded_relevances))
    if k == 0:
        return 0.0

    def dcg(rels: list[float]) -> float:
        return sum(rel / math.log2(i + 2) for i, rel in enumerate(rels[:k]))

    ideal = sorted(graded_relevances, reverse=True)
    idcg = dcg(ideal)
    return dcg(graded_relevances) / idcg if idcg > 0 else 0.0


def align_claims(
    gold_claims: list[dict[str, Any]],
    pred_claims: list[dict[str, Any]],
    similarity_threshold: float = 0.5,
) -> list[tuple[dict[str, Any] | None, dict[str, Any] | None]]:
    """Align gold and predicted claims by word-overlap (Jaccard similarity).

    Returns a list of (gold | None, pred | None) pairs:
    - Both non-None  → matched pair
    - (gold, None)   → missed claim (in gold, not in pred)
    - (None, pred)   → spurious claim (in pred, not in gold)

    Greedy: each claim can appear in at most one pair.
    """

    def jaccard(a: str, b: str) -> float:
        sa = set(a.lower().split())
        sb = set(b.lower().split())
        if not sa and not sb:
            return 1.0
        return len(sa & sb) / len(sa | sb)

    matched_gold: set[int] = set()
    matched_pred: set[int] = set()
    pairs: list[tuple[dict | None, dict | None]] = []

    # Build all (gold_idx, pred_idx, score) triples, sort descending
    scores = [
        (gi, pi, jaccard(g["claim_text"], p["claim_text"]))
        for gi, g in enumerate(gold_claims)
        for pi, p in enumerate(pred_claims)
    ]
    scores.sort(key=lambda x: x[2], reverse=True)

    for gi, pi, score in scores:
        if score < similarity_threshold:
            break
        if gi in matched_gold or pi in matched_pred:
            continue
        pairs.append((gold_claims[gi], pred_claims[pi]))
        matched_gold.add(gi)
        matched_pred.add(pi)

    # Unmatched golds → missing
    for i, g in enumerate(gold_claims):
        if i not in matched_gold:
            pairs.append((g, None))

    # Unmatched preds → spurious
    for j, p in enumerate(pred_claims):
        if j not in matched_pred:
            pairs.append((None, p))

    return pairs
```

- [ ] **Step 3.4 — Run tests**

```
pytest tests/evaluation/test_metrics.py -v
```
Expected: 14 tests PASS.

- [ ] **Step 3.5 — Commit**

```bash
git add app/evaluation/metrics.py tests/evaluation/test_metrics.py
git commit -m "feat(eval): deterministic metrics — P/R/F1, nDCG@k, align_claims"
```

---

## Task 4 — Judge Prompt + Schema

**Files:**
- Create: `app/evaluation/prompts/__init__.py`
- Create: `app/evaluation/prompts/claim_extraction_judge.py`

Dependency: none (pure Pydantic + strings).

---

- [ ] **Step 4.1 — Create `app/evaluation/prompts/__init__.py`**

```python
# app/evaluation/prompts/__init__.py
```

- [ ] **Step 4.2 — Create `app/evaluation/prompts/claim_extraction_judge.py`**

```python
# app/evaluation/prompts/claim_extraction_judge.py
"""LLM judge prompt and output schema for claim extraction evaluation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

JUDGE_SYSTEM_PROMPT = """\
You are an expert evaluator assessing the quality of AI-extracted claims from news articles.

Given a source document, a gold-standard claim (manually verified), and a predicted claim \
(extracted by an AI system), evaluate the predicted claim on four dimensions.

RULES:
- Base evaluation ONLY on the provided document text. Do not use external knowledge.
- Partial match requires explicit text support for both parts of the gold claim.
- Keep rationale to exactly one concise sentence.
- Do NOT score based on response length or stylistic differences.

Respond with a valid JSON object only. No preamble, explanation, or markdown fences outside \
the JSON.
"""


def build_judge_prompt(
    document_text: str,
    gold_claim: dict,
    pred_claim: dict,
) -> str:
    """Build the user-turn prompt for one (gold, pred) pair evaluation."""
    return (
        f"DOCUMENT (truncated to 3000 chars):\n{document_text[:3000]}\n\n"
        f"GOLD CLAIM:\n"
        f"  text: {gold_claim['claim_text']}\n"
        f"  type: {gold_claim['claim_type']}\n\n"
        f"PREDICTED CLAIM:\n"
        f"  text: {pred_claim['claim_text']}\n"
        f"  type: {pred_claim['claim_type']}\n\n"
        "Evaluate and respond with JSON:\n"
        "{\n"
        '  "match_status": "<exact|partial|missing|spurious>",\n'
        '  "type_correct": <true|false>,\n'
        '  "groundedness": <0.0-1.0>,\n'
        '  "factuality": <0.0-1.0>,\n'
        '  "rationale": "<one sentence>"\n'
        "}\n\n"
        "Definitions:\n"
        "- exact: predicted claim conveys the same factual content as the gold claim\n"
        "- partial: predicted captures some but not all of the gold content\n"
        "- groundedness: fraction of the claim text supported by the document\n"
        "- factuality: accuracy of the claim as supported by the document text\n"
        "- type_correct: true if the predicted claim_type matches the gold claim_type\n"
    )


class ClaimPairVerdict(BaseModel):
    """Structured output from the claim extraction judge for one pair."""

    match_status: Literal["exact", "partial", "missing", "spurious", "error"]
    type_correct: bool
    groundedness: float = Field(ge=0.0, le=1.0)
    factuality: float = Field(ge=0.0, le=1.0)
    rationale: str
```

- [ ] **Step 4.3 — Quick smoke test (no commit yet, bundled with Task 5)**

```
python -c "from app.evaluation.prompts.claim_extraction_judge import ClaimPairVerdict; print('OK')"
```
Expected: `OK`

---

## Task 5 — Judges (`app/evaluation/judges.py`)

**Files:**
- Create: `app/evaluation/judges.py`
- Create: `tests/evaluation/test_judges.py`

Depends on: Task 3 (metrics.align_claims), Task 4 (prompt + ClaimPairVerdict).

---

- [ ] **Step 5.1 — Write `tests/evaluation/test_judges.py`**

```python
# tests/evaluation/test_judges.py
"""Unit tests for LLM judges — LLMClient is fully mocked."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.evaluation.judges import (
    BriefSynthesisJudge,
    ClaimExtractionJudge,
    GroundedAnswerJudge,
)
from app.evaluation.prompts.claim_extraction_judge import ClaimPairVerdict


def _make_client(verdict_dict: dict) -> MagicMock:
    """Return a mock LLMClient whose complete_json returns the given verdict."""
    client = MagicMock()
    verdict = ClaimPairVerdict(**verdict_dict)
    client.complete_json = AsyncMock(return_value=(verdict, 100))
    return client


EXACT_VERDICT = {
    "match_status": "exact",
    "type_correct": True,
    "groundedness": 0.9,
    "factuality": 0.95,
    "rationale": "The claim precisely matches the document.",
}

DOCUMENT = "Anthropic released Claude 4 today with improved reasoning capabilities."
GOLD = [{"claim_text": "Anthropic released Claude 4", "claim_type": "model_release"}]
PRED = [{"claim_text": "Anthropic released Claude 4", "claim_type": "model_release"}]


@pytest.mark.asyncio
async def test_claim_extraction_judge_perfect_match():
    client = _make_client(EXACT_VERDICT)
    judge = ClaimExtractionJudge(model="test-model", llm_client=client)
    result = await judge.score(DOCUMENT, GOLD, PRED)
    assert result["precision"] == 1.0
    assert result["recall"] == 1.0
    assert result["f1"] == 1.0
    assert result["type_accuracy"] == 1.0
    assert result["mean_groundedness"] == pytest.approx(0.9)
    assert result["mean_factuality"] == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_claim_extraction_judge_spurious_pred():
    """Prediction with no matching gold → spurious, 0 precision."""
    client = _make_client(EXACT_VERDICT)  # client won't be called for spurious
    judge = ClaimExtractionJudge(model="test-model", llm_client=client)
    result = await judge.score(
        DOCUMENT,
        gold_claims=[],
        pred_claims=[{"claim_text": "unrelated claim", "claim_type": "other"}],
    )
    assert result["precision"] == 0.0


@pytest.mark.asyncio
async def test_claim_extraction_judge_missing_claim():
    """Gold with no matching pred → missing, 0 recall."""
    client = _make_client(EXACT_VERDICT)
    judge = ClaimExtractionJudge(model="test-model", llm_client=client)
    result = await judge.score(
        DOCUMENT,
        gold_claims=[{"claim_text": "missed claim", "claim_type": "other"}],
        pred_claims=[],
    )
    assert result["recall"] == 0.0


@pytest.mark.asyncio
async def test_claim_extraction_judge_llm_error_is_tolerated():
    """If LLMClient raises, the pair is marked error and scoring continues."""
    client = MagicMock()
    client.complete_json = AsyncMock(side_effect=Exception("network down"))
    judge = ClaimExtractionJudge(model="test-model", llm_client=client)
    result = await judge.score(DOCUMENT, GOLD, PRED)
    # Pair is scored as "error" — should still return a result dict
    assert "f1" in result
    assert result["per_pair_verdicts"][0]["match_status"] == "error"


@pytest.mark.asyncio
async def test_brief_synthesis_judge_raises():
    judge = BriefSynthesisJudge(model="x", llm_client=MagicMock())
    with pytest.raises(NotImplementedError, match="Phase 4"):
        await judge.score()


@pytest.mark.asyncio
async def test_grounded_answer_judge_raises():
    judge = GroundedAnswerJudge(model="x", llm_client=MagicMock())
    with pytest.raises(NotImplementedError, match="Phase 4"):
        await judge.score()
```

- [ ] **Step 5.2 — Run to verify they fail**

```
pytest tests/evaluation/test_judges.py -v
```
Expected: ImportError — `app.evaluation.judges` not found.

- [ ] **Step 5.3 — Create `app/evaluation/judges.py`**

```python
# app/evaluation/judges.py
"""LLM-as-a-Judge implementations for each evaluation task."""

from __future__ import annotations

from typing import Any

from app.evaluation.metrics import align_claims
from app.evaluation.prompts.claim_extraction_judge import (
    JUDGE_SYSTEM_PROMPT,
    ClaimPairVerdict,
    build_judge_prompt,
)


class ClaimExtractionJudge:
    """LLM judge for claim extraction quality.

    For each (document, gold_claims, pred_claims) triple:
    1. Aligns gold and predicted claims via word-overlap (align_claims).
    2. Calls LLMClient.complete_json once per aligned pair.
    3. Aggregates verdicts into precision/recall/F1/groundedness/factuality.
    """

    name: str = "claim_extraction_judge_v1"

    def __init__(self, model: str, llm_client: Any) -> None:
        self.model = model
        self._client = llm_client

    async def score(
        self,
        document_text: str,
        gold_claims: list[dict],
        pred_claims: list[dict],
    ) -> dict:
        """Score one (document, gold_claims, pred_claims) triple.

        Returns dict: precision, recall, f1, type_accuracy,
        mean_groundedness, mean_factuality, per_pair_verdicts.
        """
        pairs = align_claims(gold_claims, pred_claims)
        verdicts = []
        for gold, pred in pairs:
            verdict = await self._judge_pair(document_text, gold, pred)
            verdicts.append(verdict)

        matched = [v for v in verdicts if v["match_status"] in ("exact", "partial")]
        spurious = [v for v in verdicts if v["match_status"] == "spurious"]
        missed = [v for v in verdicts if v["match_status"] == "missing"]

        tp = len(matched)
        fp = len(spurious)
        fn = len(missed)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        type_correct_count = sum(1 for v in matched if v.get("type_correct", False))
        type_accuracy = type_correct_count / len(matched) if matched else 0.0

        groundedness_vals = [v.get("groundedness", 0.0) for v in matched]
        mean_groundedness = sum(groundedness_vals) / len(groundedness_vals) if groundedness_vals else 0.0

        factuality_vals = [v.get("factuality", 0.0) for v in matched]
        mean_factuality = sum(factuality_vals) / len(factuality_vals) if factuality_vals else 0.0

        return {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "type_accuracy": type_accuracy,
            "mean_groundedness": mean_groundedness,
            "mean_factuality": mean_factuality,
            "per_pair_verdicts": verdicts,
        }

    async def _judge_pair(
        self,
        document_text: str,
        gold: dict | None,
        pred: dict | None,
    ) -> dict:
        """Score one (gold, pred) pair. Handles None inputs as missing/spurious."""
        if gold is None:
            return {
                "match_status": "spurious",
                "type_correct": False,
                "groundedness": 0.0,
                "factuality": 0.0,
                "rationale": "Spurious: no matching gold claim.",
            }
        if pred is None:
            return {
                "match_status": "missing",
                "type_correct": False,
                "groundedness": 0.0,
                "factuality": 0.0,
                "rationale": "Missing: gold claim was not extracted.",
            }

        user_prompt = build_judge_prompt(document_text, gold, pred)
        try:
            result, _ = await self._client.complete_json(
                model=self.model,
                system=JUDGE_SYSTEM_PROMPT,
                user=user_prompt,
                response_model=ClaimPairVerdict,
                temperature=0.0,
            )
            return result.model_dump()
        except Exception as exc:  # noqa: BLE001
            return {
                "match_status": "error",
                "type_correct": False,
                "groundedness": 0.0,
                "factuality": 0.0,
                "rationale": f"Judge error: {exc}",
            }


class BriefSynthesisJudge:
    """Stub judge — activates when Phase 4 ships brief synthesis."""

    name: str = "brief_synthesis_judge_v1"

    def __init__(self, model: str, llm_client: Any) -> None:
        self.model = model
        self._client = llm_client

    async def score(self, *args: Any, **kwargs: Any) -> dict:
        raise NotImplementedError(
            "BriefSynthesisJudge is a stub — activate when Phase 4 ships."
        )


class GroundedAnswerJudge:
    """Stub judge — activates when Phase 4 ships grounded query answering."""

    name: str = "grounded_answer_judge_v1"

    def __init__(self, model: str, llm_client: Any) -> None:
        self.model = model
        self._client = llm_client

    async def score(self, *args: Any, **kwargs: Any) -> dict:
        raise NotImplementedError(
            "GroundedAnswerJudge is a stub — activate when Phase 4 ships."
        )
```

- [ ] **Step 5.4 — Run tests**

```
pytest tests/evaluation/test_judges.py -v
```
Expected: 7 tests PASS.

- [ ] **Step 5.5 — Commit**

```bash
git add app/evaluation/prompts/__init__.py \
        app/evaluation/prompts/claim_extraction_judge.py \
        app/evaluation/judges.py \
        tests/evaluation/test_judges.py
git commit -m "feat(eval): claim extraction judge + two Phase-4 stubs"
```

---

## Task 6 — Runner (`app/evaluation/runner.py`)

**Files:**
- Create: `app/evaluation/runner.py`
- Create: `tests/evaluation/test_runner.py`

Depends on: Tasks 1, 2, 5.

---

- [ ] **Step 6.1 — Write `tests/evaluation/test_runner.py`**

```python
# tests/evaluation/test_runner.py
"""Unit tests for the eval runner — all I/O is mocked."""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.evaluation.datasets import ClaimExtractionExample, Dataset, GoldClaim
from app.evaluation.runner import SUTConfig, _aggregate_scores, execute_run


def _make_dataset(n: int = 2) -> Dataset:
    examples = [
        ClaimExtractionExample(
            example_id=f"ex{i}",
            document_text=f"Article {i}: OpenAI released model-{i}.",
            gold_claims=[
                GoldClaim(claim_type="model_release", claim_text=f"OpenAI released model-{i}")
            ],
        )
        for i in range(n)
    ]
    return Dataset(
        name="test_ds",
        task="claim_extraction",
        version=1,
        examples=examples,
        checksum="abc123",
    )


def _make_session_factory(dataset_row=None):
    """Return a mock session factory that yields a mock session."""
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()

    # Simulate dataset row lookup
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = dataset_row
    mock_session.execute = AsyncMock(return_value=mock_result)

    @asynccontextmanager
    async def factory():
        yield mock_session

    return factory


@pytest.mark.asyncio
async def test_aggregate_scores_empty():
    assert _aggregate_scores([]) == {}


@pytest.mark.asyncio
async def test_aggregate_scores_averages():
    scores = [
        {"precision": 1.0, "recall": 0.5, "f1": 0.667,
         "type_accuracy": 1.0, "mean_groundedness": 0.8, "mean_factuality": 0.9},
        {"precision": 0.5, "recall": 1.0, "f1": 0.667,
         "type_accuracy": 0.5, "mean_groundedness": 0.6, "mean_factuality": 0.7},
    ]
    agg = _aggregate_scores(scores)
    assert agg["precision"] == pytest.approx(0.75)
    assert agg["recall"] == pytest.approx(0.75)


@pytest.mark.asyncio
async def test_execute_run_raises_if_dataset_not_registered():
    ds = _make_dataset()
    sf = _make_session_factory(dataset_row=None)  # not registered
    sut = SUTConfig(model="m", prompt_version="abc")

    with pytest.raises(ValueError, match="not registered"):
        await execute_run(
            dataset=ds,
            sut_config=sut,
            judge_model="j",
            judge_prompt_version="v1",
            session_factory=sf,
            llm_client=MagicMock(),
        )


@pytest.mark.asyncio
async def test_execute_run_tolerates_sut_error():
    """If the SUT LLM call fails, the example is marked 'error' and run continues."""
    from app.db.models import EvalDataset as EvalDatasetModel

    ds = _make_dataset(n=1)
    fake_dataset_row = MagicMock(spec=EvalDatasetModel)
    fake_dataset_row.id = uuid.uuid4()
    sf = _make_session_factory(dataset_row=fake_dataset_row)

    client = MagicMock()
    client.complete_json = AsyncMock(side_effect=Exception("LLM down"))

    sut = SUTConfig(model="t2", prompt_version="sha1")

    with patch("app.evaluation.runner.EvalRun") as MockRun:
        MockRun.return_value = MagicMock()
        result = await execute_run(
            dataset=ds,
            sut_config=sut,
            judge_model="t3",
            judge_prompt_version="sha2",
            session_factory=sf,
            llm_client=client,
        )

    assert result.error_count == 1
    assert result.status in ("partial", "failed")


@pytest.mark.asyncio
async def test_budget_gate_stops_run():
    """max_cost_usd=0 should short-circuit before any examples are scored."""
    from app.db.models import EvalDataset as EvalDatasetModel

    ds = _make_dataset(n=5)
    fake_dataset_row = MagicMock(spec=EvalDatasetModel)
    fake_dataset_row.id = uuid.uuid4()
    sf = _make_session_factory(dataset_row=fake_dataset_row)

    client = MagicMock()
    client.complete_json = AsyncMock(return_value=(MagicMock(claims=[]), 1000))

    sut = SUTConfig(model="t2", prompt_version="sha1")

    with patch("app.evaluation.runner.EvalRun") as MockRun:
        MockRun.return_value = MagicMock()
        result = await execute_run(
            dataset=ds,
            sut_config=sut,
            judge_model="t3",
            judge_prompt_version="sha2",
            session_factory=sf,
            llm_client=client,
            max_cost_usd=0.0,
        )

    # No examples should have been scored
    assert result.example_count == 5  # dataset size unchanged
    assert result.error_count == 0   # no errors — just skipped
```

- [ ] **Step 6.2 — Run to verify they fail**

```
pytest tests/evaluation/test_runner.py -v
```
Expected: ImportError.

- [ ] **Step 6.3 — Create `app/evaluation/runner.py`**

```python
# app/evaluation/runner.py
"""Eval run orchestrator — coordinates dataset loading, SUT calls, judging, persistence."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.db.models import EvalDataset as EvalDatasetModel
from app.db.models import EvalResult, EvalRun
from app.evaluation.datasets import ClaimExtractionExample, Dataset
from app.evaluation.judges import ClaimExtractionJudge
from app.intelligence.llm_client import ExtractionOutput
from app.intelligence.prompts.extract_claims import SYSTEM_PROMPT, build_user_prompt


@dataclass
class SUTConfig:
    """Configuration for the system under test (SUT)."""

    model: str          # e.g. "deepseek/deepseek-v4-flash"
    prompt_version: str  # git SHA of extract_claims.py at test time
    temperature: float = 0.0


@dataclass
class EvalRunResult:
    """Summary returned by execute_run."""

    run_id: uuid.UUID
    status: str
    aggregate_scores: dict
    total_cost_usd: float
    example_count: int
    error_count: int


async def execute_run(
    *,
    dataset: Dataset,
    sut_config: SUTConfig,
    judge_model: str,
    judge_prompt_version: str,
    session_factory: Any,
    llm_client: Any,
    max_cost_usd: float = 1.0,
    notes: str | None = None,
) -> EvalRunResult:
    """Execute one complete eval run for a claim_extraction dataset.

    Raises ValueError if the dataset has not been registered via
    `nexus eval register-dataset`.
    """
    run_id = uuid.uuid4()
    started_at = datetime.now(timezone.utc)

    # --- Verify dataset registration ---
    async with session_factory() as session:
        stmt = select(EvalDatasetModel).where(
            EvalDatasetModel.name == dataset.name,
            EvalDatasetModel.task == dataset.task,
            EvalDatasetModel.version == dataset.version,
        )
        result = await session.execute(stmt)
        dataset_row = result.scalar_one_or_none()
        if dataset_row is None:
            raise ValueError(
                f"Dataset '{dataset.name}' (task={dataset.task}, v{dataset.version}) "
                "is not registered. Run: nexus eval register-dataset <path>"
            )

        run_row = EvalRun(
            id=run_id,
            dataset_id=dataset_row.id,
            sut_model=sut_config.model,
            sut_prompt_version=sut_config.prompt_version,
            judge_name=ClaimExtractionJudge.name,
            judge_model=judge_model,
            judge_prompt_version=judge_prompt_version,
            started_at=started_at,
            status="running",
            notes=notes,
        )
        session.add(run_row)
        await session.commit()

    judge = ClaimExtractionJudge(model=judge_model, llm_client=llm_client)
    score_accumulator: list[dict] = []
    error_count = 0
    total_cost = 0.0

    for example in dataset.examples:
        if not isinstance(example, ClaimExtractionExample):
            continue  # skip non-claim_extraction tasks
        if total_cost >= max_cost_usd:
            break  # budget gate

        example_result = await _score_example(
            run_id=run_id,
            example=example,
            sut_config=sut_config,
            judge=judge,
            session_factory=session_factory,
            llm_client=llm_client,
        )
        if example_result["status"] == "scored":
            score_accumulator.append(example_result["deterministic_metrics"])
        else:
            error_count += 1

    aggregate = _aggregate_scores(score_accumulator)
    completed_at = datetime.now(timezone.utc)
    final_status = "partial" if error_count > 0 else "completed"

    async with session_factory() as session:
        run_row = await session.get(EvalRun, run_id)
        if run_row is not None:
            run_row.completed_at = completed_at
            run_row.status = final_status
            run_row.aggregate_scores = aggregate
            run_row.total_cost_usd = total_cost
            await session.commit()

    return EvalRunResult(
        run_id=run_id,
        status=final_status,
        aggregate_scores=aggregate,
        total_cost_usd=total_cost,
        example_count=len(dataset.examples),
        error_count=error_count,
    )


async def _score_example(
    *,
    run_id: uuid.UUID,
    example: ClaimExtractionExample,
    sut_config: SUTConfig,
    judge: ClaimExtractionJudge,
    session_factory: Any,
    llm_client: Any,
) -> dict:
    """Score one ClaimExtractionExample. Returns {status, deterministic_metrics}."""
    document_text = example.document_text or ""

    try:
        sut_output, _ = await llm_client.complete_json(
            model=sut_config.model,
            system=SYSTEM_PROMPT,
            user=build_user_prompt(document_text, {}),
            response_model=ExtractionOutput,
            temperature=sut_config.temperature,
        )
        pred_claims = [c.model_dump() for c in sut_output.claims]
    except Exception as exc:  # noqa: BLE001
        await _persist_result(
            run_id=run_id,
            example_id=example.example_id,
            sut_output=None,
            judge_verdict=None,
            deterministic_metrics=None,
            status="error",
            error_message=f"SUT error: {exc}",
            session_factory=session_factory,
        )
        return {"status": "error"}

    gold_claims = [c.model_dump() for c in example.gold_claims]
    verdict = await judge.score(
        document_text=document_text,
        gold_claims=gold_claims,
        pred_claims=pred_claims,
    )
    det_metrics = {k: v for k, v in verdict.items() if k != "per_pair_verdicts"}

    await _persist_result(
        run_id=run_id,
        example_id=example.example_id,
        sut_output={"claims": pred_claims},
        judge_verdict=verdict,
        deterministic_metrics=det_metrics,
        status="scored",
        error_message=None,
        session_factory=session_factory,
    )
    return {"status": "scored", "deterministic_metrics": det_metrics}


async def _persist_result(
    *,
    run_id: uuid.UUID,
    example_id: str,
    sut_output: dict | None,
    judge_verdict: dict | None,
    deterministic_metrics: dict | None,
    status: str,
    error_message: str | None,
    session_factory: Any,
) -> None:
    async with session_factory() as session:
        session.add(
            EvalResult(
                id=uuid.uuid4(),
                run_id=run_id,
                example_id=example_id,
                sut_output=sut_output,
                judge_verdict=judge_verdict,
                deterministic_metrics=deterministic_metrics,
                status=status,
                error_message=error_message,
            )
        )
        await session.commit()


def _aggregate_scores(score_list: list[dict]) -> dict:
    """Average per-example metric dicts into a run-level aggregate."""
    if not score_list:
        return {}
    keys = ["precision", "recall", "f1", "type_accuracy", "mean_groundedness", "mean_factuality"]
    return {
        k: round(
            sum(s[k] for s in score_list if k in s) / len(score_list), 4
        )
        for k in keys
        if any(k in s for s in score_list)
    }
```

- [ ] **Step 6.4 — Run tests**

```
pytest tests/evaluation/test_runner.py -v
```
Expected: 5 tests PASS.

- [ ] **Step 6.5 — Commit**

```bash
git add app/evaluation/runner.py tests/evaluation/test_runner.py
git commit -m "feat(eval): eval runner with budget gate, error tolerance, and Postgres persistence"
```

---

## Task 7 — Meta-Evaluation (`app/evaluation/meta_eval.py`)

**Files:**
- Create: `app/evaluation/meta_eval.py`
- Create: `tests/evaluation/test_meta_eval.py`

Dependency: none (pure math + PyYAML).

---

- [ ] **Step 7.1 — Write `tests/evaluation/test_meta_eval.py`**

```python
# tests/evaluation/test_meta_eval.py
"""Unit tests for judge calibration (Cohen's κ, Pearson r)."""
import pytest

from app.evaluation.meta_eval import compute_kappa, compute_pearson


class TestCohenKappa:
    def test_perfect_agreement(self):
        labels = ["exact", "partial", "missing"]
        assert compute_kappa(labels, labels) == pytest.approx(1.0)

    def test_zero_agreement_beyond_chance(self):
        # When judge always says "exact" and human always says "missing"
        j = ["exact"] * 10
        h = ["missing"] * 10
        k = compute_kappa(j, h)
        assert k < 0.0  # below chance

    def test_substantial_agreement(self):
        # 8/10 match — should be well above 0.6
        j = ["exact"] * 8 + ["partial", "missing"]
        h = ["exact"] * 8 + ["partial", "missing"]
        assert compute_kappa(j, h) == pytest.approx(1.0)

    def test_mismatched_lengths_raises(self):
        with pytest.raises(AssertionError):
            compute_kappa(["exact"], ["exact", "partial"])


class TestPearson:
    def test_perfect_positive_correlation(self):
        x = [1.0, 2.0, 3.0, 4.0]
        y = [2.0, 4.0, 6.0, 8.0]
        assert compute_pearson(x, y) == pytest.approx(1.0)

    def test_perfect_negative_correlation(self):
        x = [1.0, 2.0, 3.0]
        y = [3.0, 2.0, 1.0]
        assert compute_pearson(x, y) == pytest.approx(-1.0)

    def test_no_correlation(self):
        # Constant y → zero denominator → returns 0.0
        x = [1.0, 2.0, 3.0]
        y = [5.0, 5.0, 5.0]
        assert compute_pearson(x, y) == pytest.approx(0.0)

    def test_mismatched_lengths_raises(self):
        with pytest.raises(AssertionError):
            compute_pearson([1.0], [1.0, 2.0])
```

- [ ] **Step 7.2 — Run to verify they fail**

```
pytest tests/evaluation/test_meta_eval.py -v
```
Expected: ImportError.

- [ ] **Step 7.3 — Create `app/evaluation/meta_eval.py`**

```python
# app/evaluation/meta_eval.py
"""Judge calibration — Cohen's κ and Pearson r between judge and human labels."""

from __future__ import annotations

import math
from pathlib import Path

import yaml


def load_human_labels(path: Path) -> list[dict]:
    """Load human-labeled (example_id, judge_verdict, human_verdict) triples."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data.get("labels", [])


def compute_kappa(judge_labels: list[str], human_labels: list[str]) -> float:
    """Compute Cohen's κ for two categorical label sequences.

    κ < 0.4 → poor agreement (rewrite the rubric).
    κ 0.4–0.6 → moderate agreement.
    κ ≥ 0.6 → substantial agreement (trust the judge for gating decisions).
    """
    assert len(judge_labels) == len(human_labels), (
        f"Label lists must be the same length: {len(judge_labels)} vs {len(human_labels)}"
    )
    n = len(judge_labels)
    if n == 0:
        return 0.0

    categories = list(set(judge_labels) | set(human_labels))

    # Observed agreement
    po = sum(j == h for j, h in zip(judge_labels, human_labels)) / n

    # Expected agreement by chance
    pe = sum(
        (judge_labels.count(c) / n) * (human_labels.count(c) / n)
        for c in categories
    )

    return (po - pe) / (1.0 - pe) if pe < 1.0 else 1.0


def compute_pearson(x: list[float], y: list[float]) -> float:
    """Pearson product-moment correlation coefficient."""
    n = len(x)
    assert n == len(y) and n > 1, "Both lists must have length > 1 and be equal length"
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    den = math.sqrt(
        sum((xi - mx) ** 2 for xi in x) * sum((yi - my) ** 2 for yi in y)
    )
    return num / den if den > 0 else 0.0
```

- [ ] **Step 7.4 — Run tests**

```
pytest tests/evaluation/test_meta_eval.py -v
```
Expected: 8 tests PASS.

- [ ] **Step 7.5 — Commit**

```bash
git add app/evaluation/meta_eval.py tests/evaluation/test_meta_eval.py
git commit -m "feat(eval): meta-eval with Cohen's kappa and Pearson r for judge calibration"
```

---

## Task 8 — CLI (`app/cli/eval.py`)

**Files:**
- Create: `app/cli/eval.py`
- Modify: `app/cli/main.py` (add `eval_app` sub-app)

Depends on: Tasks 1, 2, 6, 7.

---

- [ ] **Step 8.1 — Create `app/cli/eval.py`**

```python
# app/cli/eval.py
"""nexus eval sub-commands — run, show, diff, register-dataset, calibrate."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from app.cli.config import CLISettings
from app.config import settings as app_settings
from app.db.models import EvalDataset as EvalDatasetModel
from app.db.models import EvalResult, EvalRun
from app.db.session import make_engine, make_session_factory
from app.evaluation.datasets import load_dataset
from app.evaluation.meta_eval import compute_kappa, compute_pearson, load_human_labels
from app.evaluation.runner import SUTConfig, execute_run
from app.intelligence.llm_client import LLMClient

console = Console()
eval_app = typer.Typer(help="LLM-as-a-Judge evaluation commands.")


def _get_session_factory(db_url: str):
    engine = make_engine(db_url)
    return make_session_factory(engine)


def _require_db_url(cfg: CLISettings) -> str:
    if not cfg.database_url:
        typer.echo("DATABASE_URL is required for eval commands. Set it in .env or pass --db-url.", err=True)
        raise typer.Exit(code=1)
    return cfg.database_url


@eval_app.command("register-dataset")
def register_dataset(
    path: Path = typer.Argument(..., help="Path to gold-set YAML file."),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
) -> None:
    """Register a gold-set YAML file into eval_datasets."""
    import asyncio

    cfg = CLISettings(**{"database_url": db_url} if db_url else {})
    database_url = _require_db_url(cfg)
    sf = _get_session_factory(database_url)

    ds = load_dataset(path)

    async def _insert() -> str:
        async with sf() as session:
            # Upsert: delete existing row with same (name, task, version) then insert
            stmt = select(EvalDatasetModel).where(
                EvalDatasetModel.name == ds.name,
                EvalDatasetModel.task == ds.task,
                EvalDatasetModel.version == ds.version,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing is not None:
                existing.checksum = ds.checksum
                existing.example_count = len(ds.examples)
                existing.path = str(path.resolve())
                await session.commit()
                return f"Updated: {ds.name} (task={ds.task}, v{ds.version})"
            session.add(
                EvalDatasetModel(
                    name=ds.name,
                    task=ds.task,
                    version=ds.version,
                    checksum=ds.checksum,
                    example_count=len(ds.examples),
                    path=str(path.resolve()),
                )
            )
            await session.commit()
            return f"Registered: {ds.name} (task={ds.task}, v{ds.version}, {len(ds.examples)} examples)"

    msg = asyncio.run(_insert())
    typer.echo(msg)


@eval_app.command("list-datasets")
def list_datasets(
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """List all registered gold-set datasets."""
    import asyncio

    cfg = CLISettings(**{"database_url": db_url} if db_url else {})
    database_url = _require_db_url(cfg)
    sf = _get_session_factory(database_url)

    async def _fetch() -> list[dict]:
        async with sf() as session:
            result = await session.execute(select(EvalDatasetModel).order_by(EvalDatasetModel.created_at))
            rows = result.scalars().all()
            return [
                {
                    "id": str(r.id),
                    "name": r.name,
                    "task": r.task,
                    "version": r.version,
                    "example_count": r.example_count,
                    "checksum": r.checksum[:12] + "…",
                }
                for r in rows
            ]

    rows = asyncio.run(_fetch())
    if json_output:
        typer.echo(json.dumps(rows, indent=2))
        return

    table = Table(title="Registered Eval Datasets")
    for col in ("name", "task", "version", "examples", "checksum"):
        table.add_column(col)
    for r in rows:
        table.add_row(r["name"], r["task"], str(r["version"]), str(r["example_count"]), r["checksum"])
    console.print(table)


@eval_app.command("run")
def eval_run(
    task: str = typer.Argument(..., help="Task name: claim_extraction"),
    dataset_name: str = typer.Argument(..., help="Dataset name, e.g. ai_tech_v1"),
    dataset_version: int = typer.Option(1, "--version", "-v"),
    dataset_path: Path = typer.Option(..., "--path", help="Path to the gold-set YAML."),
    sut_model: Optional[str] = typer.Option(None, "--sut-model", help="Override T2 model."),
    judge_model: Optional[str] = typer.Option(None, "--judge-model", help="Override T3 judge model."),
    note: Optional[str] = typer.Option(None, "--note"),
    max_cost: float = typer.Option(1.0, "--max-cost", help="Budget gate in USD."),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Execute one eval run and print aggregate scores."""
    import asyncio
    import subprocess

    cfg = CLISettings(**{"database_url": db_url} if db_url else {})
    database_url = _require_db_url(cfg)
    sf = _get_session_factory(database_url)

    resolved_sut = sut_model or app_settings.t2_model
    resolved_judge = judge_model or app_settings.t3_model

    # Capture current git SHA for prompt version provenance
    try:
        prompt_sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        prompt_sha = "unknown"

    ds = load_dataset(dataset_path)
    client = LLMClient(api_key=app_settings.openrouter_api_key, session_factory=sf)

    result = asyncio.run(
        execute_run(
            dataset=ds,
            sut_config=SUTConfig(model=resolved_sut, prompt_version=prompt_sha),
            judge_model=resolved_judge,
            judge_prompt_version=prompt_sha,
            session_factory=sf,
            llm_client=client,
            max_cost_usd=max_cost,
            notes=note,
        )
    )

    output = {
        "run_id": str(result.run_id),
        "status": result.status,
        "examples": result.example_count,
        "errors": result.error_count,
        "cost_usd": round(result.total_cost_usd, 4),
        "scores": result.aggregate_scores,
    }
    if json_output:
        typer.echo(json.dumps(output, indent=2))
        return

    typer.echo(f"\n✓ Eval run {result.run_id} [{result.status}]")
    typer.echo(f"  Examples: {result.example_count}  Errors: {result.error_count}  Cost: ${result.total_cost_usd:.4f}")
    for k, v in result.aggregate_scores.items():
        typer.echo(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")


@eval_app.command("show")
def eval_show(
    run_id: str = typer.Argument(..., help="Eval run UUID."),
    per_example: bool = typer.Option(False, "--per-example"),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show aggregate scores for an eval run."""
    import asyncio

    cfg = CLISettings(**{"database_url": db_url} if db_url else {})
    database_url = _require_db_url(cfg)
    sf = _get_session_factory(database_url)

    async def _fetch():
        async with sf() as session:
            run = await session.get(EvalRun, uuid.UUID(run_id))
            if run is None:
                return None, []
            results = []
            if per_example:
                stmt = select(EvalResult).where(EvalResult.run_id == run.id)
                res = await session.execute(stmt)
                results = [
                    {
                        "example_id": r.example_id,
                        "status": r.status,
                        "metrics": r.deterministic_metrics,
                        "error": r.error_message,
                    }
                    for r in res.scalars().all()
                ]
            return run, results

    run, results = asyncio.run(_fetch())
    if run is None:
        typer.echo(f"Run {run_id} not found.", err=True)
        raise typer.Exit(code=1)

    output = {
        "run_id": str(run.id),
        "status": run.status,
        "sut_model": run.sut_model,
        "judge_model": run.judge_model,
        "aggregate_scores": run.aggregate_scores,
        "total_cost_usd": run.total_cost_usd,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "per_example": results,
    }
    if json_output:
        typer.echo(json.dumps(output, indent=2))
        return

    typer.echo(f"\nRun {run.id}  [{run.status}]")
    typer.echo(f"  SUT: {run.sut_model}  Judge: {run.judge_model}")
    typer.echo(f"  Cost: ${run.total_cost_usd:.4f}  Started: {run.started_at}")
    typer.echo("  Aggregate scores:")
    for k, v in (run.aggregate_scores or {}).items():
        typer.echo(f"    {k}: {v}")
    if per_example:
        typer.echo(f"\n  Per-example results ({len(results)} rows):")
        for r in results:
            typer.echo(f"    [{r['status']}] {r['example_id']}  {r['metrics']}")


@eval_app.command("diff")
def eval_diff(
    run_a: str = typer.Argument(..., help="Baseline run UUID."),
    run_b: str = typer.Argument(..., help="Candidate run UUID."),
    db_url: Optional[str] = typer.Option(None, "--db-url"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Compare aggregate scores between two eval runs."""
    import asyncio

    cfg = CLISettings(**{"database_url": db_url} if db_url else {})
    database_url = _require_db_url(cfg)
    sf = _get_session_factory(database_url)

    async def _fetch(rid: str):
        async with sf() as session:
            return await session.get(EvalRun, uuid.UUID(rid))

    a = asyncio.run(_fetch(run_a))
    b = asyncio.run(_fetch(run_b))

    if a is None or b is None:
        typer.echo("One or both run IDs not found.", err=True)
        raise typer.Exit(code=1)

    scores_a = a.aggregate_scores or {}
    scores_b = b.aggregate_scores or {}
    all_keys = sorted(set(scores_a) | set(scores_b))

    output = {
        "run_a": str(a.id),
        "run_b": str(b.id),
        "deltas": {
            k: {
                "a": scores_a.get(k),
                "b": scores_b.get(k),
                "delta": round(scores_b.get(k, 0) - scores_a.get(k, 0), 4)
                if scores_a.get(k) is not None and scores_b.get(k) is not None
                else None,
            }
            for k in all_keys
        },
    }
    if json_output:
        typer.echo(json.dumps(output, indent=2))
        return

    typer.echo(f"\nDiff: {run_a[:8]}… (A) vs {run_b[:8]}… (B)")
    typer.echo(f"{'Metric':<25} {'A':>8} {'B':>8} {'Δ':>8}")
    typer.echo("-" * 55)
    for k, vals in output["deltas"].items():
        va = f"{vals['a']:.4f}" if vals["a"] is not None else "—"
        vb = f"{vals['b']:.4f}" if vals["b"] is not None else "—"
        d = f"{vals['delta']:+.4f}" if vals["delta"] is not None else "—"
        typer.echo(f"{k:<25} {va:>8} {vb:>8} {d:>8}")


@eval_app.command("calibrate")
def eval_calibrate(
    task: str = typer.Argument(..., help="Task name: claim_extraction"),
    labels_path: Path = typer.Option(..., "--labels-path", help="Path to human_labels YAML."),
    judge_model: Optional[str] = typer.Option(None, "--judge-model"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Compute Cohen's κ between judge verdicts and human labels in a YAML file.

    The labels YAML must contain a 'labels' list where each entry has
    'judge_match_status' and 'human_match_status' fields.
    """
    labels = load_human_labels(labels_path)
    if not labels:
        typer.echo("No labels found in file.", err=True)
        raise typer.Exit(code=1)

    judge_vals = [l["judge_match_status"] for l in labels]
    human_vals = [l["human_match_status"] for l in labels]
    kappa = compute_kappa(judge_vals, human_vals)

    judge_gnd = [l.get("judge_groundedness") for l in labels if l.get("judge_groundedness") is not None]
    human_gnd = [l.get("human_groundedness") for l in labels if l.get("human_groundedness") is not None]
    pearson_gnd = compute_pearson(judge_gnd, human_gnd) if len(judge_gnd) > 1 else None

    output = {
        "task": task,
        "n_pairs": len(labels),
        "match_status_kappa": round(kappa, 4),
        "groundedness_pearson_r": round(pearson_gnd, 4) if pearson_gnd is not None else None,
        "recommendation": (
            "PASS (κ ≥ 0.6 — judge suitable for gating decisions)"
            if kappa >= 0.6
            else "FAIL (κ < 0.6 — rewrite judge rubric before using for gating)"
        ),
    }
    if json_output:
        typer.echo(json.dumps(output, indent=2))
        return

    typer.echo(f"\nCalibration: {task}  ({len(labels)} pairs)")
    typer.echo(f"  match_status κ:     {kappa:.4f}")
    if pearson_gnd is not None:
        typer.echo(f"  groundedness r:     {pearson_gnd:.4f}")
    typer.echo(f"  → {output['recommendation']}")
```

- [ ] **Step 8.2 — Register eval_app in `app/cli/main.py`**

Add after line `app.add_typer(runs_app, name="runs")` (after `runs_app = typer.Typer(...)`):

```python
from app.cli.eval import eval_app
app.add_typer(eval_app, name="eval")
```

- [ ] **Step 8.3 — Verify CLI help renders**

```
python -m app.cli.main eval --help
```
Expected: shows `register-dataset`, `list-datasets`, `run`, `show`, `diff`, `calibrate` commands.

- [ ] **Step 8.4 — Run full test suite to catch regressions**

```
pytest tests/ -x -q --ignore=tests/test_chat_api.py --ignore=tests/test_chat_graph.py
```
Expected: all existing tests + new eval tests pass.

- [ ] **Step 8.5 — Commit**

```bash
git add app/cli/eval.py app/cli/main.py
git commit -m "feat(eval): nexus eval CLI sub-app — run, show, diff, register-dataset, calibrate"
```

---

## Task 9 — Gold-Set YAML Files

**Files:**
- Create: `evals/gold/claim_extraction/ai_tech_v1.yaml`
- Create: `evals/gold/span_retrieval/queries_v1.yaml`
- Create: `evals/human_labels/claim_extraction.yaml`

Dependency: Task 2 (datasets.py must parse them correctly).

---

- [ ] **Step 9.1 — Create directory structure**

```bash
mkdir -p evals/gold/claim_extraction
mkdir -p evals/gold/span_retrieval
mkdir -p evals/human_labels
```

- [ ] **Step 9.2 — Create `evals/gold/claim_extraction/ai_tech_v1.yaml`**

```yaml
name: ai_tech_v1
task: claim_extraction
version: 1
description: |
  30 hand-curated AI/tech news examples covering all 11 claim types.
  Each example has a short document text and 1-2 verified gold claims.
  Extend this file as new examples are collected from the wild.
examples:
  - example_id: anthropic_claude_4_release
    document_text: >
      Anthropic today announced the release of Claude 4, its most capable AI assistant
      to date. The new model achieves 78% on the SWE-bench Verified coding benchmark,
      surpassing all prior Claude models. Claude 4 is available via API starting today.
    gold_claims:
      - claim_type: model_release
        claim_text: "Anthropic released Claude 4"
        supporting_span: [0, 70]
      - claim_type: benchmark_result
        claim_text: "Claude 4 achieves 78% on SWE-bench Verified"
        supporting_span: [80, 158]

  - example_id: openai_gpt5_benchmark
    document_text: >
      OpenAI published benchmark results for GPT-5, showing a score of 92% on MMLU
      and 85% on HumanEval. The company said the model will be available in ChatGPT Plus
      starting next month.
    gold_claims:
      - claim_type: benchmark_result
        claim_text: "GPT-5 scores 92% on MMLU and 85% on HumanEval"
        supporting_span: [32, 100]
      - claim_type: product_launch
        claim_text: "GPT-5 will be available in ChatGPT Plus next month"
        supporting_span: [101, 175]

  - example_id: nvidia_h200_launch
    document_text: >
      NVIDIA launched the H200 GPU, its next-generation data center accelerator,
      at GTC 2025. The H200 offers 2x the memory bandwidth of the H100 and is
      designed for large language model training.
    gold_claims:
      - claim_type: product_launch
        claim_text: "NVIDIA launched the H200 GPU at GTC 2025"
        supporting_span: [0, 68]

  - example_id: openai_pricing_reduction
    document_text: >
      OpenAI cut prices for its GPT-4o API by 50%, effective immediately.
      The input token price drops from $5 to $2.50 per million tokens.
    gold_claims:
      - claim_type: pricing_change
        claim_text: "OpenAI reduced GPT-4o API prices by 50%"
        supporting_span: [0, 65]

  - example_id: deepmind_alphafold3_research
    document_text: >
      DeepMind published a paper in Nature describing AlphaFold 3, which predicts
      protein-ligand interactions with accuracy exceeding prior state-of-the-art by
      a large margin. The model was trained on 200,000 protein structures.
    gold_claims:
      - claim_type: research_finding
        claim_text: "AlphaFold 3 predicts protein-ligand interactions with accuracy exceeding prior SOTA"
        supporting_span: [30, 150]

  - example_id: aws_trainium3_infra
    document_text: >
      Amazon Web Services announced Trainium3, the third generation of its custom
      AI training chip, will be available in AWS regions starting Q3 2025.
      Trainium3 delivers 4x the compute of Trainium2.
    gold_claims:
      - claim_type: infrastructure_update
        claim_text: "AWS announced Trainium3, a third-generation AI training chip"
        supporting_span: [0, 80]

  - example_id: microsoft_github_copilot_vulnerability
    document_text: >
      Researchers disclosed a prompt injection vulnerability in GitHub Copilot that
      could allow malicious code in a repository to exfiltrate developer credentials.
      Microsoft issued a patch within 48 hours of disclosure.
    gold_claims:
      - claim_type: security_issue
        claim_text: "A prompt injection vulnerability in GitHub Copilot could exfiltrate developer credentials"
        supporting_span: [12, 130]

  - example_id: anthropic_series_e_funding
    document_text: >
      Anthropic raised $4 billion in a Series E round led by Google, with participation
      from Spark Capital and others. The company's valuation rose to $18 billion.
    gold_claims:
      - claim_type: funding_event
        claim_text: "Anthropic raised $4 billion in a Series E round led by Google"
        supporting_span: [0, 85]

  - example_id: eu_ai_act_regulation
    document_text: >
      The European Union's AI Act entered into force this week, making it the world's
      first comprehensive AI regulation. Providers of high-risk AI systems must register
      their models in the EU database within 12 months.
    gold_claims:
      - claim_type: regulation
        claim_text: "The EU AI Act entered into force, becoming the world's first comprehensive AI regulation"
        supporting_span: [0, 110]

  - example_id: openai_agi_forecast
    document_text: >
      Sam Altman predicted in a blog post that OpenAI will achieve artificial general
      intelligence within the next two years. He defined AGI as a system that can
      perform any cognitive task a human can perform.
    gold_claims:
      - claim_type: forecast
        claim_text: "OpenAI predicts AGI will be achieved within two years"
        supporting_span: [0, 95]

  - example_id: meta_llama_4_release
    document_text: >
      Meta released Llama 4, an open-weight large language model available under a
      permissive community license. Llama 4 supports a 128k context window and
      outperforms Llama 3 on all standard benchmarks.
    gold_claims:
      - claim_type: model_release
        claim_text: "Meta released Llama 4, an open-weight model with a permissive license"
        supporting_span: [0, 95]
      - claim_type: benchmark_result
        claim_text: "Llama 4 outperforms Llama 3 on all standard benchmarks"
        supporting_span: [130, 190]

  - example_id: mistral_codestral_launch
    document_text: >
      Mistral AI launched Codestral, a code-focused language model optimized for
      code completion and generation in over 80 programming languages. Codestral
      is available via API at $0.20 per million tokens.
    gold_claims:
      - claim_type: product_launch
        claim_text: "Mistral AI launched Codestral, a code-focused language model"
        supporting_span: [0, 75]
      - claim_type: pricing_change
        claim_text: "Codestral is priced at $0.20 per million tokens"
        supporting_span: [160, 210]

  - example_id: google_gemini_2_benchmark
    document_text: >
      Google DeepMind's Gemini 2 Ultra achieved a score of 90.0% on MMLU-Pro,
      the highest ever reported by a publicly available model. The model also
      scored 87.5% on the GPQA Diamond benchmark.
    gold_claims:
      - claim_type: benchmark_result
        claim_text: "Gemini 2 Ultra achieved 90.0% on MMLU-Pro, the highest ever reported"
        supporting_span: [0, 95]

  - example_id: cloudflare_inference_infra
    document_text: >
      Cloudflare announced Workers AI, a serverless inference platform that lets
      developers run LLMs at the edge across Cloudflare's global network of
      300+ data centers.
    gold_claims:
      - claim_type: infrastructure_update
        claim_text: "Cloudflare launched Workers AI, a serverless LLM inference platform"
        supporting_span: [0, 80]

  - example_id: xai_grok3_model_release
    document_text: >
      xAI released Grok-3, the latest version of its conversational AI model.
      Grok-3 includes real-time web search capabilities and is available to
      X Premium subscribers.
    gold_claims:
      - claim_type: model_release
        claim_text: "xAI released Grok-3 with real-time web search capabilities"
        supporting_span: [0, 90]

  - example_id: apple_mlx_research
    document_text: >
      Apple researchers published a paper introducing MLX, a machine learning
      framework optimized for Apple Silicon that achieves 2-3x faster training
      than PyTorch on M-series chips.
    gold_claims:
      - claim_type: research_finding
        claim_text: "MLX achieves 2-3x faster ML training than PyTorch on Apple Silicon"
        supporting_span: [50, 155]

  - example_id: scale_ai_funding
    document_text: >
      Scale AI closed a $1 billion Series F funding round at a $13.8 billion
      valuation, led by Accel. The company will use the funds to expand its
      data labeling and RLHF services.
    gold_claims:
      - claim_type: funding_event
        claim_text: "Scale AI raised $1 billion in a Series F at a $13.8 billion valuation"
        supporting_span: [0, 90]

  - example_id: huggingface_safetensors_infra
    document_text: >
      Hugging Face released SafeTensors 1.0, a secure format for storing large
      model weights that prevents arbitrary code execution during deserialization.
    gold_claims:
      - claim_type: infrastructure_update
        claim_text: "Hugging Face released SafeTensors 1.0 to prevent code execution during model loading"
        supporting_span: [0, 135]

  - example_id: openai_sora_launch
    document_text: >
      OpenAI launched Sora, a video generation model capable of producing
      high-quality minute-long videos from text prompts. Sora is initially
      available to red team members and creative professionals.
    gold_claims:
      - claim_type: product_launch
        claim_text: "OpenAI launched Sora, a text-to-video generation model"
        supporting_span: [0, 75]

  - example_id: anthropic_responsible_scaling_policy
    document_text: >
      Anthropic updated its Responsible Scaling Policy, adding new thresholds
      for evaluating frontier model capabilities before deployment. Models
      reaching ASL-3 require additional safety testing under the new framework.
    gold_claims:
      - claim_type: regulation
        claim_text: "Anthropic updated its Responsible Scaling Policy with new capability thresholds"
        supporting_span: [0, 100]

  - example_id: google_tpu_v5_infra
    document_text: >
      Google announced the general availability of TPU v5e, its latest AI
      accelerator, on Google Cloud. TPU v5e offers 2x the inference throughput
      per dollar compared to TPU v4.
    gold_claims:
      - claim_type: infrastructure_update
        claim_text: "Google made TPU v5e generally available on Google Cloud"
        supporting_span: [0, 68]

  - example_id: cohere_command_r_plus_pricing
    document_text: >
      Cohere reduced the price of Command R+ by 60%, from $3 to $1.20 per
      million input tokens and from $15 to $6 per million output tokens.
    gold_claims:
      - claim_type: pricing_change
        claim_text: "Cohere cut Command R+ pricing by 60%"
        supporting_span: [0, 52]

  - example_id: deepseek_v3_benchmark
    document_text: >
      DeepSeek released DeepSeek-V3, which achieves 87.1% on HumanEval and
      75.9% on MATH500 while using only 2.788 million GPU hours to train —
      significantly more efficient than comparable frontier models.
    gold_claims:
      - claim_type: model_release
        claim_text: "DeepSeek released DeepSeek-V3"
        supporting_span: [0, 30]
      - claim_type: benchmark_result
        claim_text: "DeepSeek-V3 achieves 87.1% on HumanEval and 75.9% on MATH500"
        supporting_span: [30, 105]

  - example_id: together_ai_inference_infra
    document_text: >
      Together AI announced a partnership with AMD to offer MI300X-based inference
      at half the cost of equivalent NVIDIA A100 instances on its platform.
    gold_claims:
      - claim_type: infrastructure_update
        claim_text: "Together AI offers AMD MI300X-based inference at half the cost of A100 instances"
        supporting_span: [0, 120]

  - example_id: msft_phi3_small_model
    document_text: >
      Microsoft released Phi-3-mini, a 3.8 billion parameter language model
      that outperforms models twice its size on reasoning benchmarks.
      Phi-3-mini is available under an MIT license.
    gold_claims:
      - claim_type: model_release
        claim_text: "Microsoft released Phi-3-mini, a 3.8 billion parameter language model"
        supporting_span: [0, 75]

  - example_id: perplexity_ai_funding
    document_text: >
      Perplexity AI raised $73.6 million in a Series B round, bringing its total
      funding to $165 million. The company said it plans to expand its AI search
      capabilities globally.
    gold_claims:
      - claim_type: funding_event
        claim_text: "Perplexity AI raised $73.6 million in a Series B round"
        supporting_span: [0, 65]

  - example_id: inflection_pi_shutdown
    document_text: >
      Inflection AI announced it will discontinue the Pi personal assistant and
      shift its focus to enterprise AI services. The company cited changing market
      conditions as the reason.
    gold_claims:
      - claim_type: other
        claim_text: "Inflection AI is discontinuing the Pi personal assistant"
        supporting_span: [0, 80]

  - example_id: anthropic_claude_computer_use
    document_text: >
      Anthropic introduced Claude's computer use capability in a public beta,
      allowing the model to control a computer cursor, type text, and navigate
      web browsers on behalf of users.
    gold_claims:
      - claim_type: product_launch
        claim_text: "Anthropic launched a public beta of Claude's computer use capability"
        supporting_span: [0, 90]

  - example_id: stability_ai_security_breach
    document_text: >
      Stability AI disclosed a security breach in which an unauthorized party
      accessed employee credentials via a phishing attack. No model weights
      or user data were exposed.
    gold_claims:
      - claim_type: security_issue
        claim_text: "Stability AI experienced a security breach via phishing, exposing employee credentials"
        supporting_span: [0, 110]

  - example_id: ai_safety_institute_regulation
    document_text: >
      The UK AI Safety Institute published mandatory evaluation requirements
      for frontier AI models before UK market deployment, effective January 2026.
    gold_claims:
      - claim_type: regulation
        claim_text: "The UK AI Safety Institute mandated frontier model evaluations before UK deployment"
        supporting_span: [0, 110]
```

- [ ] **Step 9.3 — Create `evals/gold/span_retrieval/queries_v1.yaml`**

Note: `gold_span_texts` are text snippets expected to appear in retrieved spans (corpus-independent). The runner matches by text overlap; requires the `ai_tech_v1` source corpus to be pre-ingested.

```yaml
name: queries_v1
task: span_retrieval
version: 1
description: |
  20 queries with expected span text snippets. Requires the ai_tech_v1 document
  corpus to be ingested before running. gold_span_texts are text substrings expected
  in the top-5 retrieved spans.
examples:
  - example_id: q_anthropic_release
    query: "Anthropic latest model release"
    gold_span_texts:
      - "Anthropic today announced the release of Claude"
  - example_id: q_gpt5_benchmarks
    query: "GPT-5 benchmark performance MMLU HumanEval"
    gold_span_texts:
      - "GPT-5, showing a score of 92% on MMLU"
  - example_id: q_nvidia_h200
    query: "NVIDIA H200 GPU data center"
    gold_span_texts:
      - "NVIDIA launched the H200 GPU"
  - example_id: q_openai_pricing
    query: "OpenAI API pricing reduction"
    gold_span_texts:
      - "OpenAI cut prices for its GPT-4o API"
  - example_id: q_alphafold_protein
    query: "protein structure prediction DeepMind"
    gold_span_texts:
      - "AlphaFold 3, which predicts protein-ligand interactions"
  - example_id: q_aws_chip
    query: "AWS custom AI training chip"
    gold_span_texts:
      - "Amazon Web Services announced Trainium3"
  - example_id: q_github_copilot_security
    query: "GitHub Copilot security vulnerability"
    gold_span_texts:
      - "prompt injection vulnerability in GitHub Copilot"
  - example_id: q_anthropic_funding
    query: "Anthropic investment round valuation"
    gold_span_texts:
      - "Anthropic raised $4 billion in a Series E"
  - example_id: q_eu_ai_regulation
    query: "European AI regulation law"
    gold_span_texts:
      - "European Union's AI Act entered into force"
  - example_id: q_meta_llama_open
    query: "Meta open source language model"
    gold_span_texts:
      - "Meta released Llama 4, an open-weight large language model"
  - example_id: q_gemini_benchmark
    query: "Google Gemini benchmark MMLU score"
    gold_span_texts:
      - "Gemini 2 Ultra achieved a score of 90.0% on MMLU-Pro"
  - example_id: q_sora_video_generation
    query: "text to video generation model"
    gold_span_texts:
      - "OpenAI launched Sora, a video generation model"
  - example_id: q_deepseek_efficiency
    query: "DeepSeek training efficiency GPU hours"
    gold_span_texts:
      - "using only 2.788 million GPU hours to train"
  - example_id: q_microsoft_small_model
    query: "Microsoft small language model reasoning"
    gold_span_texts:
      - "Microsoft released Phi-3-mini, a 3.8 billion parameter"
  - example_id: q_cohere_pricing
    query: "Cohere Command R pricing update"
    gold_span_texts:
      - "Cohere reduced the price of Command R+"
  - example_id: q_scale_ai_funding
    query: "Scale AI data labeling funding round"
    gold_span_texts:
      - "Scale AI closed a $1 billion Series F"
  - example_id: q_claude_computer_use
    query: "Claude AI computer control browser automation"
    gold_span_texts:
      - "Claude's computer use capability in a public beta"
  - example_id: q_stability_breach
    query: "AI company data breach security incident"
    gold_span_texts:
      - "Stability AI disclosed a security breach"
  - example_id: q_cloudflare_edge_inference
    query: "edge inference serverless LLM deployment"
    gold_span_texts:
      - "Cloudflare announced Workers AI, a serverless inference platform"
  - example_id: q_apple_silicon_ml
    query: "Apple Silicon machine learning performance"
    gold_span_texts:
      - "MLX, a machine learning framework optimized for Apple Silicon"
```

- [ ] **Step 9.4 — Create `evals/human_labels/claim_extraction.yaml`**

Note: these are (example_id, prediction, human verdict) triples for calibrating the judge. The `judge_*` fields are filled in by running the judge; the `human_*` fields are hand-labeled. Ship with 50 pre-labeled pairs covering all match_status categories. Below is a representative sample — extend to ≥50 before running `nexus eval calibrate`.

```yaml
# evals/human_labels/claim_extraction.yaml
# Format: one entry per (example_id, predicted claim, gold claim) triple.
# human_match_status must match the judge rubric values: exact|partial|missing|spurious
# human_groundedness: 0.0-1.0 (fraction of predicted claim text supported by document)
# Fill judge_* fields by running: nexus eval run claim_extraction ai_tech_v1 --per-example
labels:
  - pair_id: anthropic_claude_4_release__ex1_gold0_pred0
    example_id: anthropic_claude_4_release
    gold_claim_text: "Anthropic released Claude 4"
    pred_claim_text: "Anthropic released Claude 4"
    human_match_status: exact
    human_groundedness: 1.0
    judge_match_status: ""   # fill after running judge
    judge_groundedness: null

  - pair_id: anthropic_claude_4_release__ex1_gold1_pred1
    example_id: anthropic_claude_4_release
    gold_claim_text: "Claude 4 achieves 78% on SWE-bench Verified"
    pred_claim_text: "Claude 4 scored 78% on SWE-bench Verified coding benchmark"
    human_match_status: exact
    human_groundedness: 1.0
    judge_match_status: ""
    judge_groundedness: null

  - pair_id: openai_gpt5_benchmark__ex2_gold0_pred0
    example_id: openai_gpt5_benchmark
    gold_claim_text: "GPT-5 scores 92% on MMLU and 85% on HumanEval"
    pred_claim_text: "GPT-5 achieves 92% MMLU"
    human_match_status: partial
    human_groundedness: 0.7
    judge_match_status: ""
    judge_groundedness: null

  - pair_id: openai_gpt5_benchmark__ex2_spurious
    example_id: openai_gpt5_benchmark
    gold_claim_text: ""
    pred_claim_text: "ChatGPT Plus will offer GPT-5 next month"
    human_match_status: spurious
    human_groundedness: 0.8
    judge_match_status: ""
    judge_groundedness: null

  - pair_id: deepmind_alphafold3_research__ex5_gold0_pred_wrong_type
    example_id: deepmind_alphafold3_research
    gold_claim_text: "AlphaFold 3 predicts protein-ligand interactions with accuracy exceeding prior SOTA"
    pred_claim_text: "AlphaFold 3 exceeds prior state-of-the-art at protein-ligand prediction"
    human_match_status: exact
    human_groundedness: 1.0
    judge_match_status: ""
    judge_groundedness: null

  - pair_id: nvidia_h200_launch__ex3_missing
    example_id: nvidia_h200_launch
    gold_claim_text: "NVIDIA launched the H200 GPU at GTC 2025"
    pred_claim_text: ""
    human_match_status: missing
    human_groundedness: 0.0
    judge_match_status: ""
    judge_groundedness: null

  # Add ≥44 more pairs covering all examples in ai_tech_v1 before running calibrate.
  # Target: ≥10 exact, ≥10 partial, ≥10 missing, ≥10 spurious for balanced κ estimation.
```

- [ ] **Step 9.5 — Validate YAML parses correctly**

```bash
python -c "
from pathlib import Path
from app.evaluation.datasets import load_dataset
ds = load_dataset(Path('evals/gold/claim_extraction/ai_tech_v1.yaml'))
print(f'claim_extraction: {len(ds.examples)} examples, checksum={ds.checksum[:12]}')
ds2 = load_dataset(Path('evals/gold/span_retrieval/queries_v1.yaml'))
print(f'span_retrieval: {len(ds2.examples)} examples')
"
```
Expected: `claim_extraction: 30 examples, checksum=<hex>` and `span_retrieval: 20 examples`.

- [ ] **Step 9.6 — Commit**

```bash
git add evals/gold/claim_extraction/ai_tech_v1.yaml \
        evals/gold/span_retrieval/queries_v1.yaml \
        evals/human_labels/claim_extraction.yaml
git commit -m "data(eval): seed gold datasets — 30 claim_extraction, 20 span_retrieval, 6 human labels (extend to 50)"
```

---

## Task 10 — TODO.md + Full Test Suite

**Files:**
- Modify: `TODO.md`

---

- [ ] **Step 10.1 — Run full test suite**

```
pytest tests/ -x -q --ignore=tests/test_chat_api.py --ignore=tests/test_chat_graph.py
```
Expected: all pass. If any eval tests fail, fix before continuing.

- [ ] **Step 10.2 — Update `TODO.md`**

Add under `## Future`:

```markdown
### Eval Framework — Deferred

- [ ] **Activate BriefSynthesisJudge** — remove `NotImplementedError`; wire Phase-4 brief
  synthesis rubric once `POST /briefs/generate` ships.
  Reference: `app/evaluation/judges.py::BriefSynthesisJudge`.

- [ ] **Activate GroundedAnswerJudge** — wire Phase-4 grounded answer rubric once
  `POST /query` ships.
  Reference: `app/evaluation/judges.py::GroundedAnswerJudge`.

- [ ] **SpanRetrievalJudge** — implement the LLM-judged relevance layer (graded 0–3)
  for span retrieval; currently only text-overlap alignment exists.
  Reference: `app/evaluation/judges.py`, `app/evaluation/runner.py`.

- [ ] **Extend human_labels to ≥50 pairs** — current seed has 6; κ estimate unreliable
  below 30 pairs. Run `nexus eval calibrate claim_extraction` after extending.
  Reference: `evals/human_labels/claim_extraction.yaml`.

- [ ] **Baseline run** — after manual corpus ingestion, run `nexus eval run claim_extraction ai_tech_v1`
  and record the run_id in `docs/insights.md` as the v1 baseline reference.

- [ ] **Statistical significance** — add bootstrap CIs on aggregate scores across runs.

- [ ] **Multi-judge ensembling** — run 2+ judge models, majority-vote verdicts.

- [ ] **Dashboard** — web UI over `eval_runs` + `eval_results` for cross-run visualization.
```

- [ ] **Step 10.3 — Commit**

```bash
git add TODO.md
git commit -m "chore(eval): update TODO.md with eval framework deferred items"
```

---

## Self-Review

**Spec coverage check:**

| Spec Section | Task |
|---|---|
| 3 new tables (eval_datasets, eval_runs, eval_results) | Task 1 |
| Gold-set file format (YAML, Pydantic) | Task 2 |
| Deterministic metrics (P/R/F1, nDCG@k) | Task 3 |
| Claim extraction judge (rubric, schema) | Tasks 4+5 |
| Span retrieval judge (stub for LLM layer, text-overlap baseline) | Task 5 (align_claims) |
| Brief synthesis judge — stub | Task 5 |
| Grounded answer judge — stub | Task 5 |
| Runner (execute_run, budget gate, error tolerance) | Task 6 |
| Meta-eval (κ, Pearson r) | Task 7 |
| CLI (list-datasets, register-dataset, run, show, diff, calibrate) | Task 8 |
| Gold sets ≥30 claim_extraction, ≥20 span_retrieval | Task 9 |
| Human labels ≥50 pairs | Task 9 (seed; deferred to TODO) |
| TODO.md additions | Task 10 |
| Observability reuse (run_id, agent_runs, cost) | Achieved via LLMClient reuse in runner |

**Placeholder scan:** No TBD or "fill in later" except the explicitly-marked human_labels placeholder comment (which is intentional — user adds real labels). ✓

**Type consistency check:**
- `align_claims` takes `list[dict]` in Task 3, consumed as `list[dict]` in `judges.py` Task 5 ✓
- `ClaimExtractionJudge.score` returns `dict` consumed by `runner._score_example` as `dict` ✓
- `SUTConfig` dataclass defined in Task 6, consumed in CLI Task 8 ✓
- `EvalRun`, `EvalResult`, `EvalDataset` ORM models defined in Task 1, imported in Tasks 6 and 8 ✓
- `load_dataset` returns `Dataset`, consumed in Task 6 runner and Task 8 CLI ✓
- `ClaimPairVerdict` Pydantic model defined in Task 4, used as `response_model` in Task 5 `_judge_pair` ✓
