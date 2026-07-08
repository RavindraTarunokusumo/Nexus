from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from app.config import settings

_GLINER_LABELS = [
    "person",
    "organization",
    "location",
    "activity",
    "object",
    "event",
    "date",
]
_ner_backend: Any | None = None
_ner_backend_name: str | None = None


def _normalize_entity(raw: str) -> str | None:
    collapsed = re.sub(r"\s+", " ", raw.strip().lower())
    if len(collapsed) <= 2:
        return None
    return collapsed


def _normalize_entities(entities: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    result: list[str] = []
    for raw in entities:
        norm = _normalize_entity(raw)
        if norm is not None and norm not in seen:
            seen[norm] = None
            result.append(norm)
    return result


def _load_gliner() -> Any:
    from gliner import GLiNER

    return GLiNER.from_pretrained(settings.sentence_window_ner_model)


def _load_spacy() -> Any:
    import spacy

    return spacy.load("en_core_web_sm")


def _get_ner_backend() -> tuple[Any, str]:
    global _ner_backend, _ner_backend_name
    if _ner_backend is not None and _ner_backend_name is not None:
        return _ner_backend, _ner_backend_name
    try:
        _ner_backend = _load_gliner()
        _ner_backend_name = "gliner"
        return _ner_backend, _ner_backend_name
    except Exception:  # noqa: S110 - spaCy fallback when GLiNER unavailable
        pass
    try:
        _ner_backend = _load_spacy()
        _ner_backend_name = "spacy"
        return _ner_backend, _ner_backend_name
    except Exception as exc:
        raise RuntimeError(
            "No NER backend available (GLiNER and spaCy both failed to load)"
        ) from exc


def _entity_texts(predictions: list[dict[str, Any]]) -> list[str]:
    return [str(pred["text"]) for pred in predictions]


def _extract_with_gliner(model: Any, texts: Sequence[str]) -> list[list[str]]:
    batch_predict = getattr(model, "batch_predict_entities", None)
    if batch_predict is not None:
        predictions = batch_predict(list(texts), _GLINER_LABELS)
        return [_normalize_entities(_entity_texts(preds)) for preds in predictions]
    return [
        _normalize_entities(_entity_texts(model.predict_entities(text, _GLINER_LABELS)))
        for text in texts
    ]


def _extract_with_spacy(nlp: Any, texts: Sequence[str]) -> list[list[str]]:
    return [_normalize_entities([ent.text for ent in doc.ents]) for doc in nlp.pipe(texts)]


def extract_entities(texts: Sequence[str]) -> list[list[str]]:
    if not texts:
        return []
    backend, name = _get_ner_backend()
    if name == "gliner":
        return _extract_with_gliner(backend, texts)
    return _extract_with_spacy(backend, texts)
