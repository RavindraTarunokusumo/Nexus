# Insights

Capture durable workflow lessons here.

Use this file for:

- recurring debugging patterns
- repo-specific gotchas
- validation shortcuts that are safe to reuse
- decisions that should not be rediscovered on the next task

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
