from __future__ import annotations

from app.intelligence.chat import _assemble_within_budget, estimate_tokens


def _c(text: str) -> dict:
    return {"text": text}


def test_estimate_tokens_ceil_div_4() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2


def test_assemble_none_budget_is_flat_top_k() -> None:
    scored = [(_c("x" * 400), 0.9), (_c("y" * 400), 0.8), (_c("z" * 400), 0.7)]
    assert _assemble_within_budget(scored, top_k=2, token_budget=None) == scored[:2]


def test_assemble_stops_when_budget_exceeded() -> None:
    # each block 400 chars -> 100 tokens; budget 250 fits two (200), not three (300)
    scored = [(_c("a" * 400), 0.9), (_c("b" * 400), 0.8), (_c("c" * 400), 0.7)]
    out = _assemble_within_budget(scored, top_k=10, token_budget=250)
    assert [s for _, s in out] == [0.9, 0.8]


def test_assemble_respects_top_k_cap_under_budget() -> None:
    scored = [(_c("a" * 4), 0.9), (_c("b" * 4), 0.8), (_c("c" * 4), 0.7)]
    out = _assemble_within_budget(scored, top_k=2, token_budget=100000)
    assert len(out) == 2


def test_assemble_always_includes_first_even_if_over_budget() -> None:
    scored = [(_c("a" * 4000), 0.9), (_c("b" * 4), 0.8)]  # first ~1000 tokens
    out = _assemble_within_budget(scored, top_k=10, token_budget=10)
    assert [s for _, s in out] == [0.9]
