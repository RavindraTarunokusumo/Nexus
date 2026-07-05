# LongMemEval Adapter

External long-term memory benchmark ([LongMemEval](https://github.com/xiaowu0162/LongMemEval), ICLR 2025). The Nexus adapter maps each instance's haystack sessions to ingested documents and runs the full memory pipeline (ingest → extract → cross-doc relations → lifecycle → consolidate → answer), then scores answers with the benchmark QA-judge protocol.

Dataset JSON files are **not** committed to git (see `.gitignore`). Download them locally before running.

## Download

From the repository root:

```bash
pip install huggingface_hub  # if not already installed
huggingface-cli download xiaowu0162/longmemeval-cleaned \
  --local-dir evals/memory/longmemeval \
  --local-dir-use-symlinks False
```

For v1 evaluation, use the oracle file (evidence sessions only):

- `evals/memory/longmemeval/longmemeval_oracle.json`

Optional full-haystack files (not used by the default adapter run):

- `longmemeval_s.json` (~40 sessions per instance)
- `longmemeval_m.json` (~500 sessions per instance)

## Run the adapter

Requires a scratch Postgres database and LLM credentials (`LLM_API_KEY`, `LLM_BASE_URL` in `.env`).

```bash
DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5432/nexus_lme \
  python scripts/benchmarks/run_longmemeval.py \
  --dataset evals/memory/longmemeval/longmemeval_oracle.json \
  --categories knowledge-update,temporal-reasoning \
  --limit 20 \
  --offset 0 \
  --k 5 \
  --out docs/benchmarks/runs/longmemeval-smoke
```

### CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--dataset` | `evals/memory/longmemeval/longmemeval_oracle.json` | Path to LongMemEval JSON (list of instances) |
| `--categories` | `knowledge-update,temporal-reasoning` | Comma-separated `question_type` filter |
| `--limit` | `20` | Max instances after filter (`0` = no limit) |
| `--offset` | `0` | Skip first N instances after filter (resume) |
| `--k` | `5` | Chat retrieval `top_k` |
| `--out` | timestamped dir under `docs/benchmarks/runs/` | Output directory |

### Outputs

Written under `--out`:

| File | Contents |
|------|----------|
| `results.jsonl` | Per-instance question, hypothesis, `autoeval_label`, latency, capsule counts |
| `hypotheses.jsonl` | `question_id` + `hypothesis` only (official `evaluate_qa.py` input) |
| `report.md` | Accuracy overall and per `question_type`, latency/tokens, comparability caveats |
| `run_meta.json` | Dataset path, categories, models, git rev, `judge_errors` |

Re-score with the official judge (paper-comparable GPT-4o):

```bash
python src/evaluation/evaluate_qa.py gpt-4o hypotheses.jsonl longmemeval_oracle.json
```

(Path assumes the official LongMemEval repo checkout.)

## Instance schema (summary)

Each JSON element includes:

- `question_id` — suffix `_abs` marks abstention questions
- `question_type` — one of six categories
- `question`, `answer`, `question_date`
- `haystack_session_ids`, `haystack_dates`, `haystack_sessions` — parallel lists; each session is a list of `{"role", "content"}` turns

The adapter renders sessions as `User:` / `Assistant:` transcripts, maps each to a document with URL `longmemeval://{question_id}/{session_id}`, and truncates memory tables between instances for isolation.