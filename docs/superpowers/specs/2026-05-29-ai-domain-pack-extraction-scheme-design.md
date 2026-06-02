# AI Domain Pack Extraction Scheme Design

## Goal

Define the extraction scheme for the AI technology domain pack under the Nexus v0.7 telos-based domain-pack model.

The scheme turns AI/tech source material into purpose-relevant semantic objects with evidence paths, epistemic status, facets, relations, and an MVP-compatible projection back to the current `claims` table.

## Source Inputs

This spec is based on:

- `nexus_poc_v07_telos_semantic.md` — v0.7 shift from claim-first extraction to telos-guided semantic capsules.
- `domain_pack_contract_v3_telos.md` — v3 domain pack contract, including telos, semantic object grammar, salience policy, semantic compressor, relation grammar, epistemic policy, routing, retention, and evaluation.
- `app/domain_packs/personal_ai_tech.yaml` — current MVP AI pack with topics, 11 claim types, brief sections, and model tiers.
- `evals/gold/claim_extraction/ai_tech_v2.yaml` — AI/tech claim-extraction gold set covering all 11 current claim types, including weak categories such as security, regulation, forecasts, research findings, and `other`.

## Current State

The current extraction pipeline is claim-first:

```text
Document
  -> Span
  -> LLM claim extraction
  -> Claim rows
  -> ClaimEvidence rows
```

The current AI pack defines topics and claim types:

```text
model_release
benchmark_result
product_launch
pricing_change
research_finding
infrastructure_update
security_issue
funding_event
regulation
forecast
other
```

This remains useful, but v0.7 requires a richer interpretation layer:

```text
Source
  -> Segment
  -> Semantic Object / Semantic Capsule
  -> Semantic Relation
  -> Epistemic State
  -> Domain Projection
  -> Retrieval / Brief / Thesis / Chat outputs
```

## Scope

Included:

- AI domain telos.
- AI source type profiles.
- Semantic object families and object types.
- Mapping from v0.7 semantic objects to the current 11 claim types.
- Salience and anti-salience rules.
- Segment-level extraction output schema.
- Facet policy.
- Relation grammar.
- Epistemic policy.
- Cost-tier routing.
- Budgets and lifecycle defaults.
- Evaluation contract.
- MVP compatibility plan.

Not included:

- Alembic migration design for `semantic_capsules`.
- Implementation plan or task breakdown.
- UI/dashboard design.
- Training or fine-tuning plan for T1/T2 models.
- Full YAML domain pack file.

## Design Decision

Use a two-layer extraction scheme:

1. **Canonical v0.7 layer:** extract AI semantic objects according to telos, salience, epistemic rules, and evidence requirements.
2. **MVP projection layer:** project accepted semantic objects into the existing `claims` and `claim_evidence` tables using the current 11 claim types.

This lets Nexus improve extraction quality and future readiness without blocking on the full semantic-capsule schema migration.

## AI Domain Telos

The AI domain pack covers source material whose main purpose is to report, explain, evaluate, promote, critique, regulate, secure, finance, or forecast AI systems and their surrounding ecosystem.

### Primary Purposes

- Report AI model, product, research, infrastructure, policy, safety, or market changes.
- Explain technical capabilities, constraints, costs, or tradeoffs.
- Present evidence about model performance, reliability, risk, adoption, or economics.
- Update expectations about AI ecosystem direction.
- Surface risks, vulnerabilities, regulatory obligations, and operational constraints.

### Secondary Purposes

- Promote a product, model, benchmark, company, or research agenda.
- Frame a release as strategically important.
- Compare products, models, or methods.
- Influence developer, buyer, investor, or policy perception.
- Recruit contributors, customers, developers, or ecosystem partners.

### Anti-Purposes

- Not all AI announcements are evidence of durable technical progress.
- Not all benchmark claims are independently verified.
- Not all product launches imply broad availability or production readiness.
- Not all forecasts are neutral predictions; many are persuasion or positioning.
- Not all safety or security claims prove actual safety, only reported controls or incidents.

### Reader Goals

- Identify what changed.
- Separate concrete facts from marketing or speculation.
- Track models, products, infrastructure, pricing, benchmarks, research findings, safety issues, and regulation.
- Preserve evidence for later grounded chat, briefs, comparisons, and trend analysis.
- Detect contradictions, supersession, and stale claims as the AI ecosystem moves quickly.

## Source Type Profiles

### `ai_news_article`

Purpose: report a recent AI ecosystem event or development.

High-value sections:

- headline and lead paragraph
- quoted announcement
- concrete dates, numbers, model/product names
- described impact, availability, pricing, regulation, or incident details

Low-value sections:

- generic background repeated across articles
- unsupported market color
- vague hype without specific event or evidence

Default processing: balanced.

### `model_release_note`

Purpose: describe a model release, update, capability, limitation, license, availability, or deployment mode.

High-value sections:

- model name/version
- release date
- provider
- modality
- context window
- license/availability
- benchmark tables
- safety notes
- deployment constraints

Default processing: balanced.

### `research_paper_or_report`

Purpose: present a research problem, method, experiment, result, limitation, or implication.

High-value sections:

- abstract contribution claims
- method
- experiments/results
- benchmark tables
- limitations
- safety or failure analysis

Default processing: deep for long papers; balanced for short reports.

### `benchmark_report`

Purpose: compare models or methods using tasks, metrics, datasets, or evaluation protocols.

High-value sections:

- benchmark name
- metric
- score
- task/dataset
- evaluation setup
- baseline/comparison
- reproducibility or caveat notes

Default processing: deep for numeric extraction; escalate ambiguous chart-only values.

### `product_or_tool_announcement`

Purpose: launch or update a tool, API, platform, developer workflow, integration, or service.

High-value sections:

- product name
- launch or GA status
- target users
- key capability
- pricing/availability
- integration details
- limitations

Default processing: balanced.

### `pricing_or_terms_update`

Purpose: communicate pricing, license, access, quota, rate limit, or terms changes.

High-value sections:

- old price and new price
- unit basis
- effective date
- affected product/model/API
- license/terms restrictions

Default processing: balanced.

### `security_or_safety_disclosure`

Purpose: disclose a vulnerability, misuse pathway, safety evaluation, incident, mitigation, or responsible-scaling change.

High-value sections:

- affected system
- vulnerability or risk type
- exploit/misuse condition
- impact
- mitigation status
- disclosure date
- severity/caveats

Default processing: deep when user-impacting or model-safety critical.

### `policy_or_regulation_update`

Purpose: describe an AI rule, law, standard, investigation, evaluation requirement, or governance action.

High-value sections:

- jurisdiction or regulator
- effective date
- obligation
- affected actors or model classes
- enforcement mechanism
- thresholds such as FLOPs, risk level, or deployment category

Default processing: balanced.

### `funding_or_company_update`

Purpose: report company financing, acquisition, partnership, restructuring, workforce move, or strategic change.

High-value sections:

- company
- amount/valuation
- investors/acquirer/partner
- date
- strategic use of funds or operational consequence

Default processing: cheap to balanced.

### `forecast_or_opinion`

Purpose: predict or argue about future AI capability, cost, adoption, labor impact, market size, safety risk, or regulation.

High-value sections:

- forecaster
- forecast target
- timeframe
- magnitude
- assumptions
- uncertainty or caveat

Default processing: balanced, with explicit speculative epistemic status.

## Semantic Object Families

### `model_system`

Purpose: preserve durable facts about AI models and model releases.

Object types:

- `model_release`
- `model_update`
- `capability_claim`
- `limitation_claim`
- `availability_change`
- `license_or_access_change`
- `modality_support`

Core type mapping:

- `model_release` -> `event`
- `model_update` -> `event`
- `capability_claim` -> `claim`
- `limitation_claim` -> `constraint`
- `availability_change` -> `state_change`
- `license_or_access_change` -> `state_change`
- `modality_support` -> `definition`

MVP claim projection:

- `model_release`, `model_update`, `modality_support` -> `model_release`
- `availability_change`, `license_or_access_change` -> `product_launch` or `other` depending source
- `capability_claim`, `limitation_claim` -> `research_finding` when evidence-backed, otherwise `other`

Required fields:

- provider or organization
- model/system name
- release/update status
- date or relative timing when present
- source refs

### `evaluation_evidence`

Purpose: preserve benchmark, metric, evaluation, comparison, and reproducibility evidence.

Object types:

- `benchmark_result`
- `metric_comparison`
- `baseline_comparison`
- `evaluation_method`
- `reproducibility_note`
- `failure_mode`
- `eval_caveat`

Core type mapping:

- `benchmark_result` -> `result`
- `metric_comparison` -> `comparison`
- `baseline_comparison` -> `comparison`
- `evaluation_method` -> `description`
- `reproducibility_note` -> `observation`
- `failure_mode` -> `risk`
- `eval_caveat` -> `constraint`

MVP claim projection:

- `benchmark_result`, `metric_comparison`, `baseline_comparison` -> `benchmark_result`
- `failure_mode`, `eval_caveat` -> `research_finding` or `security_issue` when safety-related
- `evaluation_method`, `reproducibility_note` -> `research_finding`

Required fields:

- evaluated model/system/method
- metric or task
- score or outcome when stated
- benchmark/dataset/context
- source refs

### `research_knowledge`

Purpose: preserve methods, findings, technical mechanisms, limitations, and future work from AI research sources.

Object types:

- `research_finding`
- `method_claim`
- `architecture_description`
- `training_or_data_claim`
- `efficiency_finding`
- `safety_finding`
- `limitation`
- `future_work`

Core type mapping:

- `research_finding` -> `claim`
- `method_claim` -> `definition`
- `architecture_description` -> `description`
- `training_or_data_claim` -> `claim`
- `efficiency_finding` -> `result`
- `safety_finding` -> `observation`
- `limitation` -> `constraint`
- `future_work` -> `question`

MVP claim projection:

- Most object types -> `research_finding`
- `efficiency_finding` about deployment/runtime infrastructure -> `infrastructure_update`
- `safety_finding` with vulnerability or misuse risk -> `security_issue`

Required fields:

- method/system/finding
- evidence or section context
- whether claim is reported by authors or independently verified
- source refs

### `product_tooling`

Purpose: preserve product, API, tool, workflow, integration, and developer-experience changes.

Object types:

- `product_launch`
- `feature_release`
- `api_update`
- `developer_tooling_change`
- `integration`
- `availability_rollout`
- `deprecation`

Core type mapping:

- `product_launch` -> `event`
- `feature_release` -> `event`
- `api_update` -> `state_change`
- `developer_tooling_change` -> `state_change`
- `integration` -> `event`
- `availability_rollout` -> `state_change`
- `deprecation` -> `state_change`

MVP claim projection:

- `product_launch`, `feature_release`, `api_update`, `developer_tooling_change`, `integration`, `availability_rollout` -> `product_launch`
- `deprecation` -> `other`

Required fields:

- product/tool/API name
- provider
- change type
- user/developer impact when stated
- availability or effective date when present
- source refs

### `infrastructure_compute`

Purpose: preserve AI compute, chip, cloud, inference, serving, data-center, edge, and deployment infrastructure changes.

Object types:

- `chip_or_accelerator_update`
- `cloud_instance_update`
- `inference_platform_update`
- `training_cluster_update`
- `edge_deployment_update`
- `data_center_update`
- `performance_per_cost_claim`
- `capacity_constraint`

Core type mapping:

- updates -> `event` or `state_change`
- `performance_per_cost_claim` -> `claim`
- `capacity_constraint` -> `risk`

MVP claim projection:

- All infrastructure update objects -> `infrastructure_update`
- `performance_per_cost_claim` can also support `pricing_change` if cost terms are explicit

Required fields:

- provider or infrastructure actor
- infrastructure component
- changed capability, capacity, price/performance, or availability
- source refs

### `economics_pricing`

Purpose: preserve price, cost, license, quota, usage, subscription, funding, valuation, and commercial model changes.

Object types:

- `pricing_change`
- `quota_or_rate_limit_change`
- `license_change`
- `funding_round`
- `valuation_change`
- `acquisition_or_partnership`
- `commercial_strategy`
- `cost_forecast`

Core type mapping:

- price/quota/license changes -> `state_change`
- funding/acquisition/partnership -> `event`
- commercial strategy -> `argument`
- cost forecast -> `claim`

MVP claim projection:

- `pricing_change`, `quota_or_rate_limit_change`, `license_change` -> `pricing_change`
- `funding_round`, `valuation_change`, `acquisition_or_partnership` -> `funding_event`
- `commercial_strategy`, `cost_forecast` -> `forecast` or `other`

Required fields:

- actor
- economic object
- amount/value/unit/change direction where stated
- effective date or announcement date when present
- source refs

### `safety_security`

Purpose: preserve AI security, safety, misuse, vulnerability, incident, mitigation, eval, and governance controls.

Object types:

- `security_vulnerability`
- `unauthorized_access_incident`
- `prompt_injection_issue`
- `model_misuse_vector`
- `safety_eval_result`
- `mitigation_or_patch`
- `responsible_scaling_change`
- `content_safety_policy_change`

Core type mapping:

- vulnerabilities/incidents/misuse vectors -> `risk`
- eval result -> `result`
- mitigation/policy/scaling change -> `state_change`

MVP claim projection:

- `security_vulnerability`, `unauthorized_access_incident`, `prompt_injection_issue`, `model_misuse_vector` -> `security_issue`
- `safety_eval_result`, `responsible_scaling_change`, `content_safety_policy_change` -> `regulation`, `security_issue`, or `other` depending source function

Required fields:

- affected system
- risk or incident type
- impact or potential impact
- mitigation status when present
- evidence caveat if unconfirmed
- source refs

### `policy_governance`

Purpose: preserve laws, regulations, standards, investigations, reporting requirements, evaluations, and governance obligations.

Object types:

- `law_or_rule_change`
- `regulatory_obligation`
- `government_investigation`
- `standards_update`
- `safety_institute_report`
- `company_policy_update`
- `compliance_threshold`

Core type mapping:

- rule/investigation/report/policy updates -> `event` or `state_change`
- obligation/threshold -> `constraint`

MVP claim projection:

- most objects -> `regulation`
- company-only voluntary policy updates -> `regulation` when safety-governance relevant, otherwise `other`

Required fields:

- jurisdiction/regulator/issuer
- affected actors or systems
- obligation/action/report
- effective or publication date when present
- source refs

### `forecast_outlook`

Purpose: preserve explicit predictions, timelines, market forecasts, capability forecasts, adoption forecasts, and uncertainty statements.

Object types:

- `capability_forecast`
- `cost_forecast`
- `market_size_forecast`
- `labor_impact_forecast`
- `adoption_forecast`
- `risk_forecast`
- `uncertainty_statement`

Core type mapping:

- forecasts -> `claim`
- uncertainty statements -> `constraint`

MVP claim projection:

- forecasts -> `forecast`
- uncertainty statements -> `forecast` only when attached to an explicit prediction; otherwise `other`

Required fields:

- forecaster/source
- forecast target
- timeframe
- magnitude/direction when stated
- uncertainty/caveat when stated
- source refs

### `ecosystem_event`

Purpose: preserve consequential AI ecosystem changes that do not fit narrower families.

Object types:

- `team_or_org_restructure`
- `open_source_project_launch`
- `community_or_foundation_event`
- `dataset_release`
- `moderation_or_policy_overhaul`
- `legal_dispute`
- `other_material_change`

Core type mapping:

- most objects -> `event` or `state_change`

MVP claim projection:

- default -> `other`
- `dataset_release` -> `research_finding` or `product_launch` depending telos
- `moderation_or_policy_overhaul` -> `security_issue` when harm/safety-driven, otherwise `other`

Required fields:

- actor
- event/change
- why it matters under the AI domain telos
- source refs

## Segment Extraction Output

For v0.7, the extractor should output candidate semantic objects using this shape:

```json
{
  "objects": [
    {
      "source_refs": ["span_id"],
      "domain": "personal_ai_tech",
      "source_type": "ai_news_article",
      "core_type": "event",
      "domain_family": "model_system",
      "domain_object_type": "model_release",
      "function": "reports a new AI model release relevant to ecosystem tracking",
      "text": "Mistral AI released Mistral Large 2 on July 24, 2024.",
      "original_text": "Mistral AI released Mistral Large 2 on July 24, 2024...",
      "facets": {
        "orgs": ["Mistral AI"],
        "models": ["Mistral Large 2"],
        "products": [],
        "benchmarks": [],
        "metrics": [],
        "datasets": [],
        "hardware": [],
        "jurisdictions": [],
        "dates": ["2024-07-24"],
        "money": [],
        "domain_terms": ["large language model"],
        "unknown_salient_terms": []
      },
      "epistemic": {
        "status": "asserted_by_source",
        "source_authority": "primary",
        "confidence": 0.86,
        "evidence_quality": "high",
        "uncertainty": null,
        "needs_escalation": false
      },
      "salience": 0.82,
      "mvp_claim_type": "model_release"
    }
  ]
}
```

For the MVP projection, each accepted object creates:

- one `claims` row using `text` as `claim_text`
- `mvp_claim_type` as `claim_type`
- `facets` split into `entities_json` and `topics_json`
- one or more `claim_evidence` rows from `source_refs`

## Salience Policy

### Preserve If

- The text reports a concrete model, product, infrastructure, pricing, policy, security, funding, benchmark, research, or forecast change.
- The text states a measurable performance, cost, capability, safety, or adoption result.
- The text names affected systems, organizations, users, developers, jurisdictions, hardware, models, or products.
- The text adds a limitation, caveat, uncertainty, or failure mode to a headline claim.
- The text changes interpretation of prior AI ecosystem state.

### Ignore If

- The text is generic AI background with no new source-specific information.
- The text contains promotional adjectives without concrete claim content.
- The text repeats a previous statement within the same source without adding detail.
- The text is a boilerplate safe-harbor or generic disclaimer unless tied to a specific forecast or risk.
- The text is purely biographical or corporate boilerplate without AI-domain consequence.

### Downgrade If

- The claim is abstract-only and not supported later in the source.
- The source is secondary and does not identify the primary announcement, report, or filing.
- The claim lacks date, actor, metric, affected system, or context needed for durable retrieval.
- The claim is a broad trend statement without a concrete evidence anchor.

### Escalate If

- Numeric benchmark, pricing, cost, or forecast values conflict within the source.
- A benchmark result is chart-only and exact values matter.
- A security incident affects secrets, user data, model weights, or critical infrastructure.
- A regulation or policy claim has legal obligations but ambiguous affected actors.
- A forecast is high-impact and lacks stated assumptions.
- The source appears to overstate a capability beyond its evidence.

## Facet Policy

Generic facets:

- people
- orgs
- places
- dates

AI-specific facets:

- models
- model_families
- products
- APIs
- benchmarks
- metrics
- datasets
- hardware
- cloud_platforms
- frameworks
- licenses
- jurisdictions
- regulators
- vulnerabilities
- safety_levels
- money
- compute_units
- modalities
- availability_channels

Facet extraction should not block semantic object creation. Unknown but salient AI terms should be stored in `unknown_salient_terms` rather than dropped.

Canonicalization should be conservative:

- normalize obvious aliases such as `GPT-4o` casing variants;
- preserve provider-specific model names exactly when ambiguous;
- do not merge similarly named models without evidence;
- keep benchmark version labels when present.

## Relation Grammar

Core relations:

- `supports`
- `contradicts`
- `refines`
- `qualifies`
- `weakens`
- `strengthens`
- `explains`
- `causes`
- `duplicates`
- `supersedes`
- `insufficient_evidence`

AI domain relations:

- `releases_model`
- `updates_model`
- `outperforms`
- `underperforms`
- `evaluates_on`
- `uses_benchmark`
- `improves_cost`
- `increases_cost`
- `expands_availability`
- `restricts_availability`
- `patches_vulnerability`
- `introduces_obligation`
- `changes_license`
- `raises_funding`
- `forecasts_capability`
- `forecasts_cost`
- `qualifies_capability_claim`
- `supersedes_prior_release`

Relation rules:

- A new version of the same model family may `supersede` prior release objects, but only when the source states replacement, deprecation, or successor status.
- A benchmark result can `support` a capability claim only when task, metric, and evaluated model match.
- A limitation, failure mode, or caveat should `qualify` related model capability, benchmark, or product claims.
- A price reduction `strengthens` affordability/cost-efficiency thesis objects but should not imply adoption without evidence.
- A safety disclosure can `weaken` deployment-readiness claims and `support` security-risk thesis objects.
- A regulation can `restrict_availability`, `introduce_obligation`, or `qualify` product launch claims.

## Epistemic Policy

### Source Authority

- Primary release note, paper, filing, law, regulator report, or vendor disclosure: `primary`.
- Reputable article summarizing primary material: `secondary`.
- Opinion, forecast, rumor, or unsourced aggregation: `tertiary` or `unknown`.

### Status Rules

- Release/product/funding/pricing events: `asserted_by_source`.
- Benchmark and research results: `asserted_by_source` unless independent replication is present.
- Vulnerabilities/incidents: `asserted_by_source`; set `uncertainty` if details are unconfirmed.
- Forecasts: `speculative` or `forward_looking`.
- Regulation: `asserted_by_source` for enacted rules; `forward_looking` for proposals.
- Opinionated trend claims: `inferred` only if the source explicitly argues the inference.

### Confidence Rules

Raise confidence when:

- source is primary;
- object has a direct quote or exact span evidence;
- benchmark includes task, metric, score, and model;
- pricing includes unit, old/new value, and effective date;
- regulation includes jurisdiction and affected actor.

Lower confidence when:

- source is secondary without primary link;
- claim is abstract-only;
- value is approximate or chart-derived;
- benchmark lacks setup details;
- forecast lacks assumptions;
- product availability is unclear.

### Contradiction Policy

- First attempt to refine scope before marking contradiction: different benchmark, model size, date, modality, region, customer tier, or license may explain apparent conflict.
- If the same actor reports a newer value for the same object, mark older object `superseded`.
- If two sources disagree on a security, regulation, benchmark, or pricing claim and both are high-authority, escalate to T3.
- Do not resolve rumors against primary disclosures without preserving both evidence paths.

## Model Routing

### T0

Use deterministic code for:

- source metadata parsing;
- URL/domain source-type hints;
- date and money normalization;
- span anchoring;
- schema validation;
- duplicate detection;
- MVP claim-type projection when domain object type is unambiguous.

### T1

Use cheap local models for:

- candidate object detection;
- basic source relevance;
- facet extraction;
- topic/domain-term tagging;
- low-stakes duplicate/near-duplicate candidates.

T1 may suggest objects but should not make final high-impact relation, contradiction, or escalation decisions.

### T2

Use T2 for:

- semantic object validation;
- ambiguous object family/type decisions;
- evidence sufficiency;
- safety/security/policy/forecast status assignment;
- relation classification that affects durable graph structure;
- correction prompts when JSON output fails validation.

### T3

Use T3 sparingly for:

- cross-source contradictions;
- high-impact security/regulatory interpretation;
- benchmark conflicts;
- trend synthesis;
- research-thesis updates;
- unclear forecasts with major downstream implications.

### T4

Reserve T4 for:

- integrity audit;
- high-stakes deployment/safety/regulatory decisions;
- major contradiction reports;
- domain-pack blind spot review.

## Budgets

Default first-pass budgets:

```yaml
max_segments_per_source: 500
max_semantic_objects_per_source: 80
max_semantic_objects_per_segment: 5
max_relations_per_object: 8
max_facets_per_object: 24
max_t2_calls_per_source: 20
max_t3_calls_per_source: 2
force_escalation_if_budget_exceeded: false
```

Source-type budget adjustments:

- `ai_news_article`: cap 12 objects.
- `model_release_note`: cap 25 objects.
- `research_paper_or_report`: cap 80 objects.
- `benchmark_report`: cap 60 objects.
- `pricing_or_terms_update`: cap 20 objects.
- `security_or_safety_disclosure`: cap 40 objects.
- `policy_or_regulation_update`: cap 40 objects.
- `forecast_or_opinion`: cap 25 objects.

## Retention And Lifecycle

Default lifecycle states:

- `candidate`
- `active`
- `confirmed`
- `qualified`
- `contradicted`
- `superseded`
- `stale`
- `archived`
- `rejected`

AI domain defaults:

- model releases stay active until superseded or deprecated;
- benchmark results stay active but become qualified when later evaluations narrow conditions;
- pricing and availability changes supersede older pricing/availability objects;
- forecasts become stale after their prediction window passes;
- security issues remain active until patched/mitigated, then become qualified or confirmed;
- regulations stay active until superseded, repealed, or replaced;
- funding/company updates remain historical events and do not decay, but their salience cools.

Suggested windows:

```yaml
hot_window_hours: 168
warm_window_days: 45
cold_after_days: 365
archive_after_days: null
```

## Retrieval Policy

Common AI query intents:

- `what_changed`
- `model_capability_summary`
- `benchmark_comparison`
- `product_or_tool_update`
- `pricing_and_cost_change`
- `infrastructure_capacity_update`
- `security_or_safety_risk`
- `regulatory_obligation`
- `research_trend`
- `forecast_outlook`
- `company_strategy_or_funding`

Retrieval priorities by intent:

- `what_changed`: recent high-salience events, state changes, security/regulatory updates, pricing changes.
- `model_capability_summary`: model release, capability claim, benchmark result, limitation, safety finding.
- `benchmark_comparison`: benchmark result, metric comparison, evaluation method, caveat, reproducibility note.
- `security_or_safety_risk`: vulnerability, incident, misuse vector, mitigation, safety eval, policy change.
- `regulatory_obligation`: law/rule, obligation, threshold, affected actor, effective date.
- `research_trend`: research finding, method claim, limitation, reproducibility note, related benchmark.

Hybrid score weights should default to:

```yaml
semantic_similarity: 0.35
domain_object_type_match: 0.20
source_authority: 0.12
recency: 0.12
salience: 0.11
relation_relevance: 0.07
evidence_quality: 0.03
```

Policy and security queries should increase `source_authority` and `evidence_quality`. News and "what changed" queries should increase `recency`.

## Context Assembly

For grounded answers and briefs, assemble context in this order:

1. Highest-salience directly relevant semantic objects.
2. Counter-evidence and caveats.
3. Superseding or superseded objects when relevant.
4. Source refs and excerpts.
5. Epistemic notes.

Intent-specific ordering:

- Benchmark questions: model -> task/benchmark -> metric -> score -> baseline -> caveat.
- Regulation questions: jurisdiction -> obligation -> affected actor -> date -> enforcement/caveat.
- Security questions: affected system -> vulnerability/incident -> impact -> mitigation -> uncertainty.
- Forecast questions: forecaster -> target -> timeframe -> magnitude -> assumption -> caveat.
- Research questions: problem -> method/finding -> evidence -> limitation -> future work.

## Normalization Policy

Canonical text should be concise but not stronger than the source.

Allowed rewrites:

- resolve local pronouns when the referent is unambiguous in the span;
- normalize dates and money units;
- compress marketing phrasing into factual statements;
- include model/product/provider names from source metadata if clearly applicable.

Forbidden rewrites:

- add external knowledge;
- infer causality not stated by the source;
- convert forecasts into facts;
- turn benchmark results into broad superiority claims without task scope;
- omit caveats that materially change interpretation.

## Deduplication And Consolidation

Same-source duplicate threshold: 0.92.

Cross-source near-duplicate threshold: 0.86, with stricter checks for:

- same actor;
- same model/product/system;
- same date or event window;
- same metric/unit when numeric;
- compatible epistemic status.

Preserve conflicting versions rather than merging when:

- benchmark score differs;
- pricing differs;
- source authority differs materially;
- one source is primary and another is rumor/secondary;
- caveats differ.

Consolidation targets:

- AI model release history.
- Benchmark trend by model family.
- Pricing trend by provider/model.
- Security incident timeline.
- Regulatory obligation map.
- Research trend or method family.

## Evaluation Contract

Object extraction metrics:

- semantic object schema validity
- grounded object rate
- salient object precision
- salient object recall
- unsupported object rate
- MVP claim-type projection accuracy

Relation metrics:

- relation accuracy
- contradiction recall
- supersession accuracy
- evidence sufficiency accuracy

Epistemic metrics:

- status assignment accuracy
- confidence calibration
- escalation recall on hard cases
- overconfidence rate on forecasts and benchmarks

Retrieval metrics:

- relevant semantic object recall
- counter-evidence inclusion
- citation grounding rate
- stale/superseded object handling

Minimum early thresholds:

```yaml
semantic_object_schema_validity: "> 95%"
grounded_object_rate: "> 95%"
unsupported_object_rate: "< 5%"
mvp_claim_type_projection_accuracy: "> 90%"
escalation_recall_on_hard_cases: "> 85%"
citation_grounding_rate: "> 95%"
```

Use `evals/gold/claim_extraction/ai_tech_v2.yaml` as the first compatibility fixture. Add new semantic-object gold sets before replacing the current claim-first evaluator.

## MVP Compatibility Plan

The first implementation should not require replacing the current persistence model.

Recommended phases:

1. Extend the AI domain pack YAML with v3 fields while keeping current `claim_types`.
2. Update extraction prompts to produce semantic-object-shaped JSON plus `mvp_claim_type`.
3. Validate semantic objects in memory, then project accepted objects into existing `claims`.
4. Store object metadata in `claims.topics_json` or `claims.entities_json` only as an interim compatibility bridge.
5. Add semantic-capsule tables later when the migration plan is ready.

This preserves the current API and eval harness while moving extraction semantics toward v0.7.

## Acceptance Criteria

- The AI domain pack has a defined telos, source profiles, semantic object families, salience rules, relation grammar, epistemic policy, routing policy, budgets, and evaluation contract.
- Every accepted semantic object has at least one source reference.
- Every accepted semantic object can be projected into one of the current 11 MVP claim types.
- Security, regulation, benchmark, pricing, and forecast objects carry explicit uncertainty and escalation rules.
- The scheme supports `ai_tech_v2` claim-extraction examples without losing current taxonomy coverage.
- The scheme is ready to drive an implementation plan without requiring a full schema migration first.
