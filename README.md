# Nexus — Personal AI Knowledge Intelligence

Nexus is a **MemoryAgent**: it ingests a stream of documents, compresses them into
grounded *semantic capsules*, links them with typed *relations*, tracks their
*lifecycle* (active → confirmed / superseded / stale), consolidates them into
*theses*, and answers questions with citations and an epistemic evidence chain —
abstaining when the corpus can't support an answer.

T2+ reasoning runs on **Qwen Cloud** (`qwen3.6-flash` / `qwen3.7-max`); embeddings run
locally (`bge-small`, 384-dim).

---

## Demo guide

This walks from a clean checkout to a live, cited answer and a scored benchmark in a
few minutes. Everything runs against a local Postgres + Qwen Cloud; no server process
is required for the demo.

### 0. Prerequisites

- Python 3.11 + a virtualenv, Docker (for Postgres/pgvector), and a **Qwen Cloud API
  key** (DashScope, OpenAI-compatible endpoint).

### 1. Environment

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# edit .env: set QWEN_CLOUD_API_KEY, and DATABASE_URL to your Postgres.
# LLM_BASE_URL defaults to https://dashscope-intl.aliyuncs.com/compatible-mode/v1
```

Key `.env` settings (see `.env.example` for the full list):

| Var | Purpose |
| --- | --- |
| `QWEN_CLOUD_API_KEY` | Qwen Cloud key; used for every T2/T3 call |
| `LLM_BASE_URL` | OpenAI-compatible base URL (DashScope international) |
| `T2_MODEL` / `T3_MODEL` | `qwen3.6-flash` / `qwen3.7-max` |
| `DATABASE_URL` | `postgresql+asyncpg://…` — Postgres with the `vector` extension |

### 2. Database

```bash
docker compose up -d postgres        # pgvector/pgvector:pg16
alembic upgrade head                 # create the schema
```

### 3. One-command demo — run the benchmark

The fastest way to see the whole pipeline is the synthetic memory benchmark. It ingests
a 14-document AI-tech corpus, extracts capsules, classifies relations, applies lifecycle
transitions, consolidates theses, then answers 22 questions across 6 categories and
scores them.

```bash
nexus eval memory run --benchmark nexus_synthetic --k 5
# → writes docs/benchmarks/runs/<timestamp>/{report.md,results.jsonl,run_meta.json}

nexus eval memory report --run-id <timestamp>
```

The report shows overall + per-category metrics: answer correctness, evidence recall@k,
citation faithfulness, temporal / supersession correctness, abstention accuracy, latency,
and token cost. A representative baseline lives at
[`docs/benchmarks/baseline-2026-07-02.md`](docs/benchmarks/baseline-2026-07-02.md)
(answer_correctness 0.57, citation_faithfulness 1.00, abstention 0.77).

### 4. Interactive demo — ask questions with citations

Once a corpus is ingested (step 3 populates the DB), drive live answers directly:

```bash
python -m scripts.benchmarks.demo_answer \
  "What is the current price per million tokens for the Lumina Inference API?" \
  "Was LuminaSpark 2.0 trained on scraped medical records?" \
  "What is the overall thesis on small-model inference cost?"
```

Each answer prints the response plus its citations, annotated with **role**
(`primary` / `counter_evidence` / `supersession`) and an **epistemic note**
(`authority=…; evidence_quality=…; lifecycle=…`). Things to look for:

- **Living knowledge** — the pricing answer returns the *current* price; the superseded
  earlier rate is filtered out of retrieval.
- **Authority weighting** — the medical-records answer surfaces both the primary
  transparency statement and the low-authority rumor, tagged `authority=tertiary`.
- **Consolidation** — the thesis question is answered from a synthesized cross-document
  thesis, not a single capsule.
- **Abstention** — ask something absent from the corpus (e.g. a real vendor's model) and
  it declines instead of hallucinating.

### 5. The pipeline, step by step

The benchmark runs these stages end to end; you can also drive them individually against
your own ingested corpus:

| Stage | Command | What it does |
| --- | --- | --- |
| Extract | (runs during ingest) / `nexus capsules backfill` | Documents → grounded semantic capsules |
| Lifecycle | `nexus lifecycle run --domain personal_ai_tech` | active → confirmed / superseded / stale / archived |
| Consolidate | `nexus consolidation run --domain personal_ai_tech` | Clusters related capsules into theses |
| Inspect | `nexus capsules …`, `nexus theses …`, `nexus status` | Browse capsules, relations, theses, pipeline health |

Add `--dry-run` to `lifecycle`/`consolidation` to preview transitions without writing.

### 6. Where to look next

- Benchmark design & metric definitions: [`docs/benchmarks/memory-benchmark-plan.md`](docs/benchmarks/memory-benchmark-plan.md)
- Baseline results & known gaps: [`docs/benchmarks/baseline-2026-07-02.md`](docs/benchmarks/baseline-2026-07-02.md)
- Fixtures (corpus + questions): [`evals/memory/nexus_synthetic/`](evals/memory/nexus_synthetic/)
- Architecture & internals: [`docs/index.md`](docs/index.md)

---

## Development

Validation suite (run before committing):

```bash
ruff check . && ruff format --check . && mypy app/ && pytest
```

See [`CLAUDE.md`](CLAUDE.md) for the full contributor workflow.
