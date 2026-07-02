# Memory Benchmark Plan — Qwen Hackathon (MemoryAgent)

Date: 2026-07-02. Branch: `claude/def-hackathon`. Scope: survey external agent-memory benchmarks, map them to Nexus capabilities, and define the Nexus-native synthetic harness plus hackathon metrics (F1/F5).

## Nexus capability baseline (repo-grounded)

What ships today on the hackathon branch path (see `docs/architecture.md`, `TODO.md` Phases D–F):

| Capability | Status | Notes |
|---|---|---|
| Document ingestion + chunk/embed | **Implemented** | RSS, URL, text via `routes_ingestion.py`; spans + local `bge-small-en-v1.5` embeddings |
| Capsule extraction | **Implemented** | LangGraph `extraction.py`: T2 semantic-object extraction → `semantic_capsules` + `capsule_segments` |
| Relations at extract time | **Implemented** | `judge_capsules` (unary) + `classify_relations` (binary: supports/contradicts/qualifies/supersedes/…) → `semantic_relations` |
| Capsule retrieval + chat | **Implemented** | `chat.py`: intent classify → HNSW cosine over capsules → hybrid re-rank → grounded answer + citations |
| Citation validation + abstention | **Implemented** | `INSUFFICIENT_EVIDENCE_ANSWER` when retrieval empty or all citation labels invalid |
| Epistemic metadata on capsules | **Implemented** | `epistemic_state` JSONB (source_authority, evidence_quality) on extraction; hybrid scoring inputs being un-stubbed (D2) |
| Context assembly (counter-evidence, supersession blocks) | **In flight (D2)** | Pack-driven `context_assembly.include`; not on clean main yet |
| Lifecycle transitions | **In flight (E1/E2)** | `apply_lifecycle_transitions`: superseded/stale/confirmed/…; CLI `nexus lifecycle run` |
| Thesis consolidation | **In flight (E3)** | `consolidate_domain` → `theses` via relation clustering; manual `nexus theses synthesize` exists today |
| Multi-turn session memory | **Partial** | `session_memory.py` persists chat turns; not wired to capsule lifecycle or benchmark harness |
| External benchmark adapters | **Not implemented** | Stretch/post-hackathon per TODO F6 |

**Gaps Nexus does not cover today:** conversational episodic memory (LoCoMo-style multi-session dialogues as first-class ingest), open-domain personal user profiles, implicit memory writes from chat, BEAM/Memora native task formats, and automatic re-ingest of revised facts without a new document. Benchmark supersession/thesis scores depend on E1–E3 running after corpus ingest (Wave 3 pipeline ordering).

---

## External benchmark survey

### LoCoMo (Maharana et al., 2024 — *Evaluating Very Long-Term Conversational Memory of LLM Agents*)

**Measures:** Very long multi-session dialogues (~300 turns); QA over accumulated conversational facts; temporal ordering; persona/event consistency; summarization of distant events.

| Probe | Nexus mapping | Verdict |
|---|---|---|
| Fact retention across sessions | Capsule extraction from ingested text + retrieval | **Stretch** — no LoCoMo dialogue ingest adapter; session memory is turn-level, not capsule-indexed |
| Temporal reasoning | Dated capsules + `published_at` on documents | **Partial** — timeline questions in `nexus_synthetic`; no conversational timestamp alignment |
| Knowledge updates mid-dialogue | Lifecycle supersession (E1) + `supersedes` relations | **Stretch** — lifecycle applies to document-derived capsules, not chat turns |
| Multi-hop over scattered facts | Retrieval + relations + (D2) context assembly | **Partial** — `multi_doc` category; lacks LoCoMo's dialogue-specific noise profile |

### LongMemEval (Wu et al., 2024 — *LongMemEval: Benchmarking Long-Term Memory in LLM Agents*)

**Measures:** Five abilities — information extraction, multi-session reasoning, temporal reasoning, knowledge updates, abstention on unanswerable items.

| Ability | Nexus mapping | Verdict |
|---|---|---|
| Information extraction | T2 extraction graph → capsules | **Implemented** (document stream, not chat logs) |
| Multi-session reasoning | Relations + multi-doc retrieval | **Partial** — `multi_doc` / `thesis` categories |
| Temporal reasoning | Recency in hybrid score + dated corpus | **Partial** — `timeline` category; no LongMemEval session-gap simulation |
| Knowledge updates | Supersession lifecycle + contradicts relations | **In flight (E1/E2)** — scored via `superseded` category after pipeline run |
| Abstention | `INSUFFICIENT_EVIDENCE_ANSWER` | **Implemented** — `abstention` category |

**Adapter:** post-hackathon — requires converting LongMemEval JSON sessions to `corpus.jsonl` + question schema or a parallel scorer.

### BEAM (agentic memory benchmark family; exact paper title varies — treat as *benchmarking episodic/working memory for LLM agents*)

**Measures (typical):** Memory write/read cycles, interference, selective retention, task-conditioned recall under distractors.

| Probe | Nexus mapping | Verdict |
|---|---|---|
| Explicit remember/forget | No `nexus.memory.remember` MCP tool yet (H-MCP1 doc only) | **Not implemented** |
| Distractor resistance | Hybrid scoring + salience threshold | **Partial** — no BEAM distractor protocol |
| Working memory vs long-term store | Capsules (LT) vs chat session (STM) | **Partial** — two stores, no unified eval |

**Adapter:** post-hackathon unless core `nexus_synthetic` baseline is green first (TODO stretch note).

### Memora (memory-agent evaluation framework; name used in recent MemoryAgent literature — exact citation uncertain)

**Measures (typical):** Structured memory CRUD, grounded QA from memory bank, consolidation quality, staleness handling.

| Probe | Nexus mapping | Verdict |
|---|---|---|
| Memory bank QA | `/chat/answer` over capsules | **Implemented** (ingest-then-ask, not incremental Memora API) |
| Consolidation / summaries | `consolidate_domain` → theses (E3) | **In flight** — `thesis` category |
| Staleness / expiry | `stale` lifecycle + `retention_policy.stale_conditions` | **In flight (E2)** — corpus includes expired forecast fixture |
| Authority tiers | `epistemic_state.source_authority` + D2 scoring | **Partial** — `authority_conflict` category |

**Adapter:** post-hackathon.

### RAG / multi-hop QA baselines (HotpotQA, MuSiQue, 2WikiMultiHopQA, etc.)

**Measures:** Retrieve evidence spans across ≥2 documents; compose answer; cite supporting passages; avoid unsupported hops.

| Probe | Nexus mapping | Verdict |
|---|---|---|
| Multi-document evidence fusion | Multi-doc ingest + top-k capsule retrieval + citations | **Implemented** — `multi_doc` category |
| Hop chaining | Relations (`supports`, `contradicts`) + thesis clusters | **Partial** — relations at extract time; no explicit hop planner |
| Citation grounding | Label validation (`C1`…), evidence spans on `ChatCitation` | **Implemented** |
| Open-domain Wikipedia scale | Fixed demo domain pack `personal_ai_tech` | **Not implemented** — synthetic AI-tech corpus only |

**Adapter:** stretch — would need span/capsule alignment to gold supporting facts.

---

## Nexus-native synthetic benchmark (`evals/memory/nexus_synthetic/`)

Primary hackathon harness (F2). No Python in the fixture dir; runner + scorer live under `scripts/benchmarks/` (F3/F5).

### Corpus (`corpus.jsonl`)

One JSON object per line:

```json
{"doc_key": str, "title": str, "url": str, "source_type": str, "published_at": "ISO8601", "text": str}
```

- **12–16 documents**, coherent fictional AI-tech timeline, dates **2025-09 … 2026-06**.
- **Required fact patterns:** model releases with versions/dates; benchmark results across ≥2 docs; pricing change superseding earlier price; deprecated model; tertiary rumor vs primary official conflict; expired forecast; ≥3 docs supporting one investable thesis.
- `url` unique fake HTTPS; `source_type` ∈ pack `supported_source_types`; `text` 300–900 words, dense factual prose.

### Questions (`questions.jsonl`)

```json
{
  "question_id": str,
  "category": "timeline"|"multi_doc"|"superseded"|"authority_conflict"|"thesis"|"abstention",
  "question": str,
  "expected_answer_keywords": [str],
  "forbidden_keywords": [str],
  "expected_doc_keys": [str],
  "expected_abstain": bool,
  "notes": str
}
```

- **≥3 questions per category (≥18 total).** Keywords lowercased for scoring.
- **Abstention:** facts absent from corpus; `expected_doc_keys=[]`, `expected_abstain=true`.

| Category | What it probes |
|---|---|
| `timeline` | Correct date/version ordering from dated releases |
| `multi_doc` | Aggregate facts across ≥2 documents (RAG multi-hop analogue) |
| `superseded` | Prefer superseding fact; forbid superseded keywords (needs E1 + ingest) |
| `authority_conflict` | Prefer primary over tertiary source (epistemic_state + D2) |
| `thesis` | Answer reflecting consolidated relation cluster (needs E3) |
| `abstention` | Return insufficient-evidence answer, no hallucination |

### Runner pipeline (`run_memory_benchmark.py`)

1. Idempotent ingest corpus by URL → chunk/embed → extraction graph per doc.
2. `apply_lifecycle_transitions` → `consolidate_domain`.
3. Per question: `run_chat_with_context` (Qwen T2); map citation URLs → `doc_key`; abstained ⇔ answer == `INSUFFICIENT_EVIDENCE_ANSWER`.
4. Emit `results.jsonl`, `report.md`, `run_meta.json` under `--out`.

CLI surface (F4): `nexus eval memory run --benchmark nexus_synthetic --k N` and `nexus eval memory report --run-id <id>` → `docs/benchmarks/runs/<run-id>/`.

---

## Hackathon metrics (F5 — `scripts/benchmarks/scoring.py`)

Per-question fields from `score_answer(question, answer, cited_doc_keys, retrieved_doc_keys, abstained)`:

| Metric | Definition |
|---|---|
| **answer_correctness** | \|expected_answer_keywords ∩ answer_lower\| / \|expected_keywords\|; **1.0** when `expected_abstain` and abstained |
| **forbidden_violation** | Any `forbidden_keyword` present in answer (bool) |
| **evidence_recall@k** | \|cited ∩ expected_doc_keys\| / \|expected_doc_keys\|; `None` if expected empty |
| **citation_precision** | \|cited ∩ expected\| / \|cited\|; `None` if no citations |
| **citation_faithfulness** | `cited_doc_keys ⊆ retrieved_doc_keys` (bool) |
| **temporal_correctness** | `timeline` only: answer_correctness ∧ ¬forbidden_violation; else `None` |
| **supersession_correctness** | `superseded` only: keywords hit ∧ ¬forbidden (superseded facts); else `None` |
| **abstention_accuracy** | `abstained == expected_abstain` (bool) |

`aggregate(rows)` reports per-category and overall means for applicable metrics, plus **latency p50/p95** and **total token cost** when rows include `latency_ms` and `tokens_used`.

---

## Hackathon execution order

1. Land Wave 1 (fixtures F2 + this plan F1) and Wave 2 (runner F3, CLI F4).
2. Wave 3 live baseline (F6): ingest → extract → lifecycle → consolidate → benchmark with Qwen; write first report from `baseline-template.md`.
3. Stretch only after green `nexus_synthetic` run: LoCoMo/LongMemEval download + conversion; BEAM/Memora adapters.

## Success criteria (submission)

- Repeatable `nexus eval memory run` producing JSONL + Markdown with all F5 metrics broken out by category.
- Demonstrated strengths: grounded citations, abstention, multi-doc retrieval.
- Honest limits documented: no external benchmark adapters; supersession/thesis scores require E1–E3 pipeline; conversational long-term memory (LoCoMo/LongMemEval native format) deferred.