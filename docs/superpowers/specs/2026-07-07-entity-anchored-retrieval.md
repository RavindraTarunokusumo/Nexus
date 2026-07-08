# Spec — Local NER Entity-Anchored Retrieval (Rung 1)

**Status:** draft · **Date:** 2026-07-07 · **Session:** claude/h9b-walls

## Problem

The sentence-window system tops out on **LoCoMo multi_hop (0.44)** while every
other category is ≥0.80 (temporal 0.83, open_domain 0.80, single_hop 1.00) and
LongMemEval sits at 0.94. Multi_hop questions ("what volunteering have John *and*
Maria both done?", "what martial arts has John done?") are **co-retrieval / join**
failures: the answer needs two-or-more facts about the same entity (or a shared
value across entities), and top-k semantic+lexical retrieval does not reliably
surface *all* of them together. Sub-query decomposition was tried and **regressed**
multi_hop (0.47→0.39) via RRF dilution — it is out.

The verbatim spans carry no notion of *which entities a sentence is about*, so the
reader is left to reason over whatever text happens to co-retrieve. This spec adds
an **entity layer** — computed with a **local** model (no API cost, preserves the
architecture's core token win) — and an **entity-anchored retrieval channel** fused
into the existing RRF alongside semantic and lexical.

This is Rung 1 of the extraction ladder discussed 2026-07-07: the cheapest change
that captures most of a graph's *retrieval* benefit without reintroducing LLM
extraction (the old LLM-extraction pipeline scored LoCoMo 0.29 — a hard cautionary
bound) and without a traversal graph (Rung 2, deferred).

## Non-goals

- No relation/triple extraction, no graph traversal, no supersession edges (Rung 2).
- No coreference / alias resolution ("John" vs "John Smith" vs "he"). Exact,
  lowercased entity-string match only.
- No Mem0-style ADD/UPDATE/DELETE consolidation (product feature, deferred).
- No change to the reader prompt, judge, or the semantic/lexical channels.

## Approach

Additive, flag-gated (`sentence_window_entity_anchoring`, default off). When on:

1. **Ingest**: local NER over each sentence → entity strings, stored on the existing
   `Span.metadata_json` as a normalized `entities` list.
2. **Retrieve**: NER over the *question* → question-entities; fetch all spans whose
   `entities` intersect the question-entities, ranked by **match count** (a span
   mentioning more of the question's entities ranks higher — the join signal);
   feed that ranked list as a third input to `_rrf_fuse` with semantic + lexical.

When off, ingestion skips NER and retrieval is byte-for-byte the current path.

## Data model

Reuse `Span.metadata_json` (JSONB, already present). Extend from `{"speaker": ...}`
to `{"speaker": ..., "entities": ["john", "homeless shelter", "turtles"]}`.

- Entities normalized: lowercased, whitespace-collapsed, deduped per span.
- Lookup via JSONB containment: `metadata_json -> 'entities' ?| array[:ents]`.
- **Index:** GIN on `(metadata_json -> 'entities')` for the `?|` operator.
  - ponytail: JSONB array + GIN is the lazy-correct store for the ~hundreds-of-spans
    LoCoMo corpora; promote to a normalized `span_entities(span_id, text, type)` join
    table only if corpus scale makes the JSONB scan hurt.

## NER model

Local, CPU-friendly, zero-shot over a fixed conversational label set so it captures
casual entities the reader needs (activities/objects like "turtles",
"homeless shelter"), which classic PERSON/ORG/GPE taggers miss.

- **Primary:** GLiNER (`urchade/gliner_small-v2.1` or similar), labels
  `["person","organization","location","activity","object","event","date"]`.
- torch is already resident (sentence-transformers); GLiNER adds one lightweight
  model. If GLiNER proves unavailable/heavy, spaCy `en_core_web_sm` is the fallback
  (faster, but weaker on casual entities — expect a smaller multi_hop lift).
- Model id behind `sentence_window_ner_model` so it is swappable without code change.

## Interfaces (contract)

```
# app/intelligence/entities.py  (new)
def extract_entities(texts: Sequence[str]) -> list[list[str]]
    # Consumes: raw sentences (or the question, as a 1-list).
    # Produces: per-text normalized entity lists (lowercased, deduped).
    # Local NER, batched. Deterministic given model. No network.

# app/intelligence/sentence_window.py
async def ingest_sentence_spans(..., *, speaker=None)   # CHANGED
    # When settings.sentence_window_entity_anchoring: call extract_entities(sentences)
    # and merge {"entities": [...]} into each span's metadata_json.

async def _fetch_entity_hits(                            # NEW
    session, entities: list[str], fetch_k: int
) -> list[Any]
    # JSONB ?| query -> hit rows (same shape as _fetch_ann_hits: id, document_id,
    # span_index, text, title, url, published_at, fetched_at + a match_count).
    # Ordered by match_count DESC, then span_index. Empty entities -> [].

async def retrieve_windows(..., queries, hybrid)         # CHANGED
    # When entity anchoring on: ents = extract_entities([question])[0];
    # append _fetch_entity_hits(session, ents, fetch_k) to ranked_lists before RRF.
```

`_rrf_fuse`, `_build_blocks`, the reader path, and `answer_sentence_window`'s public
signature are unchanged — the entity channel is just another ranked list into RRF.

## Workflow (retrieval, anchoring on, hybrid on)

1. `ents = extract_entities([question])[0]`
2. semantic hits (ANN), lexical hits (full-text), **entity hits** (JSONB `?|`, ranked
   by match count) — three ranked lists.
3. `_rrf_fuse([...])` → top-k spans (a span present in several channels wins).
4. `_build_blocks` → ±window neighbor context → ordered blocks → reader (unchanged).

## Edge cases

- **No question entities** → entity channel empty; falls back to semantic+lexical
  (same pattern as the empty-lexical fallback). No error.
- **NER miss at ingest** (entity not tagged) → that span simply won't match; the
  semantic/lexical channels still can retrieve it. Additive, never worse.
- **Common-entity noise** (many spans mention "John") → match-count ranking + the
  `fetch_k` cap bound the channel; RRF down-weights a span that only *one* channel
  ranks. Mitigation is structural, not a new knob.
- **Ingest latency**: GLiNER on CPU ≈10–50 ms/sentence; LoCoMo ~500 sentences ⇒
  ~10–25 s/conversation added, one-time. Acceptable for benchmarking; note for scale.
- **Migration**: new GIN index via Alembic; `metadata_json` column already exists so
  no column migration. Old spans without `entities` key match nothing (channel is
  additive) — no backfill required for a fresh benchmark ingest.

## Success criteria

- **LoCoMo multi_hop 0.44 → ≥0.55** (target ~0.60), measured on the standard subset
  (6 conv × 8 q, glm-5.2/deepseek-v4-flash reader, qwen3.7-max judge).
- **No regression**: temporal/open_domain/single_hop and LongMemEval within noise of
  the current best (LoCoMo 0.688 overall, LME 0.940). The channel is additive to RRF.
- **Ingestion stays local**: zero added API calls; added wall-time bounded as above.
- If multi_hop clears ~0.55, that is the signal to invest in Rung 2 (local-LLM
  relation triples + one-hop traversal). If it does not move, the join is not the
  bottleneck and effort shifts to reader quality.

## Risks

| risk | mitigation |
| --- | --- |
| NER quality on casual dialogue (weak channel) | zero-shot GLiNER with conversation-tuned labels; spaCy fallback measured separately |
| Entity channel injects irrelevant spans into RRF | match-count ranking + fetch_k cap + RRF cross-channel down-weighting |
| New dependency (GLiNER) / model download in offline env | pin model; torch already present; spaCy `en_core_web_sm` fallback |
| 0.90 still unreached | expected — residual is reader-synthesis + inference-gold that no retrieval fix touches; stated openly, not a surprise |
