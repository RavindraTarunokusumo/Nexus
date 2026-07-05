# Plan: H9a — Productionize Chain-of-Note + Lean Prompt (answer path)

**Session:** `claude/perf-h8h9`
**Driver:** [Track-B baseline diagnostic](../../experiments/2026-07-05-trackb-baseline-diagnostic.md)
— 18/21 temporal failures are answer-path reasoning (wrong ordering/arithmetic
over retrieved evidence), the exact failure CoN fixes.
**Proven config:** [H9 answer-path experiment](../../experiments/2026-07-04-longmemeval-answer-path.md)
— `cot_leanprompt` on the fast T2 model: 0.806 overall / 0.797 temporal, −18%
answer-call tokens, **same model (no cost/latency change)**. (t3 buys ~+0.03 but
changes the model tier — left as an optional future flag, out of scope here.)

## Decision

Productionize **`cot_leanprompt`**: Chain-of-Note in-band reasoning + lean per-block
prompt, on the existing `state["model"]` (T2). No model-tier change.

## Files & interfaces

### 1. `app/intelligence/prompts/chat_answer.py`
- **`SYSTEM_PROMPT`** → CoN version. Change the schema line to
  `Return JSON with keys: notes, answer, citations.` and append the 5-step notes
  instruction (verbatim from `scripts/benchmarks/replay_answer.py::COT_SYSTEM`:
  resolve each block's absolute date; sort for ordering; compute duration deltas
  explicitly; enumerate for counting; abstain on entity-mismatch distractors;
  keep notes short, only the final response in `answer`). Keep the existing
  conflict-resolution / role-annotation paragraphs.
- **`build_user_prompt`** → lean block format. Keep: `[label]`, `Date:` (when
  `published_at`), `Role:` (when set), capsule text, ≤1 `Excerpt:`. **Drop:**
  Title, URL, Object type, Score, Epistemic note. Preserve the outer structure
  unchanged: `Current date:` (when `as_of`), `Question:`, `Context:`,
  `Answer guidance:` (when hint). Signature unchanged.
  *(Reference: `replay_answer.py::_build_lean_prompt`.)*

### 2. `app/intelligence/chat.py`
- **`ChatAnswerOutput`** (line 27) → add `notes: str = ""` (internal reasoning
  field). Default empty so parsing is backward-compatible.
- **`generate_answer`** (line 681) → **no wiring change.** It already returns
  `{"answer": result.answer, "citation_labels": result.citations, ...}`; `notes`
  is naturally dropped and never surfaced to the user. Confirm this — notes must
  not leak into the user-facing answer or citations.

### 3. `scripts/benchmarks/replay_answer.py` (+ `tests/benchmarks/test_replay_answer.py`)
Production `SYSTEM_PROMPT` is now CoN and `build_user_prompt` is now lean, which
changes what replay's `baseline`/non-lean/non-cot variants mean and could double
the CoN append. **Decouple replay from production prompt evolution:** inline
frozen copies of the *old* plain system prompt (`BASELINE_SYSTEM`) and old full
block builder for replay's baseline variants; derive `COT_SYSTEM` from
`BASELINE_SYSTEM` (not the now-CoN production `SYSTEM_PROMPT`). Keep
`test_replay_answer.py` green.

### 4. `tests/intelligence/test_chat_answer_prompt.py`
Update the format assertions to the lean output: assert `Date:`/`Role:`/text/
`Excerpt:` present and `Title:`/`URL:`/`Object type:`/`Score:`/`Epistemic note:`
**absent**. Keep the as_of / hint / excerpt-count / missing-key cases.

### 5. `tests/intelligence/test_chat_graph.py`
The `generate_answer` graph tests must still pass with the CoN system prompt +
`notes` field (mock LLM returns `{notes, answer, citations}`); the hint-line test
is preserved by the lean builder. Update mock payloads to include `notes` where
needed.

## Build order
1. `chat_answer.py` (prompt + lean builder) + `chat.py` (`ChatAnswerOutput.notes`).
2. Reconcile `replay_answer.py` (frozen baseline constants).
3. Update the three test files.

## Success gate
- Full suite green (`ruff`, `ruff format --check`, `mypy app/`, `pytest`) — the
  cross-file breakage (replay guard, prompt-format tests) is the whole risk and
  the full-suite gate is what catches it. Do NOT trust a scoped test pass.
- Then (orchestrator, outside the handoff): re-run the 55-instance temporal subset
  and confirm accuracy lifts materially above the 0.618 baseline toward the ~0.80
  replay result; `notes` never appears in any user-facing `answer`.

## Constraints
- No model-tier change (stay on `state["model"]`). No new dependency.
- `notes` is internal-only — never rendered to the user or persisted as the answer.
- Single trailing newline on every file.
