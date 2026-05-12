# NEXUS — Agentic AI Environment
## Proof of Concept Architecture Document

**Version:** 0.6 — Multimodal Processing, Knowledge Integrity & Five-Tier Triage  
**Date:** April 2026  
**Author:** Arthur  

---

## 1. Vision

Nexus is an **operating environment** — a self-evolving, continually-learning, perpetually-adapting system where intelligence is a property of the environment itself.

The system ingests information from heterogeneous sources — text, images, figures, charts, and structured data — structures it into a **multi-layer knowledge hierarchy** — from raw sources through navigable spans, atomic claims, normalised signals, temporal clusters, structured theses, and decision artefacts — and enables both automated pipelines and human-directed agents to synthesize, correlate, and act on that knowledge across domains.

Three domain-specific interfaces — the **AI Analysis Core**, the **Trading Agent**, and the **Scientific Research Dashboard** — are views into the same underlying substrate. A **domain pack** architecture ensures each domain adapts extraction, normalisation, scoring, and thesis logic without fragmenting the core ontology.

The system lives on a **private VPS with zero public exposure**. A **hybrid runtime** splits responsibilities: a Python pipeline handles always-on data processing with deterministic scripts, local models, and cheap API calls; NanoClaw handles the conversational interface and on-demand research. A periodic **knowledge integrity audit** ensures the thesis layer remains coherent, non-contradictory, and free of blind spots — treating the knowledge base as a living system that requires active maintenance, not just accumulation.

---

## 2. Architectural Principles

**Multi-layer, not flat.** Claims are the atomic grounding layer, but they are not the only cognitive unit. The system's "thinking" operates primarily on higher-order objects — signals, clusters, theses, causal chains, scenarios — with retrieval and provenance providing a reversible pathway back to spans and sources whenever justification or re-evaluation is needed. Storing only atoms forces expensive context reconstruction. Storing only summaries loses grounding. The hierarchy preserves both.

**Ontology-first, adapter-extended.** A shared core ontology (source, span, entity, claim, relation, signal, thesis, provenance, confidence, time) stays stable across all domains. Domain-specific behaviour lives in **domain packs** — adapters that define extraction rules, claim taxonomies, normalisation, deduplication, scoring hooks, and thesis update logic. Extensions attach via namespaced JSONB (`extensions.research`, `extensions.trading`), never by redefining core objects.

**Claims must be atomic, assertable, and evidence-anchored.** A claim is a single proposition that can be supported, contradicted, extended, invalidated, attached to a thesis, or used in synthesis. Every claim links to ≥1 span. Every span links to a source anchor. Unresolved references ("it", "this approach") are resolved before storage or demoted to span-only notes. Conditions ("at 64k context", "under sanctions regime X") are captured in structured metadata.

**Dual-index retrieval.** A contextual span index provides broad semantic recall for exploratory search and evidence reconstruction. An enriched claim/signal index provides precision retrieval for proposition matching, contradiction/support search, and thesis updates. Chunks are not a retrieval unit — spans and claims are.

**Deterministic first, LLM as last resort.** Operations are classified into five cost tiers (T0–T4). If a regex, SQL query, vector distance, or deterministic script can do the job, it does. Local models handle embeddings, classification, and basic image understanding. Cheap API models handle structured extraction. Frontier LLMs are reserved for genuine reasoning: claim decomposition from complex prose, thesis synthesis, nuanced contradiction analysis, and natural language interaction. The most powerful frontier model is reserved for rare, high-stakes operations where quality differences are decision-critical.

**Multimodal-aware, text-first.** Sources contain images, charts, diagrams, and figures alongside text. Not all images carry information — stock photos and decorative elements are noise. The pipeline classifies visual content at ingestion (T1, free), produces text descriptions that enter the span layer as first-class objects, and reserves expensive multimodal analysis for high-value figures where the T1 description is insufficient. Claims extracted from figures follow the same provenance rules as text-derived claims.

**Event-driven pipeline.** When new data enters the system, it propagates upward through the hierarchy: source → spans → claims → signals → cluster updates → thesis re-evaluation. Redis pub/sub drives this chain. Pipeline workers react to events, not schedules (though ingestion itself is scheduled).

**Knowledge consolidates upward, lower layers compact behind it.** At projected ingestion rates (~2,100 sources/month), unchecked accumulation of spans, claims, and embeddings will degrade retrieval quality and exhaust storage within months. The hierarchy itself provides the solution: knowledge that has successfully propagated upward into theses and clusters has been "learned" by the system. The atoms beneath it transition from active retrieval targets to reference material. A deterministic lifecycle manager partitions data into hot/warm/cold tiers, consolidates redundant claims behind stable theses, and evicts span embeddings once their grounding role is fulfilled — while preserving provenance paths for audit and rehydration.

**The knowledge base is a living system, not an archive.** Accumulating knowledge without active maintenance degrades quality over time. The system periodically audits its own thesis layer for coherence — identifying contradictions between theses, stale hypotheses that should be invalidated, gaps in coverage, and cross-domain connections that the deterministic pipeline missed. This knowledge integrity audit is a scheduled, high-reasoning operation (T4) that treats the thesis layer the way a research librarian treats a collection: not just storing, but curating, linting, and surfacing what's missing.

---

## 3. Multi-Layer Knowledge Hierarchy

### 3.1 The Seven Layers

| Layer | Responsibility | Objects | Retrieval Role |
|-------|---------------|---------|----------------|
| **Source** | Preserve raw inputs, immutable provenance anchors | Source, Attachment, SourceMetadata | Audit trail, compliance, "go back to the record" |
| **Span** | Create navigable, citeable context windows | Span (paragraph/section/table/figure/figure_description) | High-recall semantic retrieval; evidence windows |
| **Primitive** | Convert text into comparable, linkable atoms | Entity, Claim, Relation | Precise matching; contradiction/support candidates |
| **Signal/Event** | Map claims into domain-relevant "what changed" units | Signal, Event, ImpactAssessment | Fast "what changed?" search; alerting |
| **Cluster/Timeline** | Aggregate evolving narratives | Cluster (topic/event), Timeline | Summaries, change detection, trend navigation |
| **Thesis/Model** | Maintain interpretable higher-order hypotheses | Thesis, CausalChain, Scenario | Decision support; hypothesis alerts |
| **Decision Artefact** | Emit actions, capture outcomes | DecisionMemo, TradeIdea, Postmortem, IntegrityReport | "Answer the question" and log outcome for feedback |

### 3.2 Layer Relationships

```
Sources (PDFs, articles, filings, notes, images)
  │
  ▼
Spans (paragraphs, sections, tables, figure descriptions)
  │                    ▲
  ▼                    │ grounding
Claims + Entities + Relations
  │                    ▲
  ▼                    │ evidence sets
Signals / Events (normalised "what changed")
  │
  ▼
Clusters / Timelines (temporal aggregation)
  │
  ▼
Theses / Causal Chains / Scenarios
  │
  ▼
Decision Artefacts (memos, actions, integrity reports, outcomes)
  │
  ├──────── write-back ──────── ▶ Sources (outcomes become new data)
  └──────── integrity audit ──── ▶ Theses (periodic T4 coherence check)
```

The key constraint: **every upward derivation preserves a downward path back to spans and sources.** Theses link to supporting claims. Claims link to spans. Spans link to source anchors. Any conclusion can be traced to its evidence.

---

## 4. Core Schema

### 4.1 Design Principles

The schema implements the hierarchy with five design choices:

**Core objects are domain-agnostic.** Source, Span, Entity, Claim, Relation, Signal, Thesis — these never change when a new domain is added.

**Domain packs extend via namespaced JSONB.** A research claim carries `extensions.research = {section: "experiments", benchmark: "SWE-bench", metric: "resolve_rate", value: 0.49}`. A trading signal carries `extensions.trading = {tickers: ["NVDA"], asset_class: "equity", event_type: "guidance_raise", half_life_hours: 48}`. The core table schema doesn't change.

**Confidence is multi-component.** A single opaque float is insufficient. Confidence decomposes into extraction confidence (did we parse it correctly?), grounding confidence (do spans strongly support the claim?), corroboration (independent sources agree?), and overall (transparent combination).

**Storage tier is explicit.** Every span and claim carries a `storage_tier` column (`hot`, `warm`, `cold`) that controls which HNSW partition it belongs to, whether its embedding is indexed, and whether the consolidation worker can compact it. Tier transitions are deterministic and logged.

**Visual content is text-proxied.** Images and figures produce text-description spans that enter the hierarchy like any other span. The `attachment_ref` field on spans links back to the original image file on disk. Claims extracted from figure descriptions follow the same provenance and anchoring rules as text-derived claims.

### 4.2 PostgreSQL Schema

```sql
-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "age";

-- Shared types
CREATE TYPE source_type AS ENUM (
    'paper', 'news', 'filing', 'web', 'note',
    'transcript', 'dataset', 'message'
);

CREATE TYPE span_type AS ENUM (
    'paragraph', 'section', 'table_row',
    'figure_caption', 'figure_description',
    'quote', 'note_block'
);

CREATE TYPE entity_type AS ENUM (
    'person', 'org', 'asset', 'method', 'dataset',
    'law', 'case', 'place', 'concept', 'event_type'
);

CREATE TYPE claim_type AS ENUM (
    'assertion', 'result', 'definition', 'comparison',
    'limitation', 'risk', 'prediction', 'obligation', 'prohibition'
);

CREATE TYPE relation_type AS ENUM (
    'supports', 'contradicts', 'refines', 'generalises',
    'specialises', 'causes', 'correlates', 'equivalent', 'about'
);

CREATE TYPE thesis_status AS ENUM (
    'active', 'watch', 'invalidated', 'archived'
);

CREATE TYPE storage_tier AS ENUM (
    'hot', 'warm', 'cold'
);

-- ============================================================
-- LAYER 1: SOURCES
-- ============================================================

CREATE TABLE sources (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_type     source_type NOT NULL,
    title           TEXT,
    uri             TEXT,
    published_at    TIMESTAMPTZ,
    ingested_at     TIMESTAMPTZ DEFAULT NOW(),
    language        TEXT DEFAULT 'en',
    content_ref     TEXT,                       -- path to raw content on disk
    provenance      JSONB NOT NULL DEFAULT '{}', -- derivation + attribution
    confidence      JSONB DEFAULT '{}',         -- multi-component
    extensions      JSONB DEFAULT '{}',         -- domain-pack namespace
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- LAYER 2: SPANS
-- ============================================================

CREATE TABLE spans (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id       UUID NOT NULL REFERENCES sources(id),
    span_type       span_type NOT NULL,
    text            TEXT NOT NULL,
    anchor          JSONB NOT NULL,             -- {page, start, end, selector}
    attachment_ref  TEXT,                       -- path to image/figure file on disk (NULL for text spans)
    description_method TEXT,                    -- 'original', 'vlm_local', 'vlm_haiku', 'vlm_sonnet' (for figure_description spans)
    sequence        INTEGER,                    -- ordering within source
    embedding       vector(768),                -- span-level embedding (Index A)
    domain_pack     TEXT,
    entity_ids      UUID[],                     -- extracted entities in this span
    storage_tier    storage_tier DEFAULT 'hot',  -- hot/warm/cold lifecycle
    tier_changed_at TIMESTAMPTZ DEFAULT NOW(),   -- when tier last transitioned
    extensions      JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- LAYER 3: PRIMITIVES
-- ============================================================

CREATE TABLE entities (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type     entity_type NOT NULL,
    canonical_name  TEXT NOT NULL,
    aliases         TEXT[] DEFAULT '{}',
    external_ids    JSONB DEFAULT '{}',          -- {arxiv: "...", ticker: "...", wikidata: "..."}
    embedding       vector(768),
    confidence      JSONB DEFAULT '{}',
    extensions      JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(canonical_name, entity_type)
);

CREATE TABLE claims (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id       UUID NOT NULL REFERENCES sources(id),
    claim_type      claim_type NOT NULL,
    claim_text      TEXT NOT NULL,
    span_ids        UUID[] NOT NULL,            -- ≥1 span anchoring this claim
    subject_entity_ids UUID[] DEFAULT '{}',
    object_entity_ids  UUID[] DEFAULT '{}',
    time            JSONB DEFAULT '{}',         -- {event_time, publication_time, valid_from, valid_to}
    normalised      JSONB DEFAULT '{}',         -- {predicate, condition, polarity, quantitative, numbers}
    provenance      JSONB NOT NULL DEFAULT '{}',
    confidence      JSONB DEFAULT '{}',         -- {extraction, grounding, corroboration, overall}
    domain_pack     TEXT,
    status          TEXT DEFAULT 'active',       -- active, consolidated, archived
    storage_tier    storage_tier DEFAULT 'hot',  -- hot/warm/cold lifecycle
    tier_changed_at TIMESTAMPTZ DEFAULT NOW(),   -- when tier last transitioned
    consolidated_into UUID,                     -- if consolidated, points to representative claim
    extensions      JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE relations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    from_claim_id   UUID NOT NULL REFERENCES claims(id),
    to_claim_id     UUID NOT NULL REFERENCES claims(id),
    relation_type   relation_type NOT NULL,
    evidence_span_ids UUID[] DEFAULT '{}',
    confidence      JSONB DEFAULT '{}',
    method          TEXT DEFAULT 'vector+haiku', -- T0, T1, T2, T3, T4, manual
    extensions      JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(from_claim_id, to_claim_id, relation_type)
);

-- ============================================================
-- LAYER 4: SIGNALS / EVENTS
-- ============================================================

CREATE TABLE signals (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    signal_type     TEXT NOT NULL,               -- domain-pack defined (e.g., "guidance_raise")
    time            JSONB NOT NULL,              -- {event_time, publication_time}
    affected_entity_ids UUID[] DEFAULT '{}',
    evidence_claim_ids  UUID[] NOT NULL,         -- grounding back to claims
    half_life_hours REAL,                        -- domain-pack controlled decay
    confidence      JSONB DEFAULT '{}',
    domain_pack     TEXT,
    extensions      JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- LAYER 5: CLUSTERS / TIMELINES
-- ============================================================

CREATE TABLE clusters (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cluster_type    TEXT NOT NULL,               -- 'topic', 'event', 'narrative'
    title           TEXT,
    member_claim_ids UUID[] DEFAULT '{}',
    member_signal_ids UUID[] DEFAULT '{}',
    entity_ids      UUID[] DEFAULT '{}',
    time_range      JSONB DEFAULT '{}',          -- {start, end}
    summary         TEXT,
    domain_pack     TEXT,
    extensions      JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- LAYER 6: THESES / MODELS
-- ============================================================

CREATE TABLE theses (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    thesis_text     TEXT NOT NULL,
    status          thesis_status DEFAULT 'active',
    supporting_claim_ids UUID[] DEFAULT '{}',
    refuting_claim_ids   UUID[] DEFAULT '{}',
    signal_ids           UUID[] DEFAULT '{}',
    invalidation_criteria JSONB DEFAULT '[]',
    confidence      JSONB DEFAULT '{}',         -- {extraction, grounding, corroboration, overall}
    domain_pack     TEXT,
    scope           JSONB DEFAULT '{}',          -- time horizon, asset scope, domain scope
    last_integrity_check TIMESTAMPTZ,           -- when T4 last audited this thesis
    extensions      JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE causal_chains (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title           TEXT,
    edges           JSONB NOT NULL,              -- [{from, to, type, confidence, evidence_span_ids}]
    thesis_ids      UUID[] DEFAULT '{}',
    domain_pack     TEXT,
    extensions      JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- LAYER 7: DECISION ARTEFACTS
-- ============================================================

CREATE TABLE decision_artefacts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    artefact_type   TEXT NOT NULL,               -- 'memo', 'trade_idea', 'postmortem', 'task', 'integrity_report', 'query_synthesis'
    title           TEXT,
    content         TEXT,
    thesis_ids      UUID[] DEFAULT '{}',
    outcome         JSONB,                       -- write-back: what happened
    domain_pack     TEXT,
    extensions      JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- DUAL-INDEX RETRIEVER
-- ============================================================

-- Index A: Span embeddings (high recall) — hot tier only
CREATE INDEX idx_spans_embedding_hot ON spans
    USING hnsw(embedding vector_cosine_ops)
    WHERE storage_tier = 'hot';

-- Index A: Span embeddings — warm tier (queried on expansion)
CREATE INDEX idx_spans_embedding_warm ON spans
    USING hnsw(embedding vector_cosine_ops)
    WHERE storage_tier = 'warm';

-- Note: cold spans have embedding set to NULL; no HNSW index needed.

CREATE INDEX idx_spans_source ON spans(source_id);
CREATE INDEX idx_spans_domain ON spans(domain_pack);
CREATE INDEX idx_spans_tier ON spans(storage_tier);

-- Index B: Claim/signal enriched embeddings (high precision)
CREATE TABLE claim_signal_embeddings (
    object_id       UUID PRIMARY KEY,
    object_kind     TEXT NOT NULL,               -- 'claim' or 'signal'
    embedding       vector(768),
    enrichment_text TEXT,                        -- stored for debugging/repro
    event_time      TIMESTAMPTZ,
    domain_pack     TEXT,
    key_entities    TEXT[],
    assets          TEXT[],
    storage_tier    storage_tier DEFAULT 'hot',
    extensions      JSONB DEFAULT '{}'
);

CREATE INDEX idx_cse_embedding_hot ON claim_signal_embeddings
    USING hnsw(embedding vector_cosine_ops)
    WHERE storage_tier = 'hot';
CREATE INDEX idx_cse_embedding_warm ON claim_signal_embeddings
    USING hnsw(embedding vector_cosine_ops)
    WHERE storage_tier = 'warm';
CREATE INDEX idx_cse_domain ON claim_signal_embeddings(domain_pack);
CREATE INDEX idx_cse_entities ON claim_signal_embeddings USING GIN(key_entities);
CREATE INDEX idx_cse_assets ON claim_signal_embeddings USING GIN(assets);
CREATE INDEX idx_cse_tier ON claim_signal_embeddings(storage_tier);

-- Full-text search (BM25 via Postgres FTS)
CREATE INDEX idx_spans_fts ON spans USING GIN(to_tsvector('english', text));
CREATE INDEX idx_claims_fts ON claims USING GIN(to_tsvector('english', claim_text));

-- ============================================================
-- KNOWLEDGE LIFECYCLE
-- ============================================================

CREATE TABLE consolidation_log (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    action          TEXT NOT NULL,               -- 'tier_transition', 'claim_consolidation', 'span_eviction', 'integrity_audit'
    target_ids      UUID[] NOT NULL,             -- affected object IDs
    target_kind     TEXT NOT NULL,               -- 'span', 'claim', 'claim_signal_embedding', 'thesis'
    from_tier       storage_tier,
    to_tier         storage_tier,
    consolidated_into UUID,                     -- for claim consolidation: the representative claim
    reason          TEXT,                        -- human-readable justification
    domain_pack     TEXT,
    metadata        JSONB DEFAULT '{}',          -- stats, thresholds used, counts
    executed_at     TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- OPERATIONAL
-- ============================================================

CREATE TABLE agent_log (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_name      TEXT NOT NULL,
    action          TEXT NOT NULL,
    input_refs      UUID[] DEFAULT '{}',
    output_refs     UUID[] DEFAULT '{}',
    tokens_used     INTEGER DEFAULT 0,
    model_used      TEXT,
    cost_usd        REAL DEFAULT 0,
    tier            TEXT,                        -- T0, T1, T2, T3, T4
    metadata        JSONB DEFAULT '{}',
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);
```

### 4.3 Schema Notes

**Embedding dimension: 768** — local `nomic-embed-text` via Ollama. $0 cost.

**HNSW over IVFFlat** — no training step required, better speed–recall tradeoff for this scale.

**JSONB for confidence, time, provenance, extensions** — flexible without schema migration. The multi-component confidence model (`{extraction, grounding, corroboration, overall}`) lives here. Domain-pack extensions (`extensions.research`, `extensions.trading`) live here. This avoids ontology fragmentation while enabling per-domain metadata.

**`span_ids` on claims is NOT NULL** — enforces Rule A: every claim must be evidence-anchored. No orphan claims.

**`storage_tier` on spans, claims, and claim_signal_embeddings** — controls HNSW partition membership. Partial indexes on `storage_tier = 'hot'` and `storage_tier = 'warm'` keep hot-path HNSW indices small and fast. Cold objects retain text for provenance but have their embeddings set to NULL (spans) or removed from the active index (claims).

**`consolidated_into` on claims** — when a consolidation pass compresses N corroborating claims into a representative, the N-1 non-representative claims point to the survivor. Provenance is preserved: following `consolidated_into` leads to the active claim, which retains the full evidence chain.

**`consolidation_log`** — every tier transition, consolidation action, and integrity audit is logged with reason, domain pack, and metadata (thresholds used, counts affected). This is the audit trail for both the lifecycle and integrity systems.

**`attachment_ref` on spans** — for `figure_description` spans, this points to the original image file on disk. For text spans, this is NULL. Enables query-time re-analysis: an agent can retrieve the original image via this path for deeper VLM inspection.

**`description_method` on spans** — records how a figure description was generated: `original` (human-written caption from the source), `vlm_local` (T1 Ollama VLM), `vlm_haiku` (T2), `vlm_sonnet` (T3). Downstream consumers can decide whether the description is trustworthy or needs re-analysis.

**`last_integrity_check` on theses** — tracks when the T4 knowledge integrity audit last examined each thesis. Theses not checked recently are prioritised in the next audit cycle.

**`artefact_type` on decision_artefacts** — now includes `integrity_report` (output of T4 audit) and `query_synthesis` (NanoClaw complex query results filed back into the knowledge base).

---

## 5. Dual-Index Retriever

### 5.1 The Two Indexes

**Index A — Span Index (recall).** Embeds paragraphs, sections, table rows, figure captions, and figure descriptions. Rich context. Use for: exploratory search ("what do we know about attention mechanisms?"), evidence reconstruction, thematic retrieval, finding source context for a claim.

**Index B — Enriched Claim/Signal Index (precision).** Embeds normalised claim text plus light structured context (entities, predicate, benchmark/metric or asset/event_type, conditions, polarity). Use for: proposition matching, contradiction/support search, thesis updates, structured synthesis.

**Why both?** Raw one-sentence claim embeddings are "embedding-thin" — "Performance improved by 12%" has almost no discriminative content without context. The enrichment template solves this without bloating the claim object.

### 5.2 Enrichment Templates

**Span embedding text:**
```
[Section: {section_title}] {span_text} [Entities: {entity_list}]
```

**Figure description span embedding text:**
```
[Figure: {figure_label}] {description_text} [Source: {source_title}] [Entities: {entity_list}]
```

**Claim/signal embedding text:**
```
{claim_text} | entities: {subject_entities}, {object_entities} | 
predicate: {normalised_predicate} | conditions: {conditions} | 
domain: {domain_pack}
```

For trading signals, append: `| tickers: {tickers} | event_type: {signal_type}`
For research claims, append: `| benchmark: {benchmark} | metric: {metric} | value: {value}`

### 5.3 Hybrid Scoring

Retrieval combines lexical (BM25) and dense (vector) signals, fused with Reciprocal Rank Fusion (RRF), then reranked with domain-specific weights.

```
score(x) =
  w_vec   * cosine_similarity(query, x.embedding) +
  w_bm25  * normalised_bm25(query, x.text) +
  w_ent   * entity_overlap(query_entities, x.entities) +
  w_asset * asset_overlap(query_assets, x.assets) +
  w_time  * recency_decay(x.event_time, half_life) +
  w_nov   * novelty(x, already_selected) +
  w_cred  * source_credibility(x.source_id)
```

**Domain-tuned weights:**

| Weight | Research | Trading |
|--------|----------|---------|
| w_vec | 0.35 | 0.25 |
| w_bm25 | 0.25 | 0.15 |
| w_ent | 0.20 | 0.15 |
| w_asset | 0.00 | 0.15 |
| w_time | 0.05 | 0.20 |
| w_nov | 0.10 | 0.05 |
| w_cred | 0.05 | 0.05 |

Research emphasises semantic similarity and entity overlap. Trading emphasises freshness and asset relevance.

**Novelty reranking (MMR):** Penalises redundancy — five Reuters rewrites of the same earnings beat should collapse to one result, not dominate the list.

**Temporal decay:** `weight = 2^(-Δt / half_life_hours)`. Trading signals decay in hours/days. Research claims decay over months. Domain pack controls `half_life_hours` per signal type.

### 5.4 Tiered Retrieval

Queries hit the **hot partition first**. If the result set falls below a relevance threshold (configurable per domain pack, default: fewer than K results above minimum similarity) or the query explicitly requests historical context, the retriever expands to the warm partition. Cold-tier data is never searched via embedding — it is accessible only by direct ID lookup for provenance drill-down, or via full-text search on retained `text` columns.

```
RETRIEVE(query):
  1. Search hot HNSW index (spans + claims)
  2. If |results above threshold| < K:
       Expand to warm HNSW index
       Merge + re-score
  3. Return top-N after MMR reranking
```

This keeps the hot HNSW index small (roughly the most recent partition window worth of data), preserving sub-millisecond recall even as total corpus size grows over months and years.

---

## 6. Domain Pack Architecture

### 6.1 What a Domain Pack Is

A domain pack is an **adapter** between a domain's source material and the shared core ontology. It translates domain-specific documents into Nexus's common substrate without changing the substrate itself.

### 6.2 Domain Pack Contract

Every domain pack implements:

| Capability | What It Does |
|-----------|-------------|
| **Segmenter** | `segment(source) → spans[]` — splits source into navigable spans, including figure descriptions from VLM |
| **Entity Extractor** | `extract_entities(spans) → entities[]` — domain-aware NER |
| **Claim Extractor** | `extract_claims(spans, entities) → claims[]` — with claim taxonomy |
| **Signal Extractor** | `extract_signals(claims) → signals[]` — optional, domain-dependent |
| **Normaliser** | Canonicalise claims, assign time fields, assign half-life |
| **Deduplicator** | Equivalence rules for claims and signals |
| **Ranking Hooks** | Hybrid score weights, recency policy, novelty policy |
| **Budgets** | Max claims/source, max signals/source, max relations/claim |
| **Retention Policy** | Partition boundaries, consolidation thresholds, eviction rules |
| **Image Policy** | Which image types to describe (T1), which to flag for deeper analysis (T2/T3) |

### 6.3 Extraction Budgets

Budgets keep storage bounded and force extractors to prioritise high-value atoms.

| Domain | Claims/Source | Signals/Source | Relations/Claim |
|--------|--------------|----------------|-----------------|
| Research (paper) | 15–25 core + 10 secondary, cap 35 | 0–2 | 10 |
| Trading (news article) | 1–3 event + 0–3 impact, cap 8 | 1 | 5 |
| Trading (earnings/filing) | 3–10, cap 15 | 1–3 | 5 |

### 6.4 Claim Taxonomies by Domain

**Research pack** extracts: problem claims, method claims, result claims, ablation claims, scope/limitation claims, comparative claims. Normalises around benchmark/metric/baseline/condition.

**Trading pack** extracts: event claims, causal-market claims, thesis-impact claims, sentiment/positioning claims, risk/invalidation claims. Normalises to event types (`guidance_raise`, `earnings_miss`, `rate_hold`). Attaches `half_life_hours` and `affected_assets`. Deduplicates aggressively within tight time windows.

### 6.5 Cross-Domain Linking Policy

Within-domain: automatic, moderate similarity threshold, runs on every new claim.

Cross-domain: separate pass, higher threshold, requires shared entity overlap. Only fires when two claims from different domain packs reference the same entity. This prevents noise (narrative pacing ≠ GPU pipelining) while preserving valuable cross-domain signals (attention mechanism paper → semiconductor positions).

### 6.6 Retention Policies by Domain

Each domain pack defines its own retention policy, controlling how aggressively knowledge compacts over time. The policy specifies three parameters per layer:

| Parameter | Research | Trading |
|-----------|----------|---------|
| **Hot window** | 90 days | 7 days |
| **Warm window** | 90–365 days | 7–90 days |
| **Cold threshold** | >365 days | >90 days |
| **Consolidation: min corroboration** | 0.7 | 0.8 |
| **Consolidation: min claim count** | 5 | 3 |
| **Consolidation: stability period** | 30 days (no contradictions) | 7 days |
| **Span eviction: embedding drop** | After warm window expires | After warm window expires |

Trading data compacts aggressively because most market signals lose relevance within days. Research compacts slowly because foundational claims remain useful for months. Both retain full text and provenance indefinitely — only embeddings and active index membership are affected by tier transitions.

### 6.7 Image Policies by Domain

Each domain pack specifies which image types carry information worth extracting.

| Domain | Describe at T1 | Flag for T2/T3 | Ignore |
|--------|----------------|----------------|--------|
| **Research** | Architecture diagrams, result plots, ablation tables, scaling curves | Multi-panel figures with specific numbers, complex flow diagrams | Author photos, logos, decorative |
| **Trading** | Earnings slides, analyst charts, data tables | Complex multi-series charts with axis labels and annotations | Stock photos, headshots, branding |

The domain pack's image policy is checked during segmentation. The segmenter calls the local VLM for classification, then either produces a `figure_description` span (T1), flags the image for richer extraction (queued for T2/T3), or skips it entirely.

---

## 7. Knowledge Lifecycle & Storage Management

### 7.1 The Problem

At ~2,100 sources/month, Nexus accumulates roughly:

| Object | Monthly Growth | 6-Month Accumulation |
|--------|---------------|---------------------|
| Spans | ~50K | ~300K |
| Claims | ~5K–10K | ~30K–60K |
| Span embeddings (768-dim, float32) | ~150 MB | ~900 MB |
| Claim/signal embeddings | ~30 MB | ~180 MB |
| HNSW index overhead (~1.5× vectors) | ~270 MB | ~1.6 GB |

The HNSW indices grow linearly. Retrieval latency degrades as index size increases. Signal-to-noise ratio drops as old, irrelevant results compete with fresh knowledge. Storage on a single VPS becomes non-trivial.

### 7.2 Design Principle

**Knowledge consolidates upward; lower layers compact behind it.** The hierarchy already encodes this: when a cluster of 40 claims from 25 sources all corroborate the same thesis, the system has "learned" that knowledge. The 40 individual claims are reference material, not active retrieval targets. The lifecycle system formalises this by managing three mechanisms: temporal partitioning, hierarchical consolidation, and span eviction.

### 7.3 Storage Tiers

Every span and claim exists in one of three tiers:

| Tier | Embedding Indexed? | Searchable Via | Transition Trigger |
|------|-------------------|----------------|-------------------|
| **Hot** | Yes (primary HNSW) | Vector + BM25 + direct | Default on creation |
| **Warm** | Yes (secondary HNSW) | Vector + BM25 + direct (on expansion) | Age exceeds hot window |
| **Cold** | No (embedding NULL for spans) | BM25 + direct ID lookup only | Age exceeds warm window OR consolidated |

Tier transitions are **deterministic (T0)** — driven by age thresholds from the domain pack's retention policy, not by LLM judgment. The consolidation worker runs as a scheduled job (daily for trading, weekly for research) and logs every action to `consolidation_log`.

### 7.4 Mechanism 1: Temporal Index Partitioning

Partial HNSW indexes on `storage_tier = 'hot'` and `storage_tier = 'warm'` split the vector search space by age. The retriever queries hot first and expands to warm only when results are insufficient (§5.4).

**Transition logic (T0):**

```python
# Pseudocode — runs as scheduled consolidation worker
def partition_by_age(domain_pack: DomainPack):
    policy = domain_pack.retention_policy
    now = utcnow()

    # Hot → Warm
    hot_to_warm = SELECT id FROM spans
        WHERE storage_tier = 'hot'
        AND domain_pack = domain_pack.id
        AND created_at < (now - policy.hot_window)

    UPDATE spans SET storage_tier = 'warm', tier_changed_at = now
        WHERE id IN hot_to_warm

    # Warm → Cold (span embedding eviction)
    warm_to_cold = SELECT id FROM spans
        WHERE storage_tier = 'warm'
        AND domain_pack = domain_pack.id
        AND created_at < (now - policy.warm_window)

    UPDATE spans SET storage_tier = 'cold', embedding = NULL, tier_changed_at = now
        WHERE id IN warm_to_cold

    # Log all transitions
    INSERT INTO consolidation_log (...)
```

The hot HNSW index is automatically kept small because Postgres partial indexes only include rows matching the `WHERE` clause. When a span transitions from hot to warm, it leaves the hot index and enters the warm index without any explicit index rebuild — the next `VACUUM` handles it.

### 7.5 Mechanism 2: Hierarchical Consolidation

When a group of claims corroborating the same thesis reaches stability, the consolidation worker compresses them: it selects the N most representative claims (highest confidence, best provenance diversity across distinct sources) and archives the rest.

**Consolidation trigger (all must be true):**

1. **Corroboration threshold met** — the thesis's confidence.corroboration ≥ domain pack's `min_corroboration`.
2. **Claim count exceeds minimum** — more than `min_claim_count` claims support the thesis.
3. **Stability period passed** — no new contradictions against the thesis in the last `stability_period` days.
4. **No active decision artefacts** — no open trade ideas or memos reference the candidate claims.

**Consolidation action (T0):**

```python
def consolidate_thesis_claims(thesis: Thesis, domain_pack: DomainPack):
    policy = domain_pack.retention_policy
    supporting = thesis.supporting_claim_ids

    if len(supporting) <= policy.min_claim_count:
        return  # not enough to consolidate

    # Rank claims by representativeness
    ranked = rank_by_representativeness(supporting,
        criteria=['confidence.overall', 'source_diversity', 'provenance_depth'])

    # Keep top N representatives (N = min_claim_count or ceil(len/3), whichever is larger)
    keep_count = max(policy.min_claim_count, ceil(len(supporting) / 3))
    representatives = ranked[:keep_count]
    to_archive = ranked[keep_count:]

    # Archive non-representative claims
    for claim_id in to_archive:
        UPDATE claims SET
            status = 'consolidated',
            storage_tier = 'cold',
            consolidated_into = representatives[0],
            tier_changed_at = now
        WHERE id = claim_id

        # Remove from active claim_signal_embeddings index
        UPDATE claim_signal_embeddings SET
            storage_tier = 'cold'
        WHERE object_id = claim_id

    # Update thesis to reference only representatives
    UPDATE theses SET
        supporting_claim_ids = representatives,
        updated_at = now
    WHERE id = thesis.id

    # Log
    INSERT INTO consolidation_log (
        action='claim_consolidation',
        target_ids=to_archive,
        target_kind='claim',
        consolidated_into=representatives[0],
        reason=f'Thesis {thesis.id} stable for {policy.stability_period} days, '
               f'{len(supporting)} claims consolidated to {keep_count}',
        domain_pack=domain_pack.id,
        metadata={
            'thesis_id': thesis.id,
            'original_count': len(supporting),
            'kept_count': keep_count,
            'corroboration': thesis.confidence.corroboration
        }
    )
```

**Key invariant:** archived claims are never deleted. Their `span_ids` still work. Their `consolidated_into` pointer leads to the active representative. Provenance is preserved — a human (or agent) can always trace from thesis → representative claim → `consolidated_into` back-pointers → all original claims → spans → sources.

### 7.6 Mechanism 3: Span Eviction

Spans are the largest storage consumer: full text plus 768-dim embeddings for every paragraph. After a span's age exceeds the warm window and its claims have been extracted, validated, and (where applicable) consolidated, the span's embedding is dropped from the vector index.

**What is preserved:** the span `text` (compressed on disk), the `anchor` (source location), the `attachment_ref` (for figure descriptions), and the `span_ids` references on claims. Provenance drill-down still works — a user clicking from claim → span → source will see the original text. What they lose is the ability to find that span via semantic search.

**What is recoverable:** if a thesis gets revisited or a new contradiction surfaces that requires re-examination of old evidence, the span text can be re-embedded (T1, free) and temporarily promoted back to warm. This is a manual or signal-triggered operation, not part of the regular consolidation cycle.

### 7.7 Rehydration

Cold data can be promoted back to warm when needed:

```python
def rehydrate_spans(span_ids: list[UUID]):
    """Re-embed cold spans and promote to warm tier for temporary re-examination."""
    spans = SELECT id, text, source_id FROM spans WHERE id IN span_ids AND storage_tier = 'cold'

    for span in spans:
        embedding = ollama_embed(span.text)  # T1, free
        UPDATE spans SET
            embedding = embedding,
            storage_tier = 'warm',
            tier_changed_at = now
        WHERE id = span.id

    INSERT INTO consolidation_log (
        action='rehydration',
        target_ids=span_ids,
        target_kind='span',
        from_tier='cold',
        to_tier='warm',
        reason='Manual or signal-triggered re-examination'
    )
```

Rehydration is expected to be rare — it fires when a thesis is reopened, a new contradiction surfaces against consolidated knowledge, or a human explicitly requests historical evidence exploration.

### 7.8 Storage Projections with Lifecycle

| Metric | Without Lifecycle (12 months) | With Lifecycle (12 months) |
|--------|------------------------------|---------------------------|
| Active HNSW vectors (spans) | ~600K | ~100K–150K (hot+warm) |
| Active HNSW vectors (claims) | ~60K–120K | ~20K–40K (hot+warm) |
| HNSW index size | ~4–5 GB | ~800 MB–1.2 GB |
| Retained text (compressed) | ~2 GB | ~2 GB (unchanged — text is never deleted) |
| Retrieval latency (p95) | Degrading | Stable |

The lifecycle system keeps the active index roughly fixed-size at steady state, bounded by the hot+warm windows rather than growing linearly with total ingestion.

---

## 8. Computational Triage

### 8.1 The Five Tiers

| Tier | What | Cost | When |
|------|------|------|------|
| **T0** | Python scripts, SQL, regex, math | Free | Always prefer |
| **T1** | Ollama local (nomic-embed, spaCy, classifiers, LLaVA VLM) | Free (compute) | Embeddings, NER, domain tagging, image classification/description |
| **T2** | Claude Haiku 4.5 | ~$0.001/call | Relationship classification, thesis evaluation, structured chart extraction |
| **T3** | Claude Sonnet 4.6 | ~$0.01-0.10/call | Claim decomposition, thesis synthesis, NL interaction, high-value figure analysis |
| **T4** | Claude Opus 4.6 (→ best frontier model when available) | ~$0.50-2.00/call | Weekly knowledge integrity audit, complex multi-source thesis synthesis, decision memo review |

**T4 design principle:** T4 never runs in the pipeline's main event loop. It runs as a **scheduled oracle** — a separate worker triggered by either a cron schedule (weekly integrity audit) or a complexity threshold (thesis synthesis when claim count > N and contradiction ratio > M). The call bundles maximum context because the value comes from the model seeing the whole picture. When a more capable frontier model becomes available (e.g., Claude Mythos/Capybara), it immediately replaces Opus at T4. The triage tier exists for the *role*, not the model — it is always occupied by the best available reasoning system.

### 8.2 Operation Mapping

| Operation | Tier | Notes |
|-----------|------|-------|
| Fetch sources (ArXiv, RSS, market APIs) | T0 | Deterministic API/library calls |
| Segment source into spans | T0 | Rule-based: heading detection, paragraph splitting, table parsing |
| Generate span embeddings | T1 | Ollama nomic-embed-text, local |
| Extract entities (NER) | T1 | spaCy en_core_web_trf |
| Classify domain tags | T1 | Ollama zero-shot or fine-tuned classifier |
| Compute source credibility | T0 | Rule-based scoring |
| **Classify image type** | **T1** | **Ollama LLaVA: chart/diagram/architecture/photo/decorative** |
| **Describe figure (basic)** | **T1** | **Ollama LLaVA: short text description of informational images** |
| **Describe figure (structured)** | **T2** | **Haiku vision: structured extraction from flagged complex charts** |
| **Decompose spans into claims** | **T3** | **Sonnet reads full body (not chunks), extracts per domain pack taxonomy. Includes T1 figure descriptions as spans; optionally includes high-value images directly** |
| Generate enriched claim embeddings | T1 | Embed enrichment template, local |
| Deduplicate claims | T0+T1 | Normalise text (T0) + cosine threshold (T1) |
| Find candidate related claims | T0 | pgvector cosine search (Index B) |
| Pre-filter candidates | T0 | Domain overlap + entity overlap SQL filters |
| Classify relationship type | T2 | Haiku: structured classify (supports/contradicts/refines/unrelated) |
| Create signals from claims | T0+T2 | Rule-based for obvious events; Haiku for ambiguous |
| Cluster signals into events | T0+T1 | HDBSCAN on embeddings + time windowing + entity overlap |
| Update thesis confidence | T2 | Haiku: compare signal against invalidation criteria |
| Build new thesis from cluster | T3 | Sonnet: synthesise hypothesis with invalidation criteria |
| Analyse nuanced contradiction | T3 | Sonnet: evaluate conflicting evidence, generate research question |
| Tier partitioning (hot→warm→cold) | T0 | SQL UPDATE by age threshold, scheduled |
| Claim consolidation | T0 | Deterministic: rank + archive behind representative |
| Span embedding eviction | T0 | SET embedding = NULL for cold spans |
| Rehydration | T1 | Re-embed cold spans on demand, local |
| **Knowledge integrity audit** | **T4** | **Opus (→ best frontier): weekly thesis-layer coherence check** |
| **Complex thesis synthesis** | **T4** | **Opus (→ best frontier): multi-source contradictions exceeding T3 complexity threshold** |
| **Decision memo review** | **T4** | **Opus (→ best frontier): stress-test high-stakes memos before action** |
| **Query-time figure re-analysis** | **T1/T2** | **NanoClaw tool invocation: retrieve image, describe on demand** |
| Gap analysis | T0 | SQL: entities with thin claim coverage |
| WhatsApp/Telegram queries | T3 | NanoClaw: natural language understanding + graph traversal |
| Dashboard data queries | T0 | SQL/Cypher to Postgres |

### 8.3 Claim Decomposition — The Full-Document Approach

Sonnet reads the **complete useful body** of a document — not chunks. An ArXiv paper (8-15K tokens) or a news article (1-3K tokens) fits trivially in Sonnet's 200K context window. Full-document reading allows Sonnet to resolve cross-references, understand how framing modifies claim strength, and avoid splitting propositions across boundaries.

For long documents (>50K tokens): segment by **logical structure** (headings, chapters, sections), not fixed-size windows. Each section goes to Sonnet as a complete semantic unit.

The extraction prompt is domain-pack specific. Research pack prompts ask for method/result/limitation claims with benchmark metadata. Trading pack prompts ask for event/impact/risk claims with affected assets and time sensitivity. Both use structured JSON output with the claim taxonomy from §6.4.

When a document contains figures that the T1 VLM has described, those descriptions are included as spans in the document context sent to Sonnet. For high-value figures where the T1 description is flagged as insufficient (complex multi-panel charts, dense data visualisations), the original image can be included directly in the Sonnet call — the marginal cost of adding one or two images to an already-scheduled T3 call is negligible compared to orchestrating a separate T2 vision sub-step.

### 8.4 Estimated Monthly Cost

| Component | Tier | Est. Cost |
|-----------|------|-----------|
| Embeddings + NER + classification + VLM descriptions (local) | T1 | $0 |
| Claim decomposition (~2,100 sources/month × Sonnet) | T3 | $30-50 |
| Relationship classification (~15K pairs/month × Haiku) | T2 | $5-10 |
| Thesis synthesis + contradiction analysis | T3 | $5-10 |
| Structured chart extraction (flagged high-value figures × Haiku) | T2 | $1-3 |
| Knowledge integrity audit (weekly × Opus) | T4 | $5-15 |
| Complex thesis synthesis + decision memo review (~5-10/month × Opus) | T4 | $5-15 |
| WhatsApp queries + research swarms (NanoClaw) | T3 | $15-25 |
| VPS (Hetzner CX32) | — | ~$16 |
| Knowledge lifecycle (consolidation + eviction) | T0 | $0 |
| Rehydration (rare, on-demand re-embedding) | T1 | $0 |
| **Total** | | **$80-145/month** |

---

## 9. Multimodal Processing

### 9.1 Design Principle

Not all images are equal. Research papers carry key results in figures that aren't fully restated in text — ablation plots, architecture diagrams, scaling curves. Trading sources include earnings slide decks and analyst charts with structured data the text only summarises. News articles are 90% stock photos with zero informational value. The pipeline must distinguish between these cases cheaply and route accordingly.

### 9.2 Two-Stage Pipeline

**Stage 1 — Ingestion-time triage (T1, free).** When the segmenter encounters an image in a source, a local VLM (Ollama LLaVA) performs two operations: (a) classifies the image type (`chart`, `diagram`, `architecture`, `data_table`, `screenshot`, `photo`, `decorative`), and (b) produces a short text description. The output becomes a span of type `figure_description` with `description_method = 'vlm_local'`, the `attachment_ref` pointing to the image file on disk, and the standard anchor linking back to the source location.

Most images stop here. Images classified as `photo` or `decorative` are discarded (no span created). Informational images get a usable text representation that feeds into Sonnet's claim extraction context.

**Stage 2 — Enrichment for high-value figures (T2/T3, on demand).** For images flagged by the domain pack's image policy as requiring deeper analysis — complex charts with specific numbers, multi-panel figures, dense data tables rendered as images — two options are available:

- **Include in T3 claim extraction call.** When Sonnet receives the full document for claim decomposition, high-value images are included alongside the text. This adds marginal cost to an already-scheduled call and keeps the pipeline simple. Preferred for PoC.
- **Separate T2 structured extraction.** Haiku vision produces a structured JSON extraction (axis labels, data points, trends) before the document reaches Sonnet. This is cheaper per image but adds a pipeline step. Defer to post-PoC unless T1 descriptions prove systematically inadequate.

### 9.3 Query-Time Re-Analysis

At query time, VLM-as-tool is the correct pattern. When a user asks NanoClaw something like "show me the scaling behaviour from that DeepSeek paper," the agent retrieves the relevant source, locates the figure via `attachment_ref` on the span, and invokes a VLM tool to describe or re-analyse the image in the context of the question.

This is implemented as a NanoClaw tool definition (`describe_figure`) that takes a source ID and figure reference, retrieves the image from disk, sends it to the local VLM (T1, free) or Haiku (T2, cheap), and returns the description as text. The T3 model orchestrating the conversation never sees the image bytes — it gets a text tool response. Clean separation.

### 9.4 Provenance for Visual Content

Claims extracted from figure descriptions follow the same provenance rules as text-derived claims: thesis → claim → span (figure_description) → source + attachment. The only difference is the span text was generated by a VLM rather than extracted from the document body. The `description_method` field makes this transparent — downstream consumers know the provenance of the description and can request re-analysis if needed.

### 9.5 Video (Future Extension)

Out of scope for PoC. The pattern would be: extract keyframes + audio transcript (T0/T1, deterministic tools), treat the transcript as a text source and keyframes as image spans, then apply the same two-stage VLM triage. Sprint 7+ problem.

---

## 10. Knowledge Integrity System

### 10.1 Motivation

Accumulating knowledge without active maintenance creates three failure modes that the deterministic pipeline cannot catch on its own:

- **Thesis drift** — theses that were valid when created but are no longer supported by current evidence, yet haven't triggered explicit contradictions.
- **Cross-thesis incoherence** — two active theses that implicitly contradict each other but were never compared because they entered through different domain packs or time windows.
- **Blind spots** — important entities or topics with thin coverage that the gap analysis (T0 SQL) identifies structurally but cannot evaluate for *significance*.

These require a reasoning model that can hold the full thesis layer in context and evaluate coherence, relevance, and completeness as a human domain expert would. This is the T4 tier's primary justification.

### 10.2 Inspired By

Karpathy's *LLM Knowledge Bases* methodology (April 2026) treats LLM-authored "health checks" as a first-class operation: periodic passes over a knowledge base to find inconsistencies, impute missing data, and surface candidates for new investigation. Nexus adopts this concept but applies it at the structured thesis layer rather than over flat markdown files — the health check operates on typed objects with provenance, not prose summaries.

A second insight from that methodology: **every exploration should compound**. When NanoClaw synthesises a complex cross-domain answer, that synthesis should be filed back into the knowledge base as a decision artefact (`artefact_type = 'query_synthesis'`), making it queryable in future sessions. This creates a write-back loop where queries enrich the graph rather than being ephemeral.

### 10.3 Weekly Integrity Audit (T4)

A scheduled weekly job (or on-demand trigger) sends the full active thesis layer to the T4 model with a structured audit prompt. The input includes:

- All active and watch-status theses with their confidence scores, supporting/refuting claim summaries, and associated signals.
- Recent signals not yet linked to any thesis (orphan signals).
- The T0 gap analysis output (entities with thin coverage).
- The consolidation log summary from the past week (what was compacted and why).

The T4 model produces a structured **integrity report** (stored as a decision artefact with `artefact_type = 'integrity_report'`):

```json
{
  "audit_date": "2026-04-05",
  "model_used": "opus-4.6",
  "findings": {
    "contradictions": [
      {
        "thesis_a": "uuid",
        "thesis_b": "uuid",
        "nature": "Thesis A assumes rising demand; Thesis B assumes demand contraction. Both active.",
        "recommended_action": "Investigate shared entity X — conflicting signals from domains research and trading."
      }
    ],
    "stale_theses": [
      {
        "thesis_id": "uuid",
        "reason": "Last supporting evidence is 45 days old. No recent signals. Consider transitioning to 'watch'.",
        "recommended_action": "watch"
      }
    ],
    "blind_spots": [
      {
        "entity": "entity_name",
        "domain": "research",
        "gap_type": "High entity frequency in recent sources but only 2 claims extracted. Possible extraction failure or underweighted topic.",
        "recommended_action": "Re-examine recent sources mentioning this entity; consider manual ingestion."
      }
    ],
    "cross_domain_connections": [
      {
        "description": "Research claims about efficient attention mechanisms may affect trading thesis on inference cost reduction for cloud providers.",
        "entities_shared": ["attention_mechanism", "inference_cost"],
        "recommended_action": "Create cross-domain link; evaluate thesis impact."
      }
    ],
    "orphan_signals": [
      {
        "signal_id": "uuid",
        "recommendation": "Signal describes a novel regulatory action. No existing thesis covers this. Consider thesis creation."
      }
    ]
  },
  "summary": "3 contradictions found, 2 stale theses flagged, 1 significant blind spot, 2 cross-domain connections surfaced."
}
```

### 10.4 Complexity-Triggered T4 Synthesis

Beyond the scheduled audit, T4 also fires for thesis synthesis when the complexity exceeds T3's reliable operating range. The trigger is a conjunction of conditions:

- More than N supporting claims from M+ distinct sources (default: N=15, M=5).
- Contradiction ratio > threshold (default: 20% of related claims are contradictions).
- Claims span 2+ domain packs (cross-domain synthesis).

When triggered, the T4 model receives the full claim cluster with evidence spans and produces the thesis with explicit invalidation criteria, confidence decomposition, and causal reasoning that T3 struggles with at this complexity level.

### 10.5 Decision Memo Review (T4)

When Nexus produces a decision memo or trade idea that will drive real action, a single T4 pass over the full evidence chain (thesis → claims → key spans) serves as a quality gate. The model reviews the memo for: completeness of invalidation criteria, whether confidence is justified by evidence, obvious counterarguments the pipeline missed, and whether the causal chain is warranted or merely narrative.

### 10.6 Write-Back Loop

When NanoClaw synthesises a complex answer — especially cross-domain queries that require combining evidence from multiple theses — the synthesis is stored as a decision artefact (`artefact_type = 'query_synthesis'`) with proper provenance linking to the theses and claims consulted. This ensures every deep exploration enriches the knowledge base rather than being lost when the chat session ends.

---

## 11. Hybrid Runtime

### 11.1 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         PRIVATE VPS (SSH-only)                   │
│                                                                 │
│  ┌──────────────────────────┐  ┌──────────────────────────────┐ │
│  │   PYTHON PIPELINE        │  │        NANOCLAW              │ │
│  │   (always-on worker)     │  │        (interface)           │ │
│  │                          │  │                              │ │
│  │  • Scheduled ingestion   │  │  • WhatsApp/Telegram UI     │ │
│  │  • Source → Span → Claim │  │  • Natural language queries  │ │
│  │  • VLM image processing  │  │  • On-demand ingestion       │ │
│  │  • Signal extraction     │  │  • Deep research swarms      │ │
│  │  • Clustering + timeline │  │  • Daily digest generation   │ │
│  │  • Thesis evaluation     │  │  • Figure re-analysis tool   │ │
│  │  • Event-driven synthesis│  │  • Query synthesis write-back│ │
│  │  • Knowledge lifecycle   │  │                              │ │
│  │  • Integrity audit (T4)  │  │  Reads/writes via FastAPI    │ │
│  │                          │  │  Container-isolated agents   │ │
│  │  asyncio + Redis pub/sub │  │  Claude Agent SDK (T3)      │ │
│  │  Ollama + spaCy + Haiku  │  │                              │ │
│  └────────────┬─────────────┘  └──────────────┬───────────────┘ │
│               └──────────┬─────────────────────┘                │
│                          ▼                                      │
│                   FastAPI (REST + WebSocket)                    │
│                          │                                      │
│           ┌──────────────┼──────────────┐                       │
│     ┌─────▼─────┐  ┌─────▼─────┐  ┌────▼────┐                  │
│     │ Postgres  │  │   Redis   │  │ Ollama  │                  │
│     │ +pgvector │  │ (pub/sub) │  │ (local) │                  │
│     │ +AGE      │  │           │  │ +LLaVA  │                  │
│     └───────────┘  └───────────┘  └─────────┘                  │
└─────────────────────────────────────────────────────────────────┘
```

### 11.2 Pipeline Data Flow

```
APScheduler trigger (daily/hourly)
  │
  ▼
FETCH sources (T0: arxiv, RSS, market APIs)
  │
  ▼
SEGMENT into spans (T0: rule-based paragraph/section splitting)
  │
  ├── For each image encountered:
  │     ├── Classify image type (T1: Ollama LLaVA)
  │     ├── If decorative/photo → skip
  │     ├── If informational → describe (T1: Ollama LLaVA) → figure_description span
  │     └── If high-value (per image policy) → flag for T2/T3 enrichment
  │
  ▼
PROCESS spans (including figure_description spans):
  ├── NER extraction (T1: spaCy)
  ├── Domain classification (T1: Ollama)
  ├── Span embedding (T1: Ollama nomic-embed)
  └── Source credibility (T0: rule-based)
  │
  ▼
DECOMPOSE claims (T3: Sonnet, full-document, domain-pack taxonomy)
  │   (includes T1 figure descriptions as text spans;
  │    optionally includes flagged high-value images directly)
  │
  ├── Enrich + embed claims (T1: enrichment template → Ollama)
  ├── Deduplicate (T0+T1: normalise + cosine threshold)
  └── Store claims + spans + entities → Postgres
  │
  ▼
Redis publish: "nexus:new_claims" ──────────────────┐
                                                    │
  ┌─────────────────────────────────────────────────┘
  ▼
LINK claims (T0: vector search → T0: pre-filter → T2: Haiku classify)
  │
  ├── Redis publish: "nexus:contradiction_detected" (if contradicts)
  └── Store relations → Postgres
  │
  ▼
CREATE signals (T0+T2: rule-based for obvious, Haiku for ambiguous)
  │
  ▼
CLUSTER signals (T0+T1: HDBSCAN + time window + entity overlap)
  │
  ▼
EVALUATE theses (T2: Haiku checks invalidation criteria)
  │
  ▼
DIGEST → NanoClaw WhatsApp message: "Morning digest: 23 claims, 2 contradictions, 1 thesis updated."
```

### 11.3 Knowledge Lifecycle Flow (Separate Schedule)

```
APScheduler trigger (daily for trading, weekly for research)
  │
  ▼
PARTITION by age (T0: SQL UPDATE storage_tier by retention policy)
  │
  ├── Hot → Warm: move spans + claims past hot window
  ├── Warm → Cold: set span.embedding = NULL, move to cold tier
  └── Log all transitions → consolidation_log
  │
  ▼
CONSOLIDATE claims (T0: deterministic)
  │
  ├── For each thesis meeting stability criteria:
  │     ├── Rank supporting claims by representativeness
  │     ├── Keep top N, archive remainder (status='consolidated', tier='cold')
  │     ├── Update thesis.supporting_claim_ids to representatives only
  │     └── Update claim_signal_embeddings tier
  └── Log all consolidations → consolidation_log
  │
  ▼
REPORT lifecycle stats → agent_log + optional digest
  ("Lifecycle: 1,200 spans warm→cold, 85 claims consolidated behind 3 theses")
```

### 11.4 Knowledge Integrity Flow (Separate Schedule)

```
APScheduler trigger (weekly, Sunday night)
  │
  ▼
GATHER thesis layer context (T0: SQL queries)
  │
  ├── All active + watch theses with confidence, support/refute summaries
  ├── Orphan signals (not linked to any thesis)
  ├── Gap analysis output (entities with thin coverage)
  └── Consolidation log summary from past week
  │
  ▼
INTEGRITY AUDIT (T4: Opus → best frontier model)
  │
  ├── Identify inter-thesis contradictions
  ├── Flag stale theses for status transition
  ├── Evaluate blind spot significance
  ├── Surface cross-domain connections pipeline missed
  └── Assess orphan signals for thesis creation candidates
  │
  ▼
STORE integrity report → decision_artefacts (artefact_type='integrity_report')
  │
  ▼
LOG audit → consolidation_log (action='integrity_audit')
  │
  ▼
DIGEST → NanoClaw WhatsApp message:
  "Integrity audit: 3 contradictions, 2 stale theses, 1 blind spot, 2 cross-domain connections."
```

---

## 12. Infrastructure

### 12.1 VPS Specification

| Component | Recommendation |
|-----------|---------------|
| Provider | Hetzner CX32 or CX42 |
| OS | Ubuntu 24.04 LTS |
| CPU | 4+ vCPUs (8 preferred for Ollama + LLaVA) |
| RAM | 16–32 GB |
| Storage | 160 GB+ NVMe SSD |
| Network | SSH-only, no public HTTP |

Cost: **€15-30/month.**

Note: LLaVA VLM via Ollama requires additional VRAM/RAM compared to text-only models. If RAM contention becomes an issue with concurrent embedding + VLM operations, consider upgrading to CX42 (32 GB) or scheduling VLM operations during off-peak hours.

### 12.2 Docker Compose

Postgres + pgvector + AGE, Redis, Ollama (with both nomic-embed-text and LLaVA models), FastAPI (api), Pipeline worker, Frontend. All services on internal Docker network. API and frontend bind to `127.0.0.1` only (SSH tunnel access). NanoClaw runs on host, connects to API at `localhost:8000`.

### 12.3 Access Patterns

- **Laptop:** SSH tunnel → `localhost:3000` (dashboard) + `localhost:8000` (API)
- **Phone:** WhatsApp/Telegram → NanoClaw → Nexus API
- **CLI:** SSH → `nexus-cli` commands
- **Claude Code:** MCP server on VPS, accessed via SSH tunnel

---

## 13. Implementation Roadmap

### Sprint 0 — VPS + Substrate (Week 1)

- [ ] Provision and harden VPS
- [ ] Deploy Docker stack (Postgres, Redis, Ollama)
- [ ] Pull Ollama models (nomic-embed-text, LLaVA) + spaCy model
- [ ] Run Alembic migrations (full schema from §4.2, including storage_tier, attachment_ref, description_method, last_integrity_check columns)
- [ ] Build ModelRouter (Ollama + Haiku + Sonnet + Opus)
- [ ] Verify: local embed, local NER, local classify, local VLM describe

### Sprint 1 — Pipeline: Ingestion + Spans + Claims (Week 2)

- [ ] Build research domain pack: segmenter (including image classification + VLM description), entity extractor, claim taxonomy, image policy, retention policy
- [ ] Build ingestion pipeline: fetch → segment (with VLM triage) → NER → classify → Sonnet decompose (with figure description spans) → store
- [ ] Build enrichment pipeline: enrichment template → embed → store in dual index
- [ ] End-to-end: 10 papers → spans + figure_description spans + claims + entities in DB
- [ ] Build deduplicator (normalise + cosine threshold)
- [ ] Track cost per operation in agent_log

### Sprint 2 — Pipeline: Synthesis + Signals (Week 3)

- [ ] Build Claim Linker: vector search (Index B) → pre-filter → Haiku classify
- [ ] Wire Redis pub/sub event chain
- [ ] Build signal extractor (research pack: paper_published signals)
- [ ] Build HDBSCAN clusterer for signal aggregation
- [ ] Build thesis evaluator (Haiku)
- [ ] Build thesis builder (Sonnet, manual trigger first)
- [ ] Verify provenance chain: thesis → claims → spans (including figure_description) → source + attachment

### Sprint 3 — API + NanoClaw + Trading Pack (Week 4)

- [ ] FastAPI routes: all core objects + dual-index search + pipeline status
- [ ] Hybrid search endpoint (BM25 + vector + domain-tuned scoring from §5.3)
- [ ] Tiered retrieval: hot-first query with warm expansion (§5.4)
- [ ] Build trading domain pack (segmenter, event claim taxonomy, signal extraction, image policy, retention policy)
- [ ] Install NanoClaw, configure WhatsApp
- [ ] Write NanoClaw skills: query, ingest, digest, describe_figure (VLM tool)
- [ ] Implement query synthesis write-back (complex NanoClaw answers → decision_artefacts)

### Sprint 4 — Interface (Weeks 5-6)

- [ ] React dashboard with three views
- [ ] Knowledge graph explorer (react-force-graph)
- [ ] Claim feed with provenance drill-down (claim → spans → source), including figure_description spans with image preview
- [ ] Storage lifecycle dashboard (tier distribution, consolidation history, index sizes)
- [ ] Cost monitor panel (including T4 usage tracking)
- [ ] Pipeline activity stream (WebSocket)

### Sprint 5 — Domain Views + Cross-Domain (Weeks 7-8)

- [ ] Trading dashboard: thesis list, signal stream, trade journal
- [ ] Research dashboard: paper feed, domain map, gap analysis, contradiction board
- [ ] Cross-domain linking (weekly pass, entity-overlap constraint)
- [ ] Notion MCP sync
- [ ] NanoClaw research swarm skill

### Sprint 6 — Self-Evolution + Lifecycle + Integrity + Evaluation (Weeks 9-10)

- [ ] **Knowledge lifecycle worker:** tier partitioning (hot→warm→cold by retention policy)
- [ ] **Claim consolidation worker:** stability check + rank + archive behind representatives
- [ ] **Span eviction:** embedding drop for cold spans
- [ ] **Rehydration endpoint:** re-embed and promote cold spans on demand
- [ ] **Knowledge integrity audit (T4):** weekly scheduled Opus pass over thesis layer, structured report output
- [ ] **Complexity-triggered T4 synthesis:** auto-trigger on high-complexity thesis clusters
- [ ] **Integrity report dashboard:** display audit findings, link to affected theses
- [ ] **Lifecycle monitoring:** consolidation_log queries, tier distribution metrics, index size tracking
- [ ] Engagement tracking → domain reweighting (T0)
- [ ] Source credibility updating (T0: Bayesian)
- [ ] Thesis outcome tracking (T0)
- [ ] Automated backup (pg_dump → Restic → B2)
- [ ] Evaluation: provenance integrity, dedup quality, retrieval metrics, cost tracking, lifecycle correctness, integrity audit quality

---

## 14. PoC Success Criteria

**Core mechanics:**
1. **Provenance integrity** — every claim links to ≥1 span; every span links to a source anchor. Full traceback from thesis to source works. Consolidated claims preserve traceback via `consolidated_into`. Figure-derived claims trace back through `figure_description` spans to `attachment_ref` images.
2. **Dedup quality** — duplicate news articles about the same event compress to one signal cluster with multiple sources.
3. **Budget enforcement** — no source produces more claims than domain pack budget allows.

**Retrieval:**
4. **Dual-index works** — span search returns relevant context windows; claim search returns precise proposition matches. Both are measurably better than using only one index.
5. **Tiered retrieval works** — hot-first queries return results with lower latency than full-index queries. Warm expansion correctly fires when hot results are insufficient.

**Synthesis:**
6. **50+ papers ingested** with claims decomposed, entities extracted, relationships mapped.
7. **Cross-domain query works** — "What entities appear in both ML architecture research and market signals?"
8. **At least one thesis** auto-generated from claim clusters with explicit invalidation criteria.
9. **Contradiction detection fires** on a real contradiction.

**Knowledge lifecycle:**
10. **Tier transitions execute correctly** — spans and claims move hot→warm→cold on schedule per retention policy.
11. **Consolidation compresses** — a stable thesis with 10+ supporting claims is consolidated to N representatives; archived claims retain provenance via `consolidated_into`.
12. **Span eviction works** — cold span embeddings are NULL; span text and provenance remain intact and accessible.
13. **Rehydration works** — a cold span can be re-embedded and promoted to warm on demand.
14. **Index size stays bounded** — hot HNSW index size does not grow linearly with total ingestion at steady state.

**Multimodal:**
15. **Image classification works** — the T1 VLM correctly classifies images as informational vs. decorative, with >80% agreement with manual labels on a test set of 50 images.
16. **Figure descriptions produce claims** — at least one claim extracted from a figure_description span traces back through provenance to the original image attachment.
17. **Query-time re-analysis works** — NanoClaw's `describe_figure` tool retrieves an image and returns a useful description.

**Knowledge integrity:**
18. **Integrity audit runs** — the weekly T4 pass produces a structured integrity report stored as a decision artefact.
19. **Audit surfaces real findings** — the integrity report identifies at least one stale thesis, one contradiction, or one blind spot that wasn't previously flagged by the deterministic pipeline.
20. **Write-back loop works** — a complex NanoClaw query synthesis is stored as a `query_synthesis` decision artefact and is retrievable in subsequent queries.

**Interface:**
21. **WhatsApp works** — query Nexus from phone via NanoClaw.
22. **Dashboard shows full provenance** — click thesis → supporting claims → evidence spans → source. Including through consolidated claims and figure_description spans.
23. **Lifecycle dashboard** — shows tier distribution, consolidation history, index sizes, and integrity audit history.

**Cost:**
24. **Monthly LLM cost under $145** for daily ingestion of ~20 papers + ~50 articles, weekly T4 integrity audit, and occasional T4 synthesis.

**The real test:**
25. **The graph reveals something you didn't know** — a connection, gap, or contradiction that wasn't obvious from reading individually.

---

## 15. Open Questions

1. **Source deletion** — cascading effects on claims, entity orphaning, thesis invalidation, temporal record vs. hard delete. The lifecycle system's `cold` tier partially addresses this (data is retained but not actively indexed), but explicit deletion semantics for user-requested removal remain unspecified.
2. **Gap analysis mechanics** — what constitutes a "gap," threshold tuning, weighting by thesis relevance vs. domain priority.
3. **Credibility scoring formula** — the rule-based sketch is a placeholder. Needs a real Bayesian model with proper priors and update mechanics.
4. **Consolidation representativeness ranking** — the `rank_by_representativeness` function needs a concrete formula. Candidate inputs: `confidence.overall`, number of distinct source origins, provenance depth, recency of the claim, entity coverage breadth. Weights TBD.
5. **Cross-tier provenance UX** — when a user drills down from a thesis through consolidated claims to cold spans, the interface needs to clearly communicate that some evidence is archived and may require rehydration for full semantic exploration. Design TBD.
6. **VLM model selection for Ollama** — LLaVA is the assumed default, but newer multimodal Ollama models may offer better classification/description quality. Needs benchmarking against a small test set of research figures and trading charts before committing.
7. **Integrity audit scope scaling** — as the thesis layer grows beyond what fits in a single T4 context window, the audit will need to be partitioned (by domain, by entity cluster, or by time window). Partitioning strategy TBD.
8. **Notion mirror as compiled readable layer** — Karpathy's methodology validates the value of a human-readable output layer auto-generated from structured knowledge. The Notion sync (Sprint 5) should be evaluated as a candidate for this role: thesis summaries, cross-domain connections, and integrity findings rendered as interlinked Notion pages with full provenance links back to the Nexus substrate.

---

## Appendix A — Naming

**Nexus** — from Latin *nexus* ("a binding together"). Other candidates: Substrate, Lattice, Mycelium, Cortex.

## Appendix B — Key Design Decisions to Revisit

| Decision | Current | Revisit When |
|----------|---------|-------------|
| Hybrid runtime | NanoClaw (interface) + Python pipeline | Pipeline exceeds single worker → add Celery |
| Embedding model | nomic-embed-text (768-dim, local) | Retrieval quality poor → mxbai-embed-large or OpenAI |
| Cheap LLM | Haiku 4.5 | Relationship classification <80% accuracy → upgrade |
| Frontier LLM (T3) | Sonnet 4.6 | Claim decomposition quality insufficient → test Opus |
| Frontier LLM (T4) | Opus 4.6 | Immediately replaced by best available model when released (e.g., Mythos/Capybara) |
| Local VLM | Ollama LLaVA | Image classification/description quality poor → test newer multimodal Ollama models |
| VLM pipeline strategy | T1 local for all; include high-value images in T3 Sonnet call | T1 descriptions systematically inadequate → add separate T2 Haiku vision step |
| Span segmentation | Rule-based (T0) | Complex layouts (multi-column PDFs) → add layout model |
| Cross-domain linking | Weekly pass, entity-overlap constraint | Too noisy or too quiet → tune threshold |
| Single VPS | All services on one box | RAM contention (especially with LLaVA) → split or upgrade to CX42 |
| BM25 implementation | Postgres FTS (ts_vector) | Need tuned BM25 → add pg_bm25 or ParadeDB |
| Hot window (research) | 90 days | Retrieval quality drops before 90 days → shorten; still relevant after → lengthen |
| Hot window (trading) | 7 days | Stale signals polluting results → shorten to 3 days; missing recent context → lengthen |
| Consolidation frequency | Daily (trading), weekly (research) | Over-consolidating → reduce frequency; index growth too fast → increase |
| Consolidation keep ratio | max(min_claim_count, ceil(N/3)) | Too aggressive → keep more; too conservative → keep fewer |
| Span eviction strategy | Drop embedding, retain text | Text storage also growing → add text compression or external cold storage |
| Integrity audit frequency | Weekly (Sunday night) | Too infrequent (missing contradictions) → increase; too expensive → reduce or partition |
| T4 complexity threshold | N=15 claims, M=5 sources, 20% contradiction ratio | Triggering too often → raise thresholds; missing complex cases → lower |
| Write-back loop scope | Complex NanoClaw queries only | Expand to all NanoClaw queries → risk noise; restrict to manual trigger → risk missing insights |
| Notion mirror role | Planned MCP sync (Sprint 5) | Evaluate as compiled readable layer per Karpathy pattern; if valuable, promote to primary human-reading interface |
| Interface layer | NanoClaw | Evaluate Hermes Agent as alternative gateway in Sprint 5-6 (better model routing, voice mode, skill marketplace) |

## Appendix C — Source Material

This document integrates findings from:

1. *Systematising Nexus PoC v3 as a Multi-Layer Knowledge System* — a deep research report covering: multi-layer knowledge hierarchies grounded in RDF/OWL/PROV standards, dual-index retrieval aligned with dense retrieval and RAG literature, domain pack adapter patterns, extraction budgets, recomposition mechanisms (clustering, thesis synthesis, causal chains, scenarios), hybrid scoring with rank fusion/MMR/temporal decay, and evaluation frameworks (BEIR, FEVER, FiQA, LexGLUE). The report's detailed JSON schemas, worked examples, and risk/mitigation analysis serve as reference specifications for implementation.

2. Karpathy's *LLM Knowledge Bases* methodology (April 2026) — an approach treating the LLM as a "research librarian" that compiles, lints, and interlinks a structured markdown wiki from raw sources. Key concepts adopted: health checks as a first-class operation (→ knowledge integrity audit), the write-back loop where every exploration compounds (→ query synthesis artefacts), and the compiled readable layer (→ Notion mirror validation). Key concepts *not* adopted: LLM-managed indexing (replaced by pgvector + HNSW at Nexus's scale), flat markdown as the knowledge substrate (replaced by typed objects with provenance), and single-model dependency (replaced by five-tier computational triage).

## Appendix D — Version History

| Version | Date | Focus |
|---------|------|-------|
| 0.1 | Feb 2026 | Initial architecture: flat claim store, single retriever |
| 0.2 | Feb 2026 | Domain packs, computational triage |
| 0.3 | Mar 2026 | Dual-index retriever, hybrid scoring |
| 0.4 | Mar 2026 | Multi-layer knowledge hierarchy (deep research integration) |
| 0.5 | Apr 2026 | Knowledge lifecycle & storage management (temporal partitioning, hierarchical consolidation, span eviction) |
| 0.6 | Apr 2026 | Multimodal processing (two-stage VLM pipeline), knowledge integrity system (T4 audit, write-back loop), five-tier computational triage (T4: Opus → best frontier model) |
