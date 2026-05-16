"""Unit tests for the real Embedder (requires sentence-transformers + model download).

Run separately: pytest tests/test_embedder.py
Excluded from the standard CI run: pytest tests/ --ignore=tests/test_embedder.py
"""
import math

import numpy as np
import pytest

from app.intelligence.embedder import Embedder


@pytest.fixture(scope="module")
def embedder():
    return Embedder()


def test_embed_shape(embedder):
    vecs = embedder.embed(["hello world"])
    assert len(vecs) == 1
    assert len(vecs[0]) == 384


def test_embed_l2_normalised(embedder):
    vecs = embedder.embed(["normalisation check"])
    norm = math.sqrt(sum(x * x for x in vecs[0]))
    assert abs(norm - 1.0) < 1e-5


def test_embed_batch(embedder):
    texts = ["first sentence", "second sentence", "third sentence"]
    vecs = embedder.embed(texts)
    assert len(vecs) == 3
    assert all(len(v) == 384 for v in vecs)


def test_embed_empty_list(embedder):
    assert embedder.embed([]) == []
