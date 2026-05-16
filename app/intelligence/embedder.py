"""384-dim L2-normalised sentence embeddings via BAAI/bge-small-en-v1.5.

sentence-transformers is imported lazily inside __init__ so the module can be
imported in test environments where the library is unavailable; the real model
is only loaded when Embedder() is instantiated.
"""

_MODEL_NAME = "BAAI/bge-small-en-v1.5"


class Embedder:
    def __init__(self, model_name: str = _MODEL_NAME) -> None:
        from sentence_transformers import SentenceTransformer  # lazy import

        self._model = SentenceTransformer(model_name, device="cpu")

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return L2-normalised 384-dim vectors for each text."""
        if not texts:
            return []
        vecs = self._model.encode(texts, normalize_embeddings=True)
        return vecs.tolist()

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]
