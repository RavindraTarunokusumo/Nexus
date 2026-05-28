"""Quantify the sentence-vs-claim ratio at span/document level.

Three perspectives:
  (A) Gold annotation: how many gold claims per example vs how many sentences.
  (B) GLiNER's is_claim classifier: of all sentences in v3, how many did it
      classify as claim-bearing?
  (C) LLM extractor's emission: of all sentences in v3, how many claims did
      the best-stack LLM run emit?

Comparing the three reveals what each agent thinks the claim density is.
"""

from __future__ import annotations

import asyncio
import re
import sys
import uuid
from collections import Counter

import yaml
from sqlalchemy import select

from app.db.models import EvalResult
from app.db.session import make_engine, make_session_factory

GOLD_PATH = "evals/gold/claim_extraction/ai_tech_v3.yaml"
LLM_RUN_ID = uuid.UUID("6ca8abd3-8cc9-43b2-95ae-3583bc50fabd")  # taxonomy v2 + cross-family judge
GLINER_RUN_ID = uuid.UUID("1211d83e-72ee-4af2-9ede-b6beb3607749")  # gliner SUT


def split_sentences(text: str) -> list[str]:
    t = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(\[])", t)
    return [p.strip() for p in parts if p.strip()]


async def main() -> int:
    sf = make_session_factory(make_engine("postgresql+asyncpg://nexus:nexus@localhost:55432/nexus"))

    with open(GOLD_PATH, "r", encoding="utf-8") as f:
        ds = yaml.safe_load(f)

    total_sentences = 0
    total_gold_claims = 0
    per_example_sentences: dict[str, int] = {}
    per_example_gold: dict[str, int] = {}

    for ex in ds["examples"]:
        sents = split_sentences(ex["document_text"])
        n_sents = len(sents)
        n_gold = len(ex["gold_claims"])
        per_example_sentences[ex["example_id"]] = n_sents
        per_example_gold[ex["example_id"]] = n_gold
        total_sentences += n_sents
        total_gold_claims += n_gold

    async with sf() as session:
        # LLM run
        res = await session.execute(select(EvalResult).where(EvalResult.run_id == LLM_RUN_ID))
        llm_rows = res.scalars().all()
        # GLiNER run
        res = await session.execute(select(EvalResult).where(EvalResult.run_id == GLINER_RUN_ID))
        gliner_rows = res.scalars().all()

    llm_emit_total = 0
    gliner_emit_total = 0
    for r in llm_rows:
        sut = r.sut_output or {}
        llm_emit_total += len((sut.get("claims") or []))
    for r in gliner_rows:
        sut = r.sut_output or {}
        gliner_emit_total += len((sut.get("claims") or []))

    n_examples = len(ds["examples"])

    print("=" * 70)
    print("  Sentence-vs-claim ratio across ai_tech_v3 (45 examples)")
    print("=" * 70)

    print(f"\nTotal sentences in corpus:         {total_sentences}")
    print(f"Average sentences per example:     {total_sentences / n_examples:.2f}")
    sent_dist = Counter(per_example_sentences.values())
    print(f"Sentences-per-example distribution: {dict(sorted(sent_dist.items()))}")
    print()
    print(f"Gold claims (corpus total):        {total_gold_claims}")
    print(f"Gold claims per example:           {total_gold_claims / n_examples:.2f}")
    print(f"Gold claim density (claims/sentences):  {total_gold_claims / total_sentences:.3f}")
    print()
    print(f"LLM emitted (corpus total):        {llm_emit_total}")
    print(f"LLM emitted per example:           {llm_emit_total / n_examples:.2f}")
    print(f"LLM claim-density (emits/sentences):    {llm_emit_total / total_sentences:.3f}")
    print()
    print(f"GLiNER emitted (corpus total):     {gliner_emit_total}")
    print(f"GLiNER emitted per example:        {gliner_emit_total / n_examples:.2f}")
    print(f"GLiNER claim-density (emits/sentences): {gliner_emit_total / total_sentences:.3f}")

    print()
    print("=" * 70)
    print("  Interpretation: 'what fraction of sentences are claim-bearing?'")
    print("=" * 70)
    print(f"  Gold annotator says:       {total_gold_claims / total_sentences * 100:.1f}%")
    print(f"  LLM-deepseek-flash says:   {llm_emit_total / total_sentences * 100:.1f}%")
    print(f"  GLiNER-zero-shot says:     {gliner_emit_total / total_sentences * 100:.1f}%")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
