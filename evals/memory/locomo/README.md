# LoCoMo Adapter

External very-long-term conversational memory benchmark
([LoCoMo](https://github.com/snap-research/locomo), Snap Research, ACL 2024 —
"Evaluating Very Long-Term Conversational Memory of LLM Agents"). The Nexus adapter
ingests each of the benchmark's 10 conversations through the full memory pipeline
(ingest → extract → cross-doc relations → lifecycle → consolidate) **once**, then
answers every one of that conversation's QA pairs against the shared ingested state,
scoring answers with an LLM-judge protocol.

The dataset JSON is **not** committed to git (see `.gitignore`). Download it locally
before running.

License: the LoCoMo dataset is released under
[CC BY-NC 4.0](https://github.com/snap-research/locomo/blob/main/LICENSE.txt)
(Attribution-NonCommercial) — non-commercial use only.

## Download

From the repository root:

```bash
curl -sL -o evals/memory/locomo/locomo10.json \
  https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json
```

## Dataset shape

`locomo10.json` is a JSON list of 10 conversation samples. Each sample:

- `sample_id` — e.g. `"conv-26"`.
- `conversation` — `speaker_a` / `speaker_b` names, plus `session_<N>` (list of turns)
  and `session_<N>_date_time` (e.g. `"1:56 pm on 8 May, 2023"`) for each session, `N`
  starting at 1. Session counts vary per conversation (19–32 sessions). Each turn is
  `{"speaker": ..., "dia_id": "D<N>:<i>", "text": ...}`, optionally with `img_url` /
  `blip_caption` / `query` for image turns (images are not released upstream; the
  adapter ignores these fields and renders text only). Some samples carry extra
  `session_<N>_date_time` keys beyond the last populated `session_<N>` — the adapter
  anchors iteration on the content keys, not the date_time keys.
- `qa` — list of QA pairs: `question`, `answer` (str or int; `None` for adversarial),
  `evidence` (list of `dia_id` references), `category` (int 1–5), and
  `adversarial_answer` (category 5 only — a plausible-sounding *incorrect* answer used
  to check the model doesn't confabulate it).
- `event_summary`, `observation`, `session_summary` — generated annotations not used by
  this adapter.

### Categories

Verified directly against the official eval code
(`task_eval/{evaluation,gpt_utils}.py` in the upstream repo): category 2 questions get
a "use date of conversation" hint (temporal), and category 5 is graded via an
unanswerable/adversarial check. The upstream code does not otherwise distinguish
categories 1/3/4 by name in any branch; the labels below follow the ordering used in
this project's adapter task brief and are used for report labeling only, not scoring
logic:

| Category | Name | Correct behavior |
| --- | --- | --- |
| 1 | multi_hop | Answer combining multiple evidence spans |
| 2 | temporal | Answer is a date/duration; off-by-one-day tolerated |
| 3 | open_domain | Answer requires reasoning/inference beyond a direct quote |
| 4 | single_hop | Answer directly stated in one evidence span |
| 5 | adversarial | **Abstain** — no correct answer exists in the conversation |

## Run the adapter

Requires a scratch Postgres database and LLM credentials (`LLM_API_KEY`,
`LLM_BASE_URL` in `.env`).

```bash
DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5434/nexus_locomo \
  python scripts/benchmarks/run_locomo.py \
  --dataset evals/memory/locomo/locomo10.json \
  --limit 10 \
  --k 5 \
  --out docs/benchmarks/runs/locomo-smoke
```

### CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--dataset` | `evals/memory/locomo/locomo10.json` | Path to LoCoMo JSON (list of conversation samples) |
| `--categories` | `1,2,3,4,5` | Comma-separated category ints to include |
| `--limit` | `0` (no limit) | Max conversations after `--offset` (10 total in `locomo10.json`) |
| `--offset` | `0` | Skip first N conversations (resume) |
| `--question-limit` | `0` (no limit) | Max questions per conversation after category filter — mainly for smoke runs |
| `--k` | `5` | Chat retrieval `top_k` |
| `--out` | timestamped dir under `docs/benchmarks/runs/` | Output directory |
| `--workers` | `1` | Parallel worker count; shards by **conversation**, not question |
| `--db-url-template` | `""` | Per-worker DB URL template with `{n}` placeholder (required when `--workers > 1`) |
| `--db-url` | `None` | DB URL for `--workers 1` (defaults to `settings.database_url` from `.env` if omitted) |
| `--dump-context` | off | Serialize retrieved context blocks into `results.jsonl` for answer-path replay |

### Outputs

Written under `--out` (crash-safe: `results.partial.jsonl` is appended to after every
question, so a killed run doesn't lose completed work):

| File | Contents |
|------|----------|
| `results.jsonl` | Per-question `question_id`, `sample_id`, `category`, question, gold answer, hypothesis, `autoeval_label`, latency, capsule counts |
| `hypotheses.jsonl` | `question_id` + `hypothesis` only |
| `report.md` | Accuracy overall and per category, latency/tokens, comparability caveats |
| `run_meta.json` | Dataset path, categories, models, git rev, `judge_errors`/`question_errors` |

## Design notes

- **Ingest once per conversation.** Unlike the LongMemEval adapter (one haystack per
  question, so it truncates + re-ingests per question), LoCoMo conversations carry
  many QA pairs each. Memory tables are truncated once per conversation, all sessions
  are ingested, and every selected question for that conversation is then answered
  against the same state. Workers shard by conversation, not question.
- **Temporal anchor.** LoCoMo has no per-question timestamp (unlike LongMemEval's
  `question_date`). The adapter passes the latest ingested session's date as the
  chat's `as_of` — the point at which the full conversation history is available —
  as the closest analog to "answer as of now".
- **Judge model caveat.** Scoring uses an LLM-judge yes/no protocol on the Nexus T3
  model, not the official LoCoMo repo's F1/ROUGE/exact-match scripts. Numbers are not
  directly comparable to published LoCoMo leaderboard results.
