# Memory Benchmark — Baseline Report Template

Fill one of these per baseline run. Numbers come straight from
`docs/benchmarks/runs/<run-id>/report.md` + `run_meta.json`; narrative is added by hand.

## Run metadata

- Run ID: `<out-dir basename, e.g. baseline-YYYY-MM-DD>`
- Git rev: `<meta.git_rev>`
- Date: `<meta.finished_at>`
- Models: T1 `<meta.t1_model>` · T2 `<meta.t2_model>` · T3 `<meta.t3_model>`
- LLM base URL: `<meta.llm_base_url>`
- Corpus: `<meta.doc_count>` docs · `<meta.question_count>` questions · domain `<meta.domain>` · k=`<meta.k>`

## Headline metrics (overall)

| Metric | Value | Notes |
| --- | --- | --- |
| answer_correctness | | keyword coverage of expected answers |
| citation_faithfulness | | fraction of answers whose citations ⊆ retrieved context |
| evidence_recall_at_k | | expected source docs actually cited |
| abstention_accuracy | | correct abstain vs answer decisions |
| supersession_correctness | | superseded-category answers that name the current fact and avoid the stale one |
| latency p50 / p95 (s) | | wall-clock per question |
| total tokens | | across ingest+extract+answer |

## Per-category summary

Paste the per-category tables from the generated `report.md`.

## Interpretation & top follow-ups

- What the numbers say (strengths / weaknesses).
- Pipeline gaps surfaced by the run (with the metric they cap).
- Ranked next actions.
