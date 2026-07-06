# LongMemEval Report

Oracle-retrieval framing: this run uses `longmemeval_oracle.json` evidence sessions only, measuring pipeline quality under oracle retrieval rather than full haystack recall.

Judge-model caveat: scores use `qwen3.7-max` (Nexus T3), not the paper's GPT-4o judge. Compare numbers cautiously; use `hypotheses.jsonl` with the official `evaluate_qa.py` for paper-comparable judging.

## Overall

| Metric | Value |
| --- | --- |
| accuracy | 0.000 |
| mean_latency_s | 6.289 |
| mean_tokens_used | 2563.0 |

## temporal-reasoning

| Metric | Value |
| --- | --- |
| n | 6 |
| accuracy | 0.000 |
