# Insights

Capture durable workflow lessons here.

Use this file for:

- recurring debugging patterns
- repo-specific gotchas
- validation shortcuts that are safe to reuse
- decisions that should not be rediscovered on the next task

---

## Session: system tuning (2026-05-28 → 2026-05-29)

Workflow / harness observations from running the eval-driven system-tuning campaign. Feature-specific findings are in `docs/iterations/archive/2026-05-28-system-tuning.md`.

### What worked

- **Background eval runs.** `Bash(run_in_background=true)` for 30-45-example eval runs (3-5 min each) freed the main loop to read code, draft prompts, and write tests in parallel. Without it, each trial would block the session for minutes. Pattern: launch 1-2 in background, do code prep / analysis while they run, read results on notification.
- **Dispatching multiple Sonnet subagents in parallel for fixes.** When the simplify review surfaced 5 independent findings, dispatching 5 Sonnet agents in one message addressed all of them in one elapsed turn. Each agent's prompt named the file, the bug, and the exact fix to apply — no exploration required.
- **TodoCreate + TaskUpdate gave a stable "where am I" anchor** across a session that ran 30+ eval iterations, 5 architectural changes, doc updates, and pre-PR. The auto-injected task-list reminders prevented drift.
- **`gitnexus_impact` before edits to shared symbols** saved time on the prompt and schema changes — it confirmed that `SYSTEM_PROMPT` had only one upstream caller, so the changes could be made fearlessly without grep sweeps.

### What didn't work / was friction

- **`doc-updater` agent hallucinated completion.** It returned a detailed report of files allegedly modified, but the working tree was untouched. Fix: when delegating doc edits, require the agent to verify with `git status` or `git diff` before reporting. Or write critical docs inline.
- **OpenRouter routing restrictions** silently blocked Anthropic models for this account — both `claude-haiku-4.5` (S7 cross-family judge) and `claude-opus-4.7/4.8` (calibration labeler) returned 404 with `"No allowed providers are available for the selected model."` Gemini and DeepSeek work; Anthropic doesn't. Worth documenting at the project level as a known constraint.
- **PowerShell f-string parsing.** Inline `python -c "..."` with f-strings containing `{'k':>3}` or similar format specs broke on PowerShell's `:` handling. Workaround: write the script to a `.py` file and invoke that. Cleaner, also benefits from syntax highlighting in editors.
- **GLiNER zero-shot classification on abstract labels is brittle.** `is_claim:yes/no` had 85% yes-bias. `sentence_role:atomic_fact/framing/opinion/background` produced 4.3% atomic_fact (DeBERTa's prior for "atomic_fact" doesn't match our usage). Lesson: zero-shot semantic classification works only when the label name has a strong pretraining anchor. For domain-specific concepts, fine-tune or use a structural proxy (e.g. NER presence).
- **`pre-commit`'s bundled ruff is older than the local venv ruff.** Adding `ASYNC240` (new selector) to per-file-ignores broke pre-commit even though the local venv ruff accepted it. Bundled-tool drift is a recurring footgun — when picking ruff selectors, check what the bundled version knows.
- **Two background processes hitting the same DB simultaneously didn't conflict**, but I was nervous they might. They don't share state — each eval run writes its own EvalRun row. Worth remembering: independent reads/writes against Postgres are safe in parallel.
- **`Agent` tool hit a session limit mid-review**, returning "you've hit your session limit · resets 11:40pm". Fallback was to do the review inline. Lesson: keep the inline option warm; don't bet a whole step on subagents being available.

### Patterns to repeat

- **Run the eval before tuning the prompt.** The whole campaign started by treating the eval framework as a measurement instrument first — this is what surfaced both the Jaccard alignment bug and the confidence-is-information-free finding. Tuning prompts without questioning the metric would have wasted weeks.
- **When proposing a change, name what could prove it wrong AND what the "free" diagnostic is.** The S7-S10 sequence (judge calibration + cross-family judge) cost nothing but reframed every result that followed. Run free diagnostics before paid experiments.
- **Compose env-gated trials, not branches.** `EVAL_DEDUP`, `EVAL_ATOMICITY`, `EVAL_CONFIDENCE_THRESHOLD`, `EVAL_TOP_K`, `EXTRACTOR` — all opt-in environment knobs. Let one config sweep test many hypotheses. Killing experiments is then just `unset VAR`.
- **Keep an eval-friendly synthetic dataset for the canonicalization / supersede story.** The live ingestion was empty, so I exercised the alias-resolution + clustering on synthetic Claim rows. That let me ship the helper with confidence without waiting for real data.

### Anti-patterns to avoid

- **Don't claim a metric improvement is "real" without a cross-family check.** Numbers from a single judge family carry ~0.04 F1 noise from in-family bias. The right headline is the cross-family number.
- **Don't optimize for the gold's annotation style** (e.g., top-1 cap on a single-claim gold). It moves the metric but doesn't improve the system. The right fix is the gold (v3 → v4), not the cap.
- **Don't trust `confidence` fields the model emits about itself.** Default-keep `0.973` for correct claims and `0.942` for wrong ones is a calibration disaster. Use the field for diagnostics only; never gate retrieval on it.
- **Don't dispatch `Agent` for a 2-line fix.** Inline is faster; subagents shine when there are 3+ independent items that can run in parallel, or when context isolation matters.

### Tooling tweaks worth doing

- `pyproject.toml` `[tool.ruff.lint.per-file-ignores]` should explicitly carve out `scripts/**` for ASYNC230, E731, E402 — done in this PR. Saves us from per-file noqa churn on future one-off CLI utilities.
- The `EXTRACTOR=gliner` switch should be the default; LLM path stays as `EXTRACTOR=llm` opt-in. Already done. Operator override stays via env var.
- The eval framework's `mean_groundedness` and `mean_factuality` track recall almost exactly on our current gold (within ±0.01). Worth a follow-up to either (a) prove they're independent signals on adversarial cases or (b) drop them as redundant.

---

## Session: observability (2026-05-22)

### `gitnexus_detect_changes` only sees uncommitted changes

`scope: compare` and `scope: all` both return 0 changed symbols when the working tree is clean — even if the branch is many commits ahead of `main`. The tool diffs the working tree, not the git history. After committing everything, use `git diff main...HEAD --stat` to confirm branch scope instead.

### GitNexus `analyze` auto-updates CLAUDE.md and AGENTS.md

Running `npx gitnexus analyze` rewrites the stats block in both files (symbol/relationship/flow counts). These show up as unstaged modifications after every analyze run. Commit them with `chore: update GitNexus index stats` to keep the tree clean before the PR.

### `--timeout` flag not supported in this pytest config

`pytest --timeout=60` fails with "unrecognized arguments". The `pytest-timeout` plugin is not installed. Drop the flag — the suite finishes in ~60 s naturally.

### mypy not installed in the project venv

`python -m mypy` fails with "No module named mypy". Either install it (`pip install mypy`) or skip the mypy step and note it in the PR. Worth adding to `pyproject.toml` dev dependencies so it's available next session.

### Typer/Click CLI help goes to a non-standard stream on Windows

`subprocess.run([..., "--help"], capture_output=True)` returns empty stdout/stderr on Windows — Typer writes to its own buffer. Use `typer.testing.CliRunner().invoke(app, [...])` and inspect `result.output` to verify help text. Exit code 0 is still a reliable signal that there are no import errors.

### Ruff import-sort (`I001`) catches cross-group ordering

When a new import from `app.observability` is added between two `app.ingestion` imports, ruff flags an `I001` unsorted block. Run `ruff check --fix` to auto-sort; the remaining non-fixable issue (S311 on `random.randint` in tests) needs a `# noqa: S311` comment.

### CliRunner output encoding error on Windows cp1252

Printing `CliRunner.invoke().output` via `print()` in a cp1252 shell raises `UnicodeEncodeError` because Rich emits box-drawing characters. Inspect `result.output` programmatically (e.g., `"Usage" in result.output`) rather than printing it to avoid the error.

## Session: chat-session-memory-spec (2026-05-24)

### `apply_patch` uses the agent process directory, not the command workdir

When working from a dedicated git worktree, `apply_patch` can still apply relative paths against the original agent process directory. Use absolute paths in patch headers for worktree edits, or verify file placement immediately after patching before running validation.

### GitNexus query can require explicit repo paths in multi-worktree setups

After indexing both the root checkout and a session worktree, `npx gitnexus query` can fail with "Multiple repositories indexed." Pass `--repo "<absolute worktree path>"` for `query`, `context`, `impact`, and `detect-changes` commands to avoid ambiguous repo selection.
