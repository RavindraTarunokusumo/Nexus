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

---

## Session: eval-framework-impl (2026-05-24, PR #11, merge `4c9dd25`)

### Never merge to main directly — the `no-commit-to-branch` pre-commit hook fires on merge commits too

`git merge main` (or `git checkout main && git merge feature/...`) is blocked by the `no-commit-to-branch` hook even on a merge commit. The only correct flow is: push feature branch → `gh pr merge`. Attempting a local merge wastes time and creates a dirty git state that requires `git merge --abort`.

### After context compaction, `git status` is the truth — not `Read`

The harness caches early file reads. After a context compaction the "Wasted call" message on `Read` reflects the pre-compaction snapshot, not the current disk state. Always run `git status` at session start to learn what is and isn't committed; never rely on a cached `Read` result for ground truth.

### Read `CLAUDE.md`, not `AGENTS.md`

When looking for project workflow instructions, always open `CLAUDE.md` — `AGENTS.md` is the Codex/OpenAI-facing mirror and can lag behind during a merge conflict window. The two files must be kept in sync (`Any change to CLAUDE.md → apply to AGENTS.md` and vice versa), but `CLAUDE.md` is the authoritative source.

### `/simplify` is a mandatory Pre-PR step — do not skip it

`/simplify` is listed as the first Pre-PR action in `CLAUDE.md`. Skipping it leaves dead code, sequential loops that should be concurrent, and TOCTOU races in the branch. In this session it produced meaningful wins (concurrent judging, dead import removal, budget-gate fix). Add it to a mental checklist alongside `pre-commit run --all-files`.

### Merge-conflict resolution for feature branches: merge main *into* feature, not the reverse

When `gh pr view` returns `"mergeable":"CONFLICTING"`, the fix is `git fetch origin main && git merge origin/main` from inside the feature worktree, resolve locally, commit, push. Never attempt to merge the feature branch into main locally — the `no-commit-to-branch` hook will block it and you'll be in a dirty merge state.

### `gh pr view` returns `"mergeable":"UNKNOWN"` for ~8 s after a push

GitHub re-evaluates mergeability asynchronously. A `UNKNOWN` status immediately after `git push` is normal. Wait ~8 seconds and re-poll; it will resolve to `CLEAN` or `CONFLICTING`.

### `pre-commit run --all-files` auto-reformats but does not auto-fix lint/mypy

`ruff-format` modifies files in place and marks the hook `Failed` (files modified). Re-running after staging the reformatted files will pass. `ruff` lint (e.g. B904 `raise ... from None`) and `mypy` errors require manual edits — they are never auto-fixed. Common ones in this codebase: B904 inside `except ValueError` blocks, and `Collection[Any]` assignments that need `# type: ignore[assignment]`.

### Workflow Rule 4: never run `git reset --hard` or `git merge --abort` without explicit user permission

Even when recovering from a botched merge, `reset --hard` is a destructive command covered by CLAUDE.md Rule 4. The correct response to a failed merge is `git merge --abort` (not `--hard`), and even that should be confirmed with the user first. Violating this erodes trust and can silently discard staged work.
