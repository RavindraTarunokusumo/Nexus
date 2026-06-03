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
    semantic_object_extraction = "semantic_object_extraction"
    span_retrieval = "span_retrieval"


class GoldSemanticObject(BaseModel):
    """Gold-set shape for one v0.7 semantic object.

    Mirrors `app.intelligence.llm_client.SemanticObject` but loosened for
    hand-authored YAML — facets/epistemic are optional and only the fields
    the judge needs are required.
    """

    text: str
    core_type: str
    domain_family: str
    domain_object_type: str
    function: str | None = None
    facets: dict[str, list[str]] = Field(default_factory=dict)
    epistemic: dict = Field(default_factory=dict)
    salience: float = Field(default=0.5, ge=0.0, le=1.0)
    mvp_claim_type: str
    supporting_span: tuple[int, int] | None = None
    notes: str | None = None


class SemanticObjectExtractionExample(BaseModel):
    example_id: str
    document_text: str | None = None
    document_id: str | None = None
    source_type: str | None = None
    gold_objects: list[GoldSemanticObject]
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
    examples: list[Union[SemanticObjectExtractionExample, SpanRetrievalExample]]
    checksum: str = ""


def load_dataset(path: Path) -> Dataset:
    """Load and validate a gold-set YAML file.

    Raises FileNotFoundError if path does not exist.
    Raises ValueError if task is unknown.
    Computes SHA-256 checksum of the raw file bytes.
    """
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
    examples: list[SemanticObjectExtractionExample | SpanRetrievalExample] = []

    for ex in raw_examples:
        if task == EvalTask.semantic_object_extraction:
            examples.append(SemanticObjectExtractionExample.model_validate(ex))
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
