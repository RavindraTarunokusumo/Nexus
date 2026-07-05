# H9a — Chain-of-Note Answer-Path Productionization (+ E1 / Track-B experiment trail)

**Branch:** `claude/perf-h8h9`
**PR:** [#31](https://github.com/RavindraTarunokusumo/Nexus/pull/31)
**Merge commit:** `3f282d6`
**Merged at:** 2026-07-05T22:47:02Z
**Merged by:** RavindraTarunokusumo

## Summary

Productionized the **Chain-of-Note + lean prompt** answer-path config
(`cot_leanprompt`) proven in the H9 experiment (PR #30). The chat answer LLM now
reasons in an internal `notes` field (resolve each block's absolute date, sort for
ordering, compute duration deltas, enumerate for counting) before answering, over
a token-lean per-block context format. Same T2 model — no tier change.

**Full-211 LongMemEval validation:** matched frozen-context replay
**0.702 → 0.817 (+0.115, McNemar p=7e-5**, 30 wrong→right / 6 right→wrong); fresh
full run 0.812 (temporal 0.808, know-update 0.821); **−26% answer-call tokens**;
abstentions flat. Reproduces PR #30's 0.806.

This session was **experiment-first**: two prior measurements redirected the plan
before any code, and a false-negative confirmation was caught by matched-pair
analysis. Spec:
[`docs/superpowers/specs/2026-07-05-ingestion-retrieval-opt-h8h9.md`](../../superpowers/specs/2026-07-05-ingestion-retrieval-opt-h8h9.md).
Plan:
[`docs/superpowers/plans/2026-07-05-h9a-chain-of-note-productionization.md`](../../superpowers/plans/2026-07-05-h9a-chain-of-note-productionization.md).

## Tasks Completed

- [x] **E1 — pair-gate characterization** (`9deeb18`): instrumented 15-instance run
  (n=933 candidate pairs); an embedding-cosine gate skips only ~14% of
  relation-classify calls at ≥95% recall (not the projected 50–70%). Demoted A1
  (pair gate) to optional; promoted A2 batching / A3 caching. Writeup:
  `docs/experiments/2026-07-05-pair-gate-characterization.md`.
- [x] **Track-B baseline diagnostic** (`9c306d6`): 55-instance temporal run showed
  18/21 failures are answer-path reasoning (wrong ordering/arithmetic over
  retrieved evidence), not retrieval — promoted H9a ahead of H9b (retrieval walls).
  Writeup: `docs/experiments/2026-07-05-trackb-baseline-diagnostic.md`.
- [x] **H9a implementation** (`bae772e`): `chat_answer.py` CoN `SYSTEM_PROMPT` +
  lean `build_user_prompt`; `chat.py` `ChatAnswerOutput.notes` (internal, never
  surfaced); `replay_answer.py` decoupled via frozen `BASELINE_SYSTEM`; tests.
- [x] **H9a confirmation** (`324514b`, `bc3eba3`, `82e98ac`, `4d659c3`): a fresh
  full-run confirmation read false-flat (p=0.61, extraction noise); the
  frozen-context replay recovered the real +0.115 (p=7e-5). Step-5 ablation
  accuracy-neutral (kept). Writeup: `docs/experiments/2026-07-05-h9a-confirmation.md`.
- [x] **/simplify** (`8b6eb74`): deduped the verified-identical lean builder
  (replay lean variants now use production `build_user_prompt`); strengthened the
  prompt test's dropped-metadata check.
- [x] **Bundled review response** (`e8e0e31`): replay `COT_SYSTEM` now aliases
  production `SYSTEM_PROMPT` (single source of truth, kills drift; deletes
  `ChatAnswerCoN`); `notes: str | None` (null-robust); tests asserting `notes`
  never surfaces + a `SYSTEM_PROMPT` CoN contract test.

## Validation

Full suite green at merge: 593 passed / 6 pre-existing failures (verified
identical on clean `main`); ruff clean on touched files; mypy at the 3-error
pre-existing baseline. Security review skipped with justification (answer-path
prompt refinement + internal-only field; no new auth/secret/network/injection
surface). Bundled review verdict: Approve, 0 bugs — all 5 suggestions addressed.

## Deferred / Follow-Up (kept active in TODO.md)

- **H9b retrieval walls** — residual ~5–8 questions after CoN (ordering/counting/
  recency); needs full re-runs. Follow-up branch.
- **Track A ingestion levers (H9c/H8)** — A2 batching + A3 prefix caching are the
  primary token levers (E1 demoted the A1 cosine pair gate to marginal). Parked.
- **`t3_leanprompt`** — ~+0.02 accuracy at higher $/token; optional future flag.

## Methodology note

The same change read **flat (p=0.61)** via fresh full-run before/after and
**+0.115 (p=7e-5)** via frozen-context replay. Answer-path changes must be
confirmed on a frozen `--dump-context` cache (matched contexts), not fresh
full-runs where extraction stochasticity (the repo's ±0.25 noise) swamps the
signal. Report matched-pair deltas, not single-run aggregates.
