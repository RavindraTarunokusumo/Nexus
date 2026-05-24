# app/evaluation/datasets.py
"""Gold-set dataset loading and Pydantic schemas."""

from __future__ import annotations

import hashlib
from enum import Enum
from pathlib import Path
from typing import Union

import yaml
from pydantic import BaseModel, Field


class EvalTask(str, Enum):
    claim_extraction = "claim_extraction"
    span_retrieval = "span_retrieval"


class GoldClaim(BaseModel):
    claim_type: str
    claim_text: str
    supporting_span: tuple[int, int] | None = None
    notes: str | None = None


class ClaimExtractionExample(BaseModel):
    example_id: str
    document_text: str | None = None
    document_id: str | None = None
    gold_claims: list[GoldClaim]
    notes: str | None = None


class SpanRetrievalExample(BaseModel):
    example_id: str
    query: str
    gold_span_texts: list[str]
    negative_span_texts: list[str] = Field(default_factory=list)
    notes: str | None = None


class Dataset(BaseModel):
    name: str
    task: EvalTask
    version: int
    description: str | None = None
    examples: list[Union[ClaimExtractionExample, SpanRetrievalExample]]
    checksum: str = ""


def load_dataset(path: Path) -> Dataset:
    """Load and validate a gold-set YAML file.

    Raises FileNotFoundError if path does not exist.
    Raises ValueError if task is unknown.
    Computes SHA-256 checksum of the raw file bytes.
    """
    if not path.exists():
        raise FileNotFoundError(f"Dataset file not found: {path}")

    raw = path.read_bytes()
    checksum = hashlib.sha256(raw).hexdigest()

    data = yaml.safe_load(raw.decode("utf-8"))

    task_str = data.get("task", "")
    try:
        task = EvalTask(task_str)
    except ValueError:
        raise ValueError(
            f"Unknown eval task '{task_str}'. Valid tasks: {[t.value for t in EvalTask]}"
        ) from None

    raw_examples = data.get("examples") or []
    examples: list[ClaimExtractionExample | SpanRetrievalExample] = []

    for ex in raw_examples:
        if task == EvalTask.claim_extraction:
            examples.append(ClaimExtractionExample.model_validate(ex))
        elif task == EvalTask.span_retrieval:
            examples.append(SpanRetrievalExample.model_validate(ex))

    return Dataset(
        name=data["name"],
        task=task,
        version=data["version"],
        description=data.get("description"),
        examples=examples,
        checksum=checksum,
    )
