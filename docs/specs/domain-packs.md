# Domain Pack Spec

## Purpose

Domain packs adapt source material to Nexus without fragmenting the core data model.

The MVP uses a simple YAML format. Later versions can promote packs to Python modules if configuration alone is insufficient.

For the v3 telos-based purpose-grammar contract and the AI-domain extraction scheme, see [2026-05-29-ai-domain-pack-extraction-scheme-design.md](../superpowers/specs/2026-05-29-ai-domain-pack-extraction-scheme-design.md).

## Domain Pack Format

The production pack (`app/domain_packs/personal_ai_tech.yaml`) is a full **v3 purpose-grammar pack**. For the canonical shape and field semantics, see the [v3 contract spec](../superpowers/specs/2026-05-29-ai-domain-pack-extraction-scheme-design.md). The pack is loaded at runtime by `app/domain_packs/loader.py` using a Pydantic v2 model.

A minimal v3 pack skeleton looks like:

```yaml
id: personal_ai_tech
version: "3.0"
telos:
  purpose: "..."
  user_role: "..."
  primary_question: "..."

source_type_profiles:
  ai_news_article:
    claim_budget: 5
    # ...

semantic_object_families:
  - name: model_release
    object_types: [...]
    mvp_claim_type: model_release
    required_fields: [...]
    # ...

salience_policy:
  threshold: 0.3
  # ...

# Legacy top-level keys (back-compat only — not used by the production extraction path)
topics: [...]
claim_types: [...]
brief_sections: [...]
models: {t2: ..., t3: ...}
```

The legacy top-level keys (`topics`, `claim_types`, `brief_sections`, `models`) are preserved at the bottom of the YAML for back-compat with tooling that has not yet been ported to v3.

## Pack Responsibilities (v3)

The `personal_ai_tech` pack now defines:

- **Telos** — purpose, user role, and primary question that govern extraction focus
- **Source-type profiles** — 10 profiles (e.g. `ai_news_article`) each with per-source claim budgets and extraction parameters
- **Semantic-object families** — 10 families, each with `object_types`, `core_type_mapping`, `mvp_claim_type` (the projection target in the legacy claims table), `required_fields`
- **Salience policy** — minimum salience threshold and triage rules
- **AI facet list** — domain-specific facet keys injected into the extraction prompt
- **Core + domain relations** — relation grammar for the knowledge graph
- **Epistemic policy** — how to handle uncertainty and unverified claims
- **T0–T4 routing** — tier assignment rules per object type and salience
- **Per-source budgets** — maximum objects per span per source type
- **Retention windows** — hot/warm/cold tiering
- **Retrieval intents + hybrid weights** — per-intent BM25/vector balance
- **Context assembly** — how retrieved objects are ranked and truncated for synthesis
- **Evaluation contract** — target metrics (e.g. `mvp_claim_type_projection_accuracy > 0.90`)

## Initial Claim Taxonomy

| Claim Type | Description |
|---|---|
| `model_release` | Model launch or update |
| `benchmark_result` | Quantitative benchmark |
| `product_launch` | New tool or product |
| `pricing_change` | Pricing modification |
| `research_finding` | Scientific or technical finding |
| `infrastructure_update` | Infra/system news |
| `security_issue` | Vulnerability or safety issue |
| `funding_event` | Funding, acquisition, partnership |
| `regulation` | Policy or regulatory update |
| `forecast` | Prediction or speculation |
| `other` | Fallback |

## Broader PoC Domain Pack Contract

The long-term PoC describes richer domain packs with these capabilities:

| Capability | Responsibility | Status |
|---|---|---|
| Segmenter | Split sources into spans, including visual descriptions later | Deferred |
| Entity Extractor | Domain-aware named entity extraction | Live (facets in SemanticObject) |
| Claim Extractor | Claims using domain taxonomy | Live (telos-aware semantic-object path, Phase A) |
| Signal Extractor | Optional domain-specific event creation | Deferred |
| Normaliser | Canonical claims, time fields, and half-life | Deferred |
| Deduplicator | Domain equivalence rules | Deferred |
| Ranking Hooks | Hybrid score, recency, novelty, credibility weights | Live (retrieval intents + hybrid weights in pack) |
| Budgets | Maximum claims, signals, and relations | Live (per-source budgets + enforce_budgets, Phase A) |
| Retention Policy | Hot/warm/cold windows and consolidation rules | Live (retention windows in pack; DB tiering deferred to Phase B) |
| Image Policy | Which images to describe, enrich, or ignore | Deferred |
| Lifecycle / semantic_capsules table | Native v0.7 DB storage | Deferred to Phase B |

## Extraction Budgets

Budgets are future-facing constraints that should guide implementation when domain packs become richer:

| Domain | Claims/Source | Signals/Source | Relations/Claim |
|---|---:|---:|---:|
| Research paper | 15-25 core plus 10 secondary, cap 35 | 0-2 | 10 |
| Trading news article | 1-3 event plus 0-3 impact, cap 8 | 1 | 5 |
| Trading earnings/filing | 3-10, cap 15 | 1-3 | 5 |

The MVP should enforce a simpler per-document maximum once extraction is implemented to prevent runaway claim generation.

## Cross-Domain Policy

Cross-domain linking is deferred. When implemented, it should require:

- explicit entity overlap
- a higher similarity threshold than within-domain linking
- separate scheduled processing
- reviewable relation outputs

This prevents unrelated domains from generating noisy links.
