"""L2-normalised sentence embeddings via a configurable sentence-transformers model.

Default BAAI/bge-small-en-v1.5 (384-dim, no prompts). Qwen3-Embedding-* is also
supported: it carries asymmetric 'query'/'document' prompts (applied automatically
to embed_one vs embed) and is truncated to the 384-dim vector column via MRL
(settings.t1_truncate_dim). Models without prompts encode plain, so bge behaviour
is unchanged.

sentence-transformers is imported lazily inside __init__ so the module can be
imported in test environments where the library is unavailable; the real model
is only loaded when Embedder() is instantiated.
"""

from app.config import settings

_MODEL_NAME = "BAAI/bge-small-en-v1.5"


class Embedder:
    def __init__(self, model_name: str = _MODEL_NAME, truncate_dim: int | None = None) -> None:
        from sentence_transformers import SentenceTransformer  # lazy import

        dim = truncate_dim if truncate_dim is not None else (settings.t1_truncate_dim or None)
        self._model = SentenceTransformer(model_name, device="cpu", truncate_dim=dim)
        prompts = getattr(self._model, "prompts", None) or {}
        self._doc_prompt = "document" if "document" in prompts else None
        self._query_prompt = "query" if "query" in prompts else None

    def _encode(self, texts: list[str], prompt_name: str | None) -> list[list[float]]:
        kwargs: dict[str, object] = {"normalize_embeddings": True}
        if prompt_name is not None:
            kwargs["prompt_name"] = prompt_name
        return self._model.encode(texts, **kwargs).tolist()

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return L2-normalised vectors for documents (ingest side)."""
        if not texts:
            return []
        return self._encode(texts, self._doc_prompt)

    def embed_one(self, text: str) -> list[float]:
        """Return the L2-normalised vector for a query (retrieval side)."""
        return self._encode([text], self._query_prompt)[0]
