"""Unit tests for chunk_document."""

from app.ingestion.chunker import _CHUNK_TOKENS, _OVERLAP_TOKENS, chunk_document


def test_empty_text_returns_empty():
    assert chunk_document("") == []


def test_whitespace_only_returns_empty():
    assert chunk_document("   \n\t  ") == []


def test_short_text_single_span():
    spans = chunk_document("hello world this is a short document")
    assert len(spans) == 1
    assert spans[0]["span_index"] == 0
    assert spans[0]["token_count"] <= _CHUNK_TOKENS


def test_long_text_multiple_spans():
    # 700 words → 2 spans with 500-word step
    text = "word " * 700
    spans = chunk_document(text)
    assert len(spans) >= 2


def test_spans_have_overlap():
    # The last _OVERLAP_TOKENS words of span N appear at the start of span N+1.
    text = "word " * 700
    spans = chunk_document(text)
    assert len(spans) >= 2
    words_0 = spans[0]["text"].split()
    words_1 = spans[1]["text"].split()
    overlap = _OVERLAP_TOKENS
    # Tail of span 0 == head of span 1
    assert words_0[-overlap:] == words_1[:overlap]


def test_metadata_propagated():
    meta = {"source": "test", "doc_id": "abc"}
    spans = chunk_document("hello world foo bar", metadata=meta)
    assert len(spans) == 1
    assert spans[0]["metadata_json"]["source"] == "test"
    assert spans[0]["metadata_json"]["doc_id"] == "abc"
    # chunk_start_token is always added
    assert "chunk_start_token" in spans[0]["metadata_json"]


def test_span_index_sequential():
    text = "word " * 1200
    spans = chunk_document(text)
    for i, span in enumerate(spans):
        assert span["span_index"] == i
