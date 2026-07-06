# Spec: Sentence-Window Retrieval (deterministic ingest, no-LLM memory)

**Date:** 2026-07-06  **Session:** `claude/h9b-walls`  **Status:** MVP for A/B measurement

## Motivation

The current pipeline spends ~96% of tokens (62 of 65 calls/question) building an
LLM-extracted capsule graph + relation classification. That graph is LoCoMo's
accuracy ceiling (lossy capsules, mis-attributed speakers, dropped dates) and the
entire token cost. Replace it with **deterministic sentence-window retrieval**:
split documents into sentences at ingest (no LLM), embed each, and at query time
retrieve a sentence plus its local window (±N neighbors). The raw sentence *is* the
fact — zero extraction loss, zero ingestion API cost. Supersession is handled by
recency scoring over document `published_at` (already in `compute_hybrid_score`);
multi-hop is left to the strong reader over windowed context.

## Requirements

- **R1 — deterministic sentence ingest.** Given a corpus (same document list the
  existing adapters build), split each document's text into sentences and persist
  one row per sentence into `spans` with: `document_id`, `span_index` = 0-based
  sentence position within the document, `text` = sentence, `embedding` = bge-small
  vector, `metadata_json` = `{"speaker": <if known>}`. No `semantic_capsules`, no
  extraction graph, no relation classification. Document `published_at` is set by the
  adapter as today (session/question date) and carries the cross-document temporal
  order.
- **R2 — window retrieval.** Given a question, embed it, ANN-search the sentence
  spans for the top `fetch_k`, then for each hit fetch its neighbor spans
  (`document_id` equal, `span_index` in `[i-W, i+W]`), union + dedup by span id.
  Rank the resulting sentences by a hybrid of semantic similarity and document
  recency (reuse `compute_hybrid_score`'s recency component over `published_at`),
  take the top `k` **windows** (a window = the hit plus its neighbors, kept
  contiguous), and assemble context blocks ordered by `(published_at, span_index)`
  so the reader sees each fact in local + temporal order.
- **R3 — answer path reuse.** Feed the assembled windowed sentences to the existing
  Chain-of-Note answer prompt (`build_user_prompt` / `SYSTEM_PROMPT`, 4k tokens,
  schema-retry) unchanged. Citations reference span ids.
- **R4 — runner mode.** Add `--mode sentence-window` (default `semantic` = today's
  path) to `run_longmemeval.py` and `run_locomo.py`. In sentence-window mode the
  per-instance flow is: ingest documents → sentence-split + embed + persist spans →
  answer each question via window retrieval → judge (unchanged). No extraction /
  relation / consolidation / lifecycle stages run.
- **R5 — config.** `settings.sentence_window_size: int = 2` (W, neighbors each side),
  `settings.sentence_window_top_k: int = 15` (k windows). Sentence splitter: stdlib /
  lightweight (regex on `.?!` with abbreviation guard, or `blingfire`/`nltk` if
  already vendored — no new heavy dependency; a regex splitter is acceptable for the
  MVP).

## Data model

Reuse `spans` (has `document_id`, `span_index`, `text`, `embedding`,
`metadata_json`). No migration. Sentence-window rows are ordinary span rows; the
mode never writes capsules, so the two paths don't collide within a run (a given
worker DB is used by exactly one mode per run).

## Interfaces

- `sentence_window.py::ingest_sentence_spans(session_factory, embedder, document_id, text, *, speaker=None) -> int`
  — split, embed, bulk-insert sentence spans; returns count.
- `sentence_window.py::retrieve_windows(session, embedder, question, *, fetch_k, window, k, as_of) -> list[dict]`
  — ANN + neighbor expansion + hybrid rank + dedup; returns context blocks shaped
  like the existing answer path expects (`label`, `text`, `published_at`, `span_id`).
- Runners: a `--mode` branch that calls the two functions above instead of the
  extraction graph + `_run_retrieve_capsules`, then the existing answer + judge.

## Success criteria

- Runs end-to-end on both adapters producing a scored `results.jsonl` + `report.md`.
- Ingestion makes **zero** LLM calls (assert no `claim_extraction` / `classify_relation`
  rows in `agent_runs` for a sentence-window run).
- Per-question answer-path tokens stay in the ~2–3k range (report actual).
- Accuracy reported per category vs the semantic-pipeline baselines
  (LongMemEval 0.82 gate, LoCoMo 0.29).

## Out of scope (MVP — note as caveats)

- Entity-keyed retrieval expansion (supersession safety net when the query only
  matches the stale claim). Recency scoring is the MVP's only supersession signal.
- Multi-hop query decomposition / iterative retrieval. The reader handles hops it
  can from one-shot windowed context; unknown-bridge hops will under-perform.
- Speaker/entity NER metadata beyond what the adapter already carries.
