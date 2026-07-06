# H9b Wall Re-sizing + Answer-Truncation Fix (2026-07-06)

Session `claude/h9b-walls`. Companion to
[2026-07-05 Track B baseline diagnostic](2026-07-05-trackb-baseline-diagnostic.md).
Goal: re-size retrieval walls B1/B2/B3 on the lifted post-H9a baseline before
building levers, then attack the cheapest confirmed loss first.

## E2 — fresh full-211 baseline with dumped contexts

`run_longmemeval` on knowledge-update + temporal-reasoning (n=211, k=5,
workers=6, `--dump-context`), rev `f16799d`:
[`h9b-e2-baseline`](../benchmarks/runs/h9b-e2-baseline/) — **accuracy 0.821**,
4 instance errors, 37 failures. (Committed `results.jsonl` is slimmed —
`context_blocks` stripped for repo size; regenerate with `--dump-context` if a
new replay cache is needed.)

The 4 errors are all `LLMSchemaError` from **JSON truncation**: the answer
call's `max_tokens=2000` cut the Chain-of-Note response mid-object at ~1,900
tokens on long contexts.

## Failure taxonomy (37 failures)

Scripted bucketing by gold-token coverage of the retrieved context
(`wall_taxonomy.py`: cov = fraction of gold content tokens present in
context; wall1 cov<0.5, wall2 supersession-direction keywords, wall3
ordering/counting), then manual review of every item:

| bucket | scripted n | after manual review |
| --- | --- | --- |
| wall1 — evidence not retrieved | 15 | **~8–10 true retrieval misses.** cov is inflated by computed-number golds (e.g. gold "3 times" never appears verbatim in evidence), which land in wall1 despite full evidence being present — those are answer-path, not retrieval, failures. |
| wall2 — supersession direction | 3 | 3. Far smaller than the pre-H9a estimate; **B2 demoted**. |
| wall3 — ordering/counting | 6 | 6, solid. Needs per-sub-query slots (corrected R2 design). |
| other (cov≥0.5) | 13 | ~7 are a **new bucket: abstention-with-evidence** — full evidence retrieved (cov≈1.0) but the model gives the insufficient-evidence sentence anyway. Remainder is judge-boundary noise (≥3). |

Net: the retrieval walls are much smaller than budgeted on the old baseline;
the biggest single recoverable losses were on the **answer path**
(truncation + over-abstention), not retrieval.

## Replay A/B — frozen-context answer-path experiment

`replay_answer.py` over the E2 context cache (n=207, the 4 error rows
excluded): [`h9b-replay-abstention`](../benchmarks/runs/h9b-replay-abstention/).

| variant | accuracy | abstain | temporal | knowledge-update |
| --- | --- | --- | --- | --- |
| cot_leanprompt (production ref) | 0.802 | 34 | 0.777 | 0.844 |
| cot_leanprompt_nostep5 | 0.821 | 24 | 0.831 | 0.805 |
| **cot_leanprompt_4k** | **0.850** | 28 | 0.846 | 0.857 |
| cot_leanprompt_confident | 0.821 | 32 | 0.808 | 0.844 |
| cot_leanprompt_confident_4k | 0.816 | 29 | 0.815 | 0.818 |

McNemar exact vs reference:

- **`_4k` (max_tokens 2000→4000): p = 0.013** (12 recovered / 2 lost) — significant.
- `_nostep5` (drop entity-mismatch abstention rule): p = 0.50 — not significant.
- `_confident` (abstention re-scan suffix): p = 0.34 — not significant.
- `_confident_4k` under-performs plain `_4k`: the suffix costs about what it
  recovers once truncation is fixed.

Interpretation: 2000 tokens didn't just cause the 4 hard schema errors — it
silently squeezed CoN note-taking on long contexts well before the hard
cutoff. The prompt dials (step-5 ablation, confidence nudge) shuffle the
abstention boundary without net gain.

## Production change + validation

- `chat.py` answer call `max_tokens=4000` — commit `ff77d19`.
- **Validation caveat:** the first fresh-pipeline attempt
  ([`h9b-4k-validation`](../benchmarks/runs/h9b-4k-validation/), n=50
  all-temporal) is **not a test of this change** — benchmark scripts run as
  files imported `app` from the venv's editable install (the main checkout,
  still at 2000 tokens), so it measured main-vs-main. Its matched "flat"
  result (0.804→0.739, p≈0.45) is a same-code noise reading. Fixed by
  inserting the script's own tree root into `sys.path`
  (`scripts/benchmarks/run_longmemeval.py`, `replay_answer.py`); the real
  arm is `b3-gate-4k`. Bonus: two other same-code n=50 runs
  (`b3-gate-baseline`/`b3-gate-slots`) give the gate's noise floor —
  0.760/0.760 overall, ±3 per category.

## B3 A/B verdict (post-footgun, correct code both arms)

n=50 mixed gate (25/category) + targeted wall-3 runs, noise floor from the
same-code pair (0.760/0.760, ±3/category):

| arm | gate | temporal | knowledge-update | wall-3 (6q) |
| --- | --- | --- | --- | --- |
| 2000-token main (noise pair) | 0.760 / 0.760 | 17, 20 | 21, 18 | 1/6, 0/6 |
| **4k, slots off** (`b3-gate-4k`, `b3-wall3-4k`) | **0.820** | 20/25 | 21/25 | 1/6 (+2 schema errors) |
| 4k + slots (`b3-gate-slots-v2`, `b3-wall3-slots-v2`) | 0.776 | 17/25 | 21/25 | **0/6** |

- **4k confirmed on fresh pipeline**: 0.820 vs the 0.760/0.760 same-code pair —
  +3 questions, both categories at their best observed values, 0 gate schema
  errors. Direction and size match the frozen-context replay (p=0.013).
- **B3 slots FAIL their gate**: −0.044 on the gate (5 up / 7 down, p≈0.77, ns)
  and 0/6 on the target population — including flipping the Samsung/Dell
  ordering question right→wrong in **two independent replicates**. Emission
  verified real: 5/6 wall-3 questions produced ≥2 sensible sub-queries
  (`agent_runs`), so the mechanism ran as designed and still lost.
  **`retrieval_subquery_slots` stays False.**
- **Wall-3 is not (mainly) a retrieval problem anymore.** Per the taxonomy these
  questions retrieve their evidence (cov 0.58–1.0); across four runs the same
  4/6 fail systematically via date-arithmetic mistakes, abstention-with-evidence,
  or — on the two 6-item enumeration questions — the notes-overrun
  `LLMSchemaError`. The lever is the answer path (schema-failure retry, date
  arithmetic), not slot allocation.

## Revised path to >0.90 (211-question gate)

1. ~~Truncation fix~~ (`ff77d19`) — worth ≈+3–5 pts, validated by replay.
2. **B3 per-sub-query slots** — 6 questions, corrected R2 design.
3. **B1 fetch-pool bump** — ~9 true retrieval misses.
4. Abstention-with-evidence (~7) — no cheap prompt lever found; revisit after
   retrieval levers (some of these may resolve once ordering evidence is
   slotted properly).
5. B2 supersession-direction — demoted (n=3).

Judge noise (≥3) puts an effective ceiling near 0.97–0.98; 0.90 needs roughly
two of levers 2–4 to land.
