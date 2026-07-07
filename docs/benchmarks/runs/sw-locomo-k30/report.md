# LoCoMo Report

Full-conversation framing: each conversation's sessions are ingested once through the full pipeline (ingest -> extract -> cross-doc relations -> lifecycle -> consolidate); every selected question for that conversation is then answered against the same ingested state -- no per-question re-ingestion, unlike the LongMemEval adapter.

Judge-model caveat: scores use `qwen3.7-max` (Nexus T3) via an LLM-judge yes/no protocol, not the official LoCoMo repo's F1/ROUGE/exact-match scripts. Numbers are not directly comparable to published LoCoMo leaderboard results.

Category legend: 1=multi_hop, 2=temporal, 3=open_domain, 4=single_hop, 5=adversarial (correct behavior is abstention; see run_locomo.py header comment for the mapping's provenance).

## Overall

| Metric | Value |
| --- | --- |
| accuracy | 0.500 |
| mean_latency_s | 18.700 |
| mean_tokens_used | 3921.3 |

## 1 (multi_hop)

| Metric | Value |
| --- | --- |
| n | 18 |
| accuracy | 0.389 |

## 2 (temporal)

| Metric | Value |
| --- | --- |
| n | 23 |
| accuracy | 0.652 |

## 3 (open_domain)

| Metric | Value |
| --- | --- |
| n | 5 |
| accuracy | 0.000 |

## 4 (single_hop)

| Metric | Value |
| --- | --- |
| n | 2 |
| accuracy | 1.000 |
