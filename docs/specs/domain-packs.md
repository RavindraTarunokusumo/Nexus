# Domain Pack Spec

## Purpose

Domain packs adapt source material to Nexus without fragmenting the core data model.

The MVP uses a simple YAML format. Later versions can promote packs to Python modules if configuration alone is insufficient.

For the v3 telos-based purpose-grammar contract and the AI-domain extraction scheme, see [2026-05-29-ai-domain-pack-extraction-scheme-design.md](../superpowers/specs/2026-05-29-ai-domain-pack-extraction-scheme-design.md).

## MVP Domain Pack Format

```yaml
id: personal_ai_tech
name: Personal AI Technology Analyst

topics:
  - AI agents
  - open-source LLMs
  - inference infrastructure

claim_types:
  - model_release
  - benchmark_result
  - product_launch

brief_sections:
  - top_developments
  - research_updates
  - tools_and_repos

models:
  t2: openrouter-cheap-model
  t3: openrouter-strong-model
```

## MVP Pack Responsibilities

The `personal_ai_tech` pack defines:

- accepted source types and source defaults
- topics used for tagging and filtering
- claim taxonomy
- brief sections
- model routing preferences
- extraction prompt variables
- synthesis prompt variables

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

| Capability | Responsibility |
|---|---|
| Segmenter | Split sources into spans, including visual descriptions later |
| Entity Extractor | Domain-aware named entity extraction |
| Claim Extractor | Claims using domain taxonomy |
| Signal Extractor | Optional domain-specific event creation |
| Normaliser | Canonical claims, time fields, and half-life |
| Deduplicator | Domain equivalence rules |
| Ranking Hooks | Hybrid score, recency, novelty, credibility weights |
| Budgets | Maximum claims, signals, and relations |
| Retention Policy | Hot/warm/cold windows and consolidation rules |
| Image Policy | Which images to describe, enrich, or ignore |

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
