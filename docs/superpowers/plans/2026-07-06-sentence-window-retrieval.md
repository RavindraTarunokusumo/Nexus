# Plan: Sentence-Window Retrieval MVP

**Spec:** [`2026-07-06-sentence-window-retrieval.md`](../specs/2026-07-06-sentence-window-retrieval.md)
**Session:** `claude/h9b-walls`

## Task 1 — `app/intelligence/sentence_window.py` (new module)

**Interfaces (Consumes/Produces):**

- `split_sentences(text: str) -> list[str]` — regex splitter on `.?!` boundaries with
  a guard for common abbreviations (Mr., Dr., e.g., etc.); collapse whitespace; drop
  empties. Stdlib `re` only, no new dependency.
- `async ingest_sentence_spans(session_factory, embedder, document_id, text, *, speaker=None) -> int`
  — split `text`, embed each sentence with `embedder.embed_many` (or `embed_one` per
  sentence), bulk-insert `Span` rows: `document_id`, `span_index` = 0-based position,
  `text` = sentence, `embedding` = vector, `token_count` = `estimate_tokens`,
  `metadata_json` = `{"speaker": speaker}` when given. Returns count. No capsules.
- `async retrieve_windows(session, embedder, question, *, fetch_k, window, k, as_of) -> list[dict]`
  — embed question; ANN top-`fetch_k` spans by cosine distance (join `Document` for
  `published_at`, `title`, `url`); for each hit fetch neighbor spans
  (`document_id` = hit's, `span_index` in `[i-window, i+window]`); union + dedup by
  span id; score each hit by `semantic_sim` blended with a recency term over
  `published_at` (reuse the recency normalization approach from
  `compute_hybrid_score` — extract or replicate the min/max recency scaling; do NOT
  call the capsule-specific fields). Select the top-`k` hit windows; assemble one
  context block per window: concatenated neighbor sentences in `span_index` order,
  with `label` (e.g. `C{n}`), `text`, `published_at`, `span_ids`. Order the returned
  blocks by `(published_at, first span_index)`. Return list-of-dict shaped to what
  `app.intelligence.prompts.chat_answer.build_user_prompt` reads (inspect it: at
  minimum `label`, `text`; include a `Date:` via `published_at` the way the existing
  blocks do).
- `async answer_sentence_window(session_factory, client, embedder, question, model, *, fetch_k, window, k, as_of, pack) -> dict`
  — open a session, `blocks = retrieve_windows(...)`; if empty return the
  `INSUFFICIENT_EVIDENCE_ANSWER` shape; else `build_user_prompt` + `SYSTEM_PROMPT`
  and `client.complete_json(..., run_type="chat_answer", max_tokens=4000)` reusing the
  **same schema-retry** wrapper as `chat.py`'s answer node (factor the retry into a
  shared helper or replicate it). Return `{"answer", "citation_labels",
  "tokens_used", "context_blocks", "question_shape": "sentence_window"}`.

## Task 2 — config

`app/config.py`: `sentence_window_size: int = 2`, `sentence_window_top_k: int = 15`,
`sentence_window_fetch_k: int = 60`.

## Task 3 — runner `--mode`

Both `scripts/benchmarks/run_longmemeval.py` and `run_locomo.py`:

- Add `--mode {semantic,sentence-window}` (default `semantic`). Thread `mode` into the
  per-instance / per-conversation function.
- In sentence-window mode, replace the ingest+extract+relations+lifecycle+consolidate
  block with: truncate → persist documents (reuse the document-persist loop from
  `_ingest_corpus`, i.e. `_persist_document` per doc — do **not** call
  `_chunk_and_embed`, `_extract_documents`, `classify_cross_document_relations`,
  `apply_lifecycle_transitions`, `consolidate_domain`) → `ingest_sentence_spans` per
  persisted document (pass the doc's speaker from metadata if the adapter has it).
- Replace `run_chat_with_context(...)` with `answer_sentence_window(...)` using
  `settings.sentence_window_fetch_k / _size / _top_k` (allow `--k` to override
  `sentence_window_top_k`). Keep the existing judge call and row/report writing
  unchanged. `capsule_count`/`relation_count` will be 0 — that is expected; add a
  `sentence_span_count` stat.

## Build order

Task 1 (module + unit test for `split_sentences` and a `retrieve_windows` ranking/
dedup unit test with a fake session) → Task 2 → Task 3 wiring.

## Validation

- Unit: `split_sentences` (abbreviation guard, boundaries), window dedup + ordering
  (pure-ish, mock rows).
- Full `ruff check` + `ruff format --check` + `mypy app/` + `pytest` (ignore the 6
  known pre-existing failures + 2 ASYNC240 + 3 mypy listed in prior handoffs).
- Assert no `semantic_capsules` writes and no `claim_extraction`/`classify_relation`
  `agent_runs` in a sentence-window smoke.

## Risks

- `build_user_prompt` block-shape mismatch → inspect it and match the fields it reads;
  unit-test one assembled block through it.
- Recency scaling coupling: replicate only the `published_at` min/max recency term,
  not capsule epistemic fields.
- Span table shared with the semantic path: fine because a worker DB runs one mode per
  run and the runner truncates first.
