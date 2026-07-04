# LongMemEval Report

Oracle-retrieval framing: this run uses `longmemeval_oracle.json` evidence sessions only, measuring pipeline quality under oracle retrieval rather than full haystack recall.

Judge-model caveat: scores use `qwen3.7-max` (Nexus T3), not the paper's GPT-4o judge. Compare numbers cautiously; use `hypotheses.jsonl` with the official `evaluate_qa.py` for paper-comparable judging.

## Overall

| Metric | Value |
| --- | --- |
| accuracy | 0.353 |
| mean_latency_s | 2.530 |
| mean_tokens_used | 841.1 |

## knowledge-update

| Metric | Value |
| --- | --- |
| n | 78 |
| accuracy | 0.587 |

## temporal-reasoning

| Metric | Value |
| --- | --- |
| n | 133 |
| accuracy | 0.217 |
