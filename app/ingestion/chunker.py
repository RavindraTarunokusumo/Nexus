"""Span chunking: overlapping sliding-window splits measured in whitespace tokens."""

## Comment: This is a simple implementation that splits on whitespace and counts tokens as words. For more accuracy, especially with languages where tokenization is not whitespace-based, consider integrating a proper tokenizer (e.g., from Hugging Face's tokenizers library) to count tokens and split accordingly.
_CHUNK_TOKENS = 600
_OVERLAP_TOKENS = 100
_STEP = _CHUNK_TOKENS - _OVERLAP_TOKENS  # 500


def chunk_document(text: str, metadata: dict | None = None) -> list[dict]:
    """Split *text* into overlapping 600-word windows (100-word overlap).

    Returns a list of span dicts with keys:
      span_index, text, token_count, metadata_json
    Returns [] for empty or whitespace-only input.
    """
    if not text or not text.strip():
        return []

    words = text.split()
    if not words:
        return []

    metadata = metadata or {}
    spans: list[dict] = []

    for i, start in enumerate(range(0, len(words), _STEP)):
        # Skip trailing windows whose content is entirely within the overlap of the
        # previous span (i.e., no new content beyond the overlap boundary).
        if start > 0 and len(words) - start <= _OVERLAP_TOKENS:
            break
        window = words[start : start + _CHUNK_TOKENS]
        if not window:
            break
        chunk_text = " ".join(window)
        spans.append(
            {
                "span_index": i,
                "text": chunk_text,
                "token_count": len(window), ## Comment: this is a rough proxy for token count; for more accuracy, consider using a tokenizer.
                "metadata_json": {**metadata, "chunk_start_token": start},
            }
        )

    return spans
