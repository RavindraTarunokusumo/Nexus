"""T1 claim extractor — local GLiNER2 (no LLM, CPU inference).

Per-sentence pipeline:
  1. is_claim?            classify_text yes/no   — drops framing/opinion sentences
  2. claim_type           classify_text over the 23 dotted types
  3. entities             extract_entities over a fixed vocab

claim_text is the source sentence verbatim — encoder models cannot rewrite,
and quoting from source guarantees groundedness=1.0.

The model loads once per process and is cached as a module-level singleton.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Any

from app.intelligence.canonicalization import normalize_entity
from app.intelligence.taxonomy import ALL_TYPES

# Entity types we ask GLiNER to look for. Covers most AI-news vocab.
_ENTITY_VOCAB = [
    "organization",
    "person",
    "model",
    "product",
    "date",
    "metric",
    "money",
    "location",
    "law",
]

# Sentence-role classes for Option A — multi-class semantic labels.
# Replaces the ambiguous binary `is_claim` with discriminative roles.
_SENTENCE_ROLES = [
    "atomic_fact",   # a verifiable factual proposition
    "framing",       # commentary or interpretation ("marking a milestone")
    "opinion",       # subjective assertion ("experts say")
    "background",    # orientation context, not the main point
]

# Only sentences whose role is `atomic_fact` become extracted claims.
_KEEP_ROLES = {"atomic_fact"}

# Entity types that strongly indicate a factual claim — used by the NER-based
# filter (sentence is a claim if it contains ≥1 entity of these types).
_CLAIM_INDICATOR_ENTITIES = {
    "organization",
    "person",
    "model",
    "product",
    "law",
    "money",
    "metric",
}


_model = None
_lock = threading.Lock()


def _get_model() -> Any:
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from gliner2 import GLiNER2

                _model = GLiNER2.from_pretrained("fastino/gliner2-base-v1")
    return _model


def split_sentences(text: str) -> list[str]:
    """Same conservative splitter as the LLM sentence-bounded path."""
    t = re.sub(r"\s+", " ", text).strip()
    if not t:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(\[])", t)
    return [p.strip() for p in parts if p.strip()]


@dataclass
class GLiNERClaim:
    """Mirror of ExtractedClaim, populated from GLiNER calls.

    Stores both raw and canonical entities. The eval framework currently looks
    at `entities` only; we expose the canonical (alias-normalized) list there
    so downstream consumers see deduplicated entity strings. `raw_entities`
    preserves the original spans for debugging.
    """

    claim_text: str
    claim_type: str
    entities: list[str] = field(default_factory=list)         # canonical
    raw_entities: list[str] = field(default_factory=list)     # as extracted
    topics: list[str] = field(default_factory=list)
    confidence: float = 0.0  # filled from classifier softmax when available
    rationale: str = ""
    sentence_role: str = "atomic_fact"

    def model_dump(self) -> dict:
        return {
            "claim_text": self.claim_text,
            "claim_type": self.claim_type,
            "entities": self.entities,
            "raw_entities": self.raw_entities,
            "topics": self.topics,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "sentence_role": self.sentence_role,
        }


def _classify_label(result: Any, key: str) -> tuple[str, float]:
    """Pull (label, confidence) from a classify_text result.

    GLiNER2 returns either a dict {key: label} or {key: {label: prob, ...}}
    depending on configuration. Handle both shapes.
    """
    raw = result.get(key) if isinstance(result, dict) else None
    if isinstance(raw, str):
        return raw, 0.0  # no probabilities returned
    if isinstance(raw, dict):
        if not raw:
            return "", 0.0
        # Pick max-probability label.
        best = max(raw.items(), key=lambda kv: float(kv[1]))
        return best[0], float(best[1])
    if isinstance(raw, list) and raw:
        # Some versions return [{"label": ..., "score": ...}]
        if isinstance(raw[0], dict):
            best = max(raw, key=lambda d: float(d.get("score", 0.0)))
            return str(best.get("label", "")), float(best.get("score", 0.0))
        return str(raw[0]), 0.0
    return "", 0.0


def _flatten_entities(result: Any) -> list[str]:
    ents = result.get("entities") if isinstance(result, dict) else None
    if not isinstance(ents, dict):
        return []
    seen: list[str] = []
    for v in ents.values():
        if isinstance(v, list):
            for e in v:
                if isinstance(e, str) and e not in seen:
                    seen.append(e)
    return seen


def extract_claims(document_text: str) -> list[GLiNERClaim]:
    """Per-sentence T1 extraction pipeline.

    Steps per sentence:
      1. sentence_role classification (atomic_fact / framing / opinion / background)
      2. drop sentence if role not in _KEEP_ROLES
      3. claim_type classification (24 dotted types)
      4. extract_entities with the AI-news vocab
      5. canonicalize entities via the alias table in canonicalization.py
    """
    model = _get_model()
    out: list[GLiNERClaim] = []
    for sent in split_sentences(document_text):
        # Permissive filter — binary is_claim. We extract liberally at storage
        # time and let retrieval-time relevance scoring decide what's salient.
        is_claim_res = model.classify_text(sent, {"is_claim": ["yes", "no"]})
        is_claim_label, _ = _classify_label(is_claim_res, "is_claim")
        if is_claim_label != "yes":
            continue

        # Type classification — 24-way zero-shot.
        type_res = model.classify_text(sent, {"claim_type": list(ALL_TYPES)})
        claim_type, type_conf = _classify_label(type_res, "claim_type")

        # Entity extraction + canonicalization.
        ents = model.extract_entities(sent, _ENTITY_VOCAB)
        raw_entities = _flatten_entities(ents)
        seen: list[str] = []
        for e in raw_entities:
            c = normalize_entity(e)
            if c and c not in seen:
                seen.append(c)
        canonical_entities = seen

        out.append(
            GLiNERClaim(
                claim_text=sent,
                claim_type=claim_type if claim_type in ALL_TYPES else "release.product",
                entities=canonical_entities,
                raw_entities=raw_entities,
                topics=[],
                confidence=round(type_conf, 3) if type_conf else 0.0,
                rationale=f"GLiNER2 is_claim=yes; entities={raw_entities[:3]}",
                sentence_role="atomic_fact",
            )
        )
    return out


def classify_all_sentence_roles(document_text: str) -> list[tuple[str, str, float]]:
    """Diagnostic helper — return (sentence, role, conf) for every sentence.

    Used by scripts/sentence_role_stats.py to break down what GLiNER thinks
    the role distribution is in a corpus.
    """
    model = _get_model()
    rows: list[tuple[str, str, float]] = []
    for sent in split_sentences(document_text):
        res = model.classify_text(sent, {"sentence_role": _SENTENCE_ROLES})
        label, conf = _classify_label(res, "sentence_role")
        rows.append((sent, label, conf))
    return rows
