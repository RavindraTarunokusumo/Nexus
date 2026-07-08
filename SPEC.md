# Perpetual Analyst — Specification

**Status:** draft v1 · **Date:** 2026-07-08 · **Track:** Qwen Cloud MemoryAgent

> This spec is self-contained. Perpetual Analyst (PA) is built in a **separate repo**
> that **clones Nexus** and uses it as the memory substrate. Sections 2–3 document the
> Nexus architecture PA inherits (what to reuse, what to leave behind); sections 4+
> specify PA itself.

---

## 1. Summary

**Perpetual Analyst** is a Qwen-powered research agent with persistent **narrative
memory**. It watches a topic over time, remembers source-grounded developments across
sessions, updates a living interpretation as new evidence arrives, maintains competing
hypotheses, and makes scored predictions. It answers: *what changed, why it matters,
what explains it, and what may happen next.*

- **One-liner:** persistent narrative memory for analysts.
- **Not** a summarizer, fact-checker, or chat-history wrapper. The value is
  cross-session, memory-driven analysis.
- **Judged contribution:** the *analytical* memory layer — source / claim / event /
  narrative / hypothesis / prediction — not raw text recall.
- **Primary demo domain:** AI / LLM developments (single domain for the MVP).

### Track fit
Qwen's MemoryAgent track asks for agents that accumulate experience, remember across
sessions, update understanding, retrieve efficiently, and forget outdated information.
PA's value *depends* on cross-session memory — the narrative/hypothesis/prediction
objects persist and are retrieved fresh each session.

---

## 2. Nexus as the Memory Substrate

PA clones Nexus and builds on its infrastructure. Nexus is a FastAPI + SQLAlchemy-async
+ Postgres/pgvector + Redis + LangGraph application using **Qwen Cloud** models
(OpenAI-compatible via DashScope-intl) and local embeddings.

### 2.1 Reuse as-is (inherited infrastructure)

| Capability | Nexus entry point | PA use |
| --- | --- | --- |
| Source ingestion (paste/upload/url/rss) | `POST /ingest/text` \| `/ingest/url` \| `/ingest/rss`; `_persist_document` (content-hash + URL dedupe) | paste-snippet ingest is the demo path |
| Chunk + embed → spans | `_chunk_and_embed`, `chunk_document`, `Embedder` (Qwen3-Embedding-0.6B @384-dim, MRL-truncated; asymmetric query/document prompts) | claim/event embedding |
| **Extraction *mechanism*** | `make_extraction_graph` (LangGraph `StateGraph`) + `LLMClient.complete_json` structured-JSON output + dual-write + deterministic `idempotency_key` + evidence-span linkage | reuse the *pattern*, new schema (§4.1) |
| Semantic retrieval | pgvector ANN (HNSW) + hybrid rescore (`_run_retrieve_capsules`); returns cited blocks with roles/evidence | topic-scoped claim/event retrieval |
| Sessions | `ChatSession` / `ChatMessage` + LangGraph `AsyncPostgresSaver` checkpointer | session container only (see §2.3) |
| Inspector seed | `GET /stats/overview`, `GET /capsules/{id}/provenance`; React 19 + Vite app (Chat / Dashboard / "How it works" provenance graph) | seed for the memory inspector |
| Observability | `agent_runs` (per-LLM-call cost/token log) | cost tracking |

### 2.2 The Qwen stack (validated)
Embedder **Qwen3-Embedding-0.6B**@384, reader/extractor **qwen3.x-plus** (thinking),
judge/synthesis **qwen3.x-max**. All OpenAI-compatible, structured JSON output, via
`LLMClient` (`app/intelligence/llm_client.py`) — `_TIMEOUT`, JSON-fence stripping,
schema-retry, thinking-locked-model handling already implemented.

### 2.3 Do NOT reuse — the scrapped extraction/ontology layer

Nexus's original **semantic-capsule pipeline** was benchmarked at **~69k tokens/question**
and abandoned for the memory benchmark (the deterministic sentence-window path replaced
it). PA keeps the *mechanism* but **not** this layer:

- **`semantic_capsules` ontology** — `core_type` (15-value), `source_telos`,
  `object_family`, `domain_object_type`, `function`, `facets`, `salience`,
  `escalation_state`. This is the "full Nexus ontology" the brief says to avoid.
- **domain-pack telos steering** (`domain_packs`, `build_source_prompt_prefix`).
- **Full `epistemic_state`** + `judge_capsules` escalation machinery.
- **The O(n²) relation reasoning at ingest** — `classify_relations` (~52 LLM
  calls/question, ~39% of the old cost) and `cross_relations`. PA computes
  supersession/contradiction/hypothesis links **lazily on the retrieved subset per
  query**, never eagerly over the whole corpus.
- **`theses` / `decision_artefacts`** tables (part of the same ontology) — PA's
  hypothesis object is fresh (§3), though its shape is informed by `theses`.

> **Reuse the machinery, replace the ontology.** The cheap, reusable parts are the
> LangGraph structured-extraction plumbing, evidence linkage, idempotency, embeddings,
> retrieval, and the API/UI shell — not the capsule/pack/epistemic stack.

### 2.4 Gaps in Nexus that PA must close
- **No topic scoping** — retrieval is over one global corpus (flagged in Nexus PR #32).
  PA adds a `watch_topic_id` scope on every memory object and a `WHERE topic_id = …`
  filter on every retrieval query.
- **Session memory is write-only** — the checkpointer stores turns but only the latest
  is used; there is no cross-session carry. PA **sidesteps** this: cross-session memory
  is the persistent analytical objects (narrative/hypothesis/prediction) retrieved fresh
  per session, not conversation history.
- **No narrative-diff, events, predictions, or user preferences** — all new (§3, §4.2).

---

## 3. PA Memory Model (analytical schema)

Seven memory types → narrow tables, all scoped by `watch_topic_id`. New Alembic
migrations on top of the Nexus schema. Reuse Nexus `documents`/`spans` for raw text +
embeddings; PA claims/events reference spans for evidence.

| Table | Purpose | Key columns |
| --- | --- | --- |
| `watch_topics` | the scoping unit ("AI agent memory systems") | `id`, `name`, `description`, `domain`, `created_at` |
| `source_profiles` | who said it + reliability | `id`, `topic_id`, `document_id`, `name`, `source_type`, `incentive_note`, `reliability` (0–1), `created_at` |
| `claims` | source-backed atomic assertion | `id`, `topic_id`, `document_id`, `claim_text`, `entities_json`, `confidence` (0–1), `source_authority` (0–1), `status` (`active`/`superseded`/`contradicted`/`stale`), `embedding`, `created_at`; evidence via `claim_evidence(claim_id, span_id, quote)` |
| `events` | time-stamped development | `id`, `topic_id`, `document_id`, `event_time`, `description`, `entities_json`, `claim_ids` (backing claims), `embedding`, `created_at` |
| `narrative_states` | living interpretation, **versioned** | `id`, `topic_id`, `version`, `summary`, `change_summary` (what changed vs prev + why), `prev_version_id`, `supporting_claim_ids`, `created_at` |
| `hypotheses` | competing explanations | `id`, `topic_id`, `statement`, `confidence` (0–1), `status` (`active`/`leading`/`retired`/`invalidated`), `supporting_claim_ids`, `contradicting_claim_ids`, `invalidation_criteria`, `created_at`, `updated_at` |
| `predictions` | scored forecasts | `id`, `topic_id`, `hypothesis_id`, `statement`, `probability` (0–1), `horizon_days`, `resolve_by`, `resolution_criteria`, `status` (`open`/`hit`/`miss`/`expired`), `outcome_note`, `created_at`, `resolved_at` |
| `user_preferences` | light framing/interests | `id`, `topic_id`, `interests_json`, `framing_note` |

`entities_json` holds string lists (orgs/models/people); no separate entity table or
resolution in the MVP (Nexus's local NER `extract_entities` is available if needed).

---

## 4. Pipelines / Workflows

### 4.1 Ingest + extract (per source — **one** LLM call)
1. `POST /topics/{id}/ingest` (paste/url) → `document` (reuse Nexus ingest + dedupe) →
   chunk + embed spans.
2. **One structured extraction call** (qwen-plus, `complete_json`) over the document
   returns `SourceExtraction` = `{source_profile, claims[], events[]}` where each claim
   carries `claim_text`, `entities`, `confidence`, `source_authority`, and
   `evidence_span_indices`. Dual-write with an `idempotency_key` (reuse Nexus pattern);
   embed claims/events. Re-ingest is idempotent (delete-then-insert by document).
3. **No** relation classification, judging, or thesis synthesis at ingest (cost-bounded).

### 4.2 Narrative-update loop (**the core contribution**)
Triggered on "update my understanding" (or after N new sources):
1. Retrieve the topic's **current `narrative_state`** + the **top-k relevant claims/events**
   (topic-scoped ANN + hybrid), including newly-added and prior claims.
2. **One synthesis call** (qwen-plus) that: compares prior narrative vs. new evidence,
   marks superseded/contradicted claims **within the retrieved subset**, writes a **new
   `narrative_state` version** with a `change_summary` ("before X, now Y because A/B/C
   from S1/S2"), updates each `hypothesis` (supporting/contradicting sets + confidence;
   spawn/retire per `invalidation_criteria`), and emits/updates `predictions`.
3. Persist: new narrative version (prev linked), claim `status` flips, hypothesis + prediction rows.
4. Return the **briefing** + the set of objects **retrieved** vs **updated** (for the inspector).

### 4.3 Cross-session query
Answered from persistent objects, not chat history: "current view" → latest
`narrative_state`; "competing hypotheses" → `hypotheses` for the topic; "what did you
predict / did it resolve" → `predictions`. Reuse the Nexus retrieval + Chain-of-Note
reader for grounded, cited sub-answers.

### 4.4 Prediction scoring / lifecycle
A `predictions resolve` pass (CLI or on new evidence): predictions past `resolve_by`, or
matched by resolving evidence against `resolution_criteria`, are scored `hit`/`miss`
(`expired` if undecidable). Claims decay `active → stale` past a topic-configurable window.

---

## 5. Interfaces

### 5.1 New API endpoints (extend Nexus FastAPI)
- `POST /topics`, `GET /topics`, `GET /topics/{id}` — watch topics.
- `POST /topics/{id}/ingest` — ingest a source into a topic (wraps Nexus ingest + §4.1).
- `POST /topics/{id}/update` — run the narrative-update loop (§4.2); returns briefing +
  `{retrieved:[…], updated:[…]}` object ids.
- `GET /topics/{id}/narrative` — current + version history (timeline).
- `GET /topics/{id}/hypotheses`, `GET /topics/{id}/predictions`, `GET /topics/{id}/claims`
  (filter by status) — **browse/inspect** (closes Nexus's missing list endpoints).
- `POST /topics/{id}/ask` — cross-session query (§4.3).

### 5.2 New UI views (extend the React app)
- **Watch-topic** list + create.
- **Narrative timeline** — versions with change-summaries (the "what changed" story).
- **Hypothesis board** — competing hypotheses with confidence + supporting/contradicting claims.
- **Prediction ledger** — open/resolved forecasts with probability + outcome.
- **Retrieved-vs-updated diff** — the key demo surface, reusing the provenance graph seed.

### 5.3 LLM structured-output schemas (Pydantic, via `complete_json`)
- `SourceExtraction` = `{source_profile:{type,incentive_note,reliability}, claims:[{claim_text,entities,confidence,source_authority,evidence_span_indices}], events:[{event_time,description,entities,claim_refs}]}`
- `NarrativeUpdate` = `{narrative_summary, change_summary, superseded_claim_ids, hypotheses:[{statement,confidence,supporting_claim_ids,contradicting_claim_ids,invalidation_criteria,status}], predictions:[{statement,probability,horizon_days,resolution_criteria}]}`

---

## 6. Memory lifecycle (states)

- **claim:** `active` → `superseded` | `contradicted` | `stale`
- **hypothesis:** `active` → `leading` → `retired` | `invalidated`
- **prediction:** `open` → `hit` | `miss` | `expired`
- **narrative:** append-only versions (history is the diff source; never deleted)

---

## 7. User interaction flow (demo story)

1. Create watch topic "AI agent memory systems."
2. **Session 1** — paste several source snippets → extraction builds initial narrative +
   hypotheses + predictions; inspector shows created objects.
3. **Session 2 (later)** — add new sources.
4. Ask **"What changed in your understanding?"** → narrative-update loop → briefing:
   *"Before I believed **X**; after claims **A/B/C** from **S1/S2** I update toward **Y**;
   prediction **Z**, 60% over 30 days."*
5. Inspector highlights **retrieved vs updated** memory objects.
6. Cross-session queries anytime ("current view", "competing hypotheses", "did your
   prediction resolve").

---

## 8. Constraints

- **Qwen Cloud only** (OpenAI-compatible, structured JSON output).
- **Cost-bounded:** one extraction call per source; all heavy reasoning (narrative diff,
  supersession, hypothesis update) runs on the **retrieved subset per query** — never
  O(n²) over the corpus. This is the explicit lesson from the abandoned capsule pipeline.
- **Topic-scoped** retrieval on every query (`WHERE topic_id`).
- **Single primary domain** (AI/LLM) for the MVP.
- Reuse Nexus infra; add only the narrow analytical tables + the update loop.

---

## 9. Scope

**Build:** watch topics; source ingestion (reuse); narrow structured extraction; the 6
analytical tables + preferences; topic-scoped semantic retrieval; the narrative-update
loop; hypothesis + prediction tracking + scoring; cross-session query; the memory
inspector (browse + narrative timeline + retrieved-vs-updated).

**Do NOT build** (per brief): autonomous crawling; Telegram/Notion; multi-domain
pipeline; real-time monitoring; political-source reliability engine; full benchmark
suite; **the full Nexus capsule/telos/epistemic ontology**; multi-agent orchestration.

---

## 10. Success criteria

1. The agent remembers across sessions (persistent analytical objects).
2. Memory is structured and queryable (browse endpoints + inspector).
3. The agent **uses** memory to update analysis, not merely recall text (the update loop
   produces a versioned narrative diff).
4. Source-backed claims are distinguished from interpretation (claim vs narrative;
   `source_authority`/`confidence`).
5. The user can inspect what memory was **retrieved** and what was **updated**.
6. The demo maps clearly to Qwen MemoryAgent requirements.
7. Repo has architecture diagram, setup, OSS license, demo video, deployment proof.

---

## 11. Edge cases / risks

- **Contradictory sources** → keep both claims, surface the conflict, let the hypothesis
  confidences diverge; don't silently pick one.
- **Low-evidence claims** → low `source_authority`/`confidence`; excluded from
  narrative unless corroborated.
- **Narrative thrash** on noisy single sources → require ≥N corroborating claims (or a
  confidence threshold) before a narrative version flips.
- **Prediction resolution without ground truth** → `expired` when undecidable; never
  fabricate an outcome.
- **Entity coref** ("GPT-4o" vs "the model") — string-match only in MVP; note as a limit.
- **Cost creep** — cap retrieved-subset size (top-k) so update-loop cost is bounded.

---

## 12. Open decisions (defer to plan)

- Exact top-k / corroboration thresholds for narrative flips (tune on the demo corpus).
- Whether hypotheses are seeded by the first extraction or only by the first update loop.
- Prediction scoring cadence (CLI pass vs on-ingest trigger).
- How much of the Nexus React app to fork vs. rebuild for PA's views.
