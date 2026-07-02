# Nexus Synthetic Memory Benchmark Fixtures

Fictional-but-realistic AI-technology corpus and question set for the `personal_ai_tech` domain pack. All company and model names are invented so answers cannot leak from model priors about real vendors.

Domain: `personal_ai_tech` (from `app/domain_packs/personal_ai_tech.yaml` metadata.domain).

## Files

| File | Description |
|------|-------------|
| `corpus.jsonl` | 14 source documents (one JSON object per line) |
| `questions.jsonl` | 22 evaluation questions (one JSON object per line) |

## Corpus schema (`corpus.jsonl`)

Each line is a single JSON object with exactly these fields:

| Field | Type | Description |
|-------|------|-------------|
| `doc_key` | string | Stable identifier referenced by `expected_doc_keys` in questions |
| `title` | string | Human-readable document title |
| `url` | string | Unique fictional HTTPS URL used to map citations back to `doc_key` during benchmark runs |
| `source_type` | string | One of the pack's `metadata.supported_source_types` |
| `published_at` | string | ISO 8601 UTC timestamp (`YYYY-MM-DDTHH:MM:SSZ`) |
| `text` | string | Full document body (300–900 words, dense factual content) |

### Supported `source_type` values

From `personal_ai_tech` pack: `ai_news_article`, `model_release_note`, `research_paper_or_report`, `benchmark_report`, `product_or_tool_announcement`, `pricing_or_terms_update`, `security_or_safety_disclosure`, `policy_or_regulation_update`, `funding_or_company_update`, `forecast_or_opinion`.

## Question schema (`questions.jsonl`)

Each line is a single JSON object with exactly these fields:

| Field | Type | Description |
|-------|------|-------------|
| `question_id` | string | Unique question identifier |
| `category` | string | One of the categories below |
| `question` | string | Natural-language query posed to the chat system |
| `expected_answer_keywords` | array of string | Lowercase substrings a correct answer should contain |
| `forbidden_keywords` | array of string | Lowercase substrings that must not appear (stale or rumored facts) |
| `expected_doc_keys` | array of string | Corpus `doc_key` values that should be cited or retrieved |
| `expected_abstain` | bool | Whether the system should return insufficient-evidence abstention |
| `notes` | string | Rationale for scoring expectations (not shown to the model) |

All keywords in `expected_answer_keywords` and `forbidden_keywords` are lowercase.

## Question categories

| Category | Purpose | Scoring notes |
|----------|---------|---------------|
| `timeline` | Model releases, deprecations, and dated events | `temporal_correctness` requires expected keywords and no forbidden hits |
| `multi_doc` | Facts spanning two or more documents | `evidence_recall_at_k` measures overlap of cited vs expected doc keys |
| `superseded` | Current value after a newer document replaces an older one | `supersession_correctness` penalizes forbidden (superseded) keywords |
| `authority_conflict` | Tertiary rumor vs primary official statement | Answers should follow primary sources; forbidden keywords capture rumor text |
| `thesis` | Investable narrative supported by ≥3 corpus docs | Tests retrieval of jointly supporting evidence (e.g. small-model inference cost collapse) |
| `abstention` | Plausible questions with no corpus support | `expected_doc_keys` is `[]`, `expected_abstain` is `true` |

## Doc key to URL mapping

The benchmark runner builds a URL index from `corpus.jsonl`. Chat citations return document URLs; the runner maps each URL back to its `doc_key` for scoring.

| doc_key | url |
|---------|-----|
| `lumina-spark-1-0-release` | https://docs.lumina-ai.example/releases/luminaspark-1-0 |
| `lumina-spark-1-0-benchmark` | https://evals.lumina-ai.example/reports/luminabench-mmlu-2025-10 |
| `lumina-edge-quant-research` | https://arxiv.lumina-research.example/abs/2510.04412 |
| `lumina-spark-1-5-release` | https://docs.lumina-ai.example/releases/luminaspark-1-5 |
| `lumina-api-pricing-nov-2025` | https://pricing.lumina-ai.example/rate-cards/2025-11 |
| `lumina-orion-edge-announcement` | https://products.lumina-ai.example/orion-edge-npu-ga |
| `lumina-api-pricing-feb-2026` | https://pricing.lumina-ai.example/rate-cards/2026-02 |
| `lumina-spark-2-0-rumor` | https://rumorwire.example/ai/2026-02-28-luminaspark-scrape |
| `lumina-spark-2-0-release` | https://docs.lumina-ai.example/releases/luminaspark-2-0 |
| `lumina-spark-2-0-benchmark` | https://evals.lumina-ai.example/reports/luminabench-mmlu-2026-04 |
| `lumina-mmlu-forecast-expired` | https://outlook.meridian-analytics.example/forecasts/luminaspark-2-mmlu-q1-2026 |
| `lumina-spark-0-9-deprecation` | https://docs.lumina-ai.example/deprecations/luminaspark-0-9 |
| `lumina-inference-funding` | https://invest.lumina-ai.example/news/series-c-2026-05 |
| `lumina-small-model-thesis-news` | https://news.meridian-tech.example/articles/small-model-inference-2026-06 |

URLs are unique per document. Ingestion is idempotent by URL.

## Corpus narrative (internal consistency)

- **Model timeline**: LuminaSpark 1.0 (2025-09-15), 1.5 (2025-12-10), 2.0 (2026-03-18); LuminaSpark 0.9 preview deprecated 2026-05-01.
- **Benchmarks**: LuminaBench-MMLU 72.4% (1.0, Oct 2025) → 81.0% (2.0, Apr 2026 independent).
- **Pricing supersession**: LuminaSpark 1.0 output $2.40 (Nov 2025) → $0.85 (Feb 2026).
- **Authority conflict**: AI RumorWire tertiary claim of scraped medical records; LuminaSpark 2.0 primary release note denies it.
- **Expired forecast**: Meridian Analytics predicted 85% MMLU by 2026-03-31; window closed before June 2026 corpus date.
- **Thesis**: Sub-10B inference cost collapse via LuminaQuant-Edge research, API price cuts, and Orion Edge NPU hardware.

## Usage

```bash
nexus eval memory run --benchmark nexus_synthetic --k 8 --out docs/benchmarks/runs/<run-id>
```

Fixtures path resolves to `evals/memory/nexus_synthetic/` relative to the repository root.