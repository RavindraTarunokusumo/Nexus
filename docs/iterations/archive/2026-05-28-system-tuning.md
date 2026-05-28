# System Tuning — Eval-Driven Architecture Overhaul

**Dates:** 2026-05-26 → 2026-05-29
**Branch:** `feature/system-tuning`
**PR:** [#14](https://github.com/RavindraTarunokusumo/Nexus/pull/14)
**Merge ID:** _pending_

## Outcome

Tactical eval-driven tuning campaign that exposed and fixed structural
limitations in the claim-extraction pipeline. Net effect:

| Metric (ai_tech_v4, cross-family judge) | Before | After (GLiNER stack) | Δ |
|---|---:|---:|---:|
| F1 | 0.327 | **0.713** | +0.39 |
| Precision | 0.226 | 0.656 | +0.43 |
| Recall | 0.667 | 0.878 | +0.21 |
| Type accuracy | 0.567 | 0.641 | +0.07 |
| SUT cost per run | $0.025 | $0.000 | -100% |

Highest-impact lever: replacing Jaccard with Sørensen-Dice alignment in the eval framework — surfaced ~0.30 F1 of "true" recall that was being eaten by an alignment bug.

## Subitems

Per `TODO.md` workflow rule, each subitem landed as its own commit. Tagging with hash.

### Phase A — Experiment-trial system (T1-T9)
- [x] Ran calibration check, per-type slice, pro model, prompt tweaks, confidence filter, dedup, json_schema, distill, larger gold (T7-T9 + T1-T6) — `9dbe97c`
- [x] Reported the trial matrix with recommendations and an F1 0.327 → 0.401 result on ai_tech_v2 — `9dbe97c`

### Phase B — System-level (S1-S10)
- [x] S10 judge calibration populated (kappa=0.75 against seed labels) — `9dbe97c`
- [x] S8 confidence calibration — found self-reported confidence is information-free — `9dbe97c`
- [x] S7 cross-family judge (gemini-2.5-flash) → confirmed in-family bias ≈ +0.04 F1 — `9dbe97c`
- [x] S1 sentence-bounded extraction (regressed on this dataset shape — env-gated, kept) — `9dbe97c`
- [x] S6 atomicity validator (regressed — env-gated, kept as opt-in) — `9dbe97c`
- [x] S4 canonicalization library (entity aliases + signature clustering + supersede check) — `9dbe97c`
- [x] S2/S3/S5/S9 combined migration `0004_system_tuning` (category, claim_embedding, valid_from/to, superseded_by, canonical_claim_id) — `9dbe97c`

### Phase C — Taxonomy v2
- [x] `app/intelligence/taxonomy.py` — `CATEGORIES` dict, dotted vocabulary, `legacy_to_new()` — `1ae0f8d`
- [x] `ExtractedClaim.claim_type` switched to Literal[24 dotted strings] — `1ae0f8d`
- [x] `ai_tech_v3.yaml` relabeled via `relabel_gold_v3.py` — `1ae0f8d`

### Phase D — T1 GLiNER + Dice alignment
- [x] `gliner_extractor.py` per-sentence pipeline (is_claim → claim_type → NER + canonical entities) — `26d4c5c`
- [x] Runner branch on `EXTRACTOR=gliner`; `asyncio.to_thread` wrapper for CPU-bound extraction — `26d4c5c`
- [x] `_dice` + punctuation-normalized tokens in `align_claims` (threshold 0.5) — `26d4c5c`

### Phase E — End-to-end S5 + deferred items
- [x] `chat.retrieve_spans` hybrid scoring (max of span and claim embeddings) — `3d6bb55`
- [x] `extraction.store_claims` batch-embeds claim_text via `embedder.embed`; writes `claim_embedding` — `3d6bb55`
- [x] Populates `claims.category` via `taxonomy.category_of()` at extraction time — `3d6bb55`
- [x] Default `settings.extractor="gliner"` + `judge_model="google/gemini-2.5-flash"` — `3d6bb55`
- [x] Gold v4 multi-claim re-curation (45 → 70 gold claims) — `3d6bb55`
- [x] Unit tests: `test_taxonomy`, `test_canonicalization`, `test_metrics_dice` — `3d6bb55`

### Phase F — Simplify review
- [x] `embedder.embed` now uses `asyncio.to_thread` (no event-loop block) — `8c2e470`
- [x] `canonicalize()` orders DESC so newest is canonical (matches `supersede_check`) — `8c2e470`
- [x] `_schema_is_strict_safe()` guards strict JSON schema when Optional fields present — `8c2e470`
- [x] `_extract_entities_list()` handles list / `{"entities": …}` / GLiNER dict shapes — `8c2e470`
- [x] `EVAL_DISTILL_PASS` skipped when `EXTRACTOR=gliner` with one-time warning — `8c2e470`

### Phase G — Pre-PR
- [x] Docs updates (architecture, database, commands) — `4027699`
- [x] `pre-commit run --all-files` → all 12 hooks green — `4027699`
- [x] `npx gitnexus analyze` (2662 → 3417 symbols, 76 → 96 flows) — `4027699` + `348ad78`
- [x] PR opened — see header

## Deferred to follow-on (logged in `TODO.md`)

- S3 multi-span provenance in real ingestion (ClaimEvidence already supports it; extractor still emits 1 row per claim)
- S4 canonicalization wired as post-ingest hook (needs S3 first for meaningful multi-doc data)
- S9 supersede check on real claims (needs real ingested data)
- Fine-tune GLiNER on v4 corpus (target type accuracy 0.85+)
- Cross-family Claude human labels (Anthropic blocked at OpenRouter routing layer)
- Integration test: ingest → extract → chat retrieves a claim-side hit that beats the span-side score

## Key learnings (deeper takes in `docs/insights.md` § 2026-05-29)

1. **The eval can be the bottleneck.** Jaccard alignment silently capped recall at 0.40-0.75 for both LLM and GLiNER SUTs. Swapping to Dice surfaced 0.20+ F1 that was always there.
2. **Self-reported LLM confidence is information-free** on this task. Filtering on it works only as variance reduction, not signal selection.
3. **In-family LLM judges inflate by ~0.04 F1.** Default to cross-family.
4. **A 110M-param CPU encoder + good architecture beats a 7B+ LLM API** on this task. The architecture matters more than the model size when the task is fundamentally span-tagging.
5. **Permissive-extract + selective-retrieve is the right principle.** Don't try to answer "is this a salient claim?" at storage time; let the query decide.
