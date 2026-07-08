from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.intelligence import entities


class _FakeGliner:
    def batch_predict_entities(
        self, texts: list[str], labels: list[str]
    ) -> list[list[dict[str, str]]]:
        del labels
        return [
            [
                {"text": "  John  "},
                {"text": "homeless shelter"},
                {"text": "it"},
                {"text": "john"},
            ]
            for _ in texts
        ]


class _FakeSpacy:
    def pipe(self, texts: list[str]):
        for text in texts:
            yield SimpleNamespace(ents=[SimpleNamespace(text=f"  {text}  ")])


def test_extract_entities_normalizes_dedups_and_drops_short_tokens(monkeypatch) -> None:
    monkeypatch.setattr(entities, "_ner_backend", _FakeGliner())
    monkeypatch.setattr(entities, "_ner_backend_name", "gliner")

    result = entities.extract_entities(["Maria volunteered at the shelter."])

    assert result == [["john", "homeless shelter"]]


def test_extract_entities_empty_input_returns_empty(monkeypatch) -> None:
    monkeypatch.setattr(entities, "_ner_backend", _FakeGliner())
    monkeypatch.setattr(entities, "_ner_backend_name", "gliner")

    assert entities.extract_entities([]) == []


def test_extract_entities_raises_when_no_backend_available(monkeypatch) -> None:
    monkeypatch.setattr(entities, "_ner_backend", None)
    monkeypatch.setattr(entities, "_ner_backend_name", None)
    monkeypatch.setattr(entities, "_load_gliner", lambda: (_ for _ in ()).throw(ImportError()))
    monkeypatch.setattr(entities, "_load_spacy", lambda: (_ for _ in ()).throw(ImportError()))

    with pytest.raises(RuntimeError, match="No NER backend available"):
        entities.extract_entities(["test sentence"])


def test_extract_entities_spacy_path_normalizes(monkeypatch) -> None:
    monkeypatch.setattr(entities, "_ner_backend", _FakeSpacy())
    monkeypatch.setattr(entities, "_ner_backend_name", "spacy")

    result = entities.extract_entities(["John Smith"])

    assert result == [["john smith"]]
