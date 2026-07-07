# Plan — Entity-Anchored Retrieval (Rung 1)

Implementer contract for `docs/superpowers/specs/2026-07-07-entity-anchored-retrieval.md`.
Additive, flag-gated (`sentence_window_entity_anchoring`, default off). When off, the
current retrieval path is byte-for-byte unchanged.

## File structure

- `app/intelligence/entities.py` — **new**. Local NER wrapper.
- `app/config.py` — add `sentence_window_entity_anchoring: bool = False`,
  `sentence_window_ner_model: str = "urchade/gliner_small-v2.1"`.
- `app/intelligence/sentence_window.py` — ingest tagging + entity retrieval channel.
- `alembic/versions/*` — GIN index on `(metadata_json -> 'entities')`.
- `tests/intelligence/test_entities.py` — **new**. Pure-helper tests.
- `tests/intelligence/test_sentence_window.py` — extend (entity-hit ranking / RRF wiring).

## Tasks (build order)

1. **`entities.py` — `extract_entities(texts) -> list[list[str]]`.**
   Local, batched NER. Try GLiNER (`sentence_window_ner_model`, label set
   person/organization/location/activity/object/event/date); fall back to spaCy
   `en_core_web_sm` if GLiNER unavailable. Normalize: lowercase, collapse whitespace,
   dedup per text, drop len≤2 tokens. Lazy-load the model at module scope (one load).
   - **Offline safety:** if neither model can load, raise at first call — but the
     function must be import-safe (no load at import) so tests can monkeypatch it.
   - Consumes: sentences or `[question]`. Produces: per-text entity lists.

2. **Ingest tagging — extend `ingest_sentence_spans`.**
   When `settings.sentence_window_entity_anchoring`: `ents = extract_entities(sentences)`
   and merge `{"entities": ents[i]}` into each span's `metadata_json` (preserving
   `speaker`). When off: unchanged (no NER call).

3. **`_fetch_entity_hits(session, entities, fetch_k) -> list[Any]`.**
   Empty `entities` → `[]`. Else JSONB `metadata_json -> 'entities' ?| :ents`, returning
   the same column shape as `_fetch_ann_hits` (id, document_id, span_index, text, title,
   url, published_at, fetched_at) plus a computed `match_count` = size of the
   intersection. Order by `match_count DESC, span_index`. Limit `fetch_k`.
   - Use a parameterized `text()` query (array param); guard with try/except → `[]`.

4. **Wire into `retrieve_windows`.**
   When anchoring on: `ents = extract_entities([question])[0]`; append
   `_fetch_entity_hits(session, ents, fetch_k)` to `ranked_lists` **before** `_rrf_fuse`.
   Entity anchoring implies the RRF path (same branch condition as `hybrid or len>1`);
   extend that condition to include the anchoring flag. Semantic/lexical channels
   unchanged. `_rrf_fuse`, `_build_blocks`, `answer_sentence_window` signatures unchanged.

5. **Migration.** Alembic revision adding the GIN index (JSONB path ops). No column
   change (`metadata_json` exists). Downgrade drops the index.

6. **Tests.** `test_entities.py`: normalization + dedup + short-token drop on a
   monkeypatched/deterministic extractor (no model download in CI). Extend
   `test_sentence_window.py`: `_fetch_entity_hits` match-count ordering is exercised via
   a fake result set, and `_rrf_fuse` already covered — add one asserting an
   entity-channel hit that also appears semantically wins fusion.

## Interfaces

See spec §Interfaces. The only changed public-ish surfaces are `ingest_sentence_spans`
(behavior, same signature) and `retrieve_windows` (new internal branch, same signature).
No other caller changes — `answer_sentence_window` and the benchmark scripts are untouched.

## Validation

`ruff check` + `ruff format --check` + `mypy app/` + `pytest` full suite. Tests must pass
**without network** (extractor monkeypatched). Single trailing newline per file.

## Risks

- GLiNER/model download unavailable in the build env → keep NER load lazy + injectable
  so the suite is green offline; real model wired at benchmark time via config.
- JSONB `?|` requires the entities stored as a JSON array of text — ensure ingest writes
  a plain list, not nested. Covered by an ingest→fetch round-trip check where a DB is
  available (skip-if-no-DB), plus the pure-helper tests.
- Entity-channel noise → match-count ranking + `fetch_k` cap (spec §Edge cases).

## Out of scope (Rung 2+)

Relation triples, graph traversal, coref/alias resolution, supersession/consolidation.
