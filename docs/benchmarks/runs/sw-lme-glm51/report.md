# LongMemEval Report

Oracle-retrieval framing: this run uses `longmemeval_oracle.json` evidence sessions only, measuring pipeline quality under oracle retrieval rather than full haystack recall.

Judge-model caveat: scores use `qwen3.7-max` (Nexus T3), not the paper's GPT-4o judge. Compare numbers cautiously; use `hypotheses.jsonl` with the official `evaluate_qa.py` for paper-comparable judging.

## Overall

| Metric | Value |
| --- | --- |
| accuracy | 0.840 |
| mean_latency_s | 16.231 |
| mean_tokens_used | 3068.5 |

## knowledge-update

| Metric | Value |
| --- | --- |
| n | 25 |
| accuracy | 0.880 |

## temporal-reasoning

| Metric | Value |
| --- | --- |
| n | 25 |
| accuracy | 0.800 |
