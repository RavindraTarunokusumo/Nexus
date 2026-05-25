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

## Session: web-ui-chat-session-memory (2026-05-25)

### `feedparser` incompatible with Python 3.11 in network-restricted remote env

`feedparser>=6.0.11` depends on `sgmllib3k` which requires a C extension build. In the remote env, `sgmllib3k` fails to build and `feedparser` itself fails to import due to the missing `sgmllib` stdlib module (removed in Python 3). Workaround: create a minimal `sgmllib.py` stub at `/usr/local/lib/python3.11/dist-packages/sgmllib.py` exporting the regex variables (`entityref`, `incomplete`, `interesting`, `shorttag`, `shorttagopen`, `starttagopen`) and a `SGMLParser` class that delegates to `html.parser.HTMLParser`. This unblocks all tests that import via conftest.

### `langgraph-checkpoint-postgres` lives at `langgraph.checkpoint.postgres`, not a separate package

Despite being installed via `pip install langgraph-checkpoint-postgres`, the module is part of the `langgraph` namespace: `from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver`. Trying to import `langgraph_checkpoint_postgres` directly fails.

### Vitest `getByLabelText` regex matches both label text and aria-label on other elements

When a `<label>Message</label>` is associated with a textarea AND a nearby button has `aria-label="Send message"`, `getByLabelText(/message/i)` throws "Found multiple elements" because RTL also matches elements whose own `aria-label` satisfies the query. Fix: use `getByRole('textbox', { name: /message/i })` for the input, and anchor the button query with `^send message$` to avoid partial matches.

### `erasableSyntaxOnly: true` in TypeScript 6 disallows constructor parameter properties

TypeScript 6 (shipped with the Vite React-TS template) enables `erasableSyntaxOnly`, which bans `public readonly` shorthand in constructors. Replace with an explicit property declaration + manual assignment in the constructor body.

### Vite `defineConfig` from `vite` doesn't accept `test` property; use `vitest/config`

When adding Vitest config to `vite.config.ts`, the `test` field causes a TypeScript error if `defineConfig` is imported from `vite` instead of `vitest/config`. Always use `import { defineConfig } from 'vitest/config'` when Vitest options are present.

### jsdom (Vitest) doesn't implement `scrollIntoView`

`element.scrollIntoView()` throws `TypeError: is not a function` in jsdom. Add `window.HTMLElement.prototype.scrollIntoView = () => {}` in the Vitest setup file (`src/test/setup.ts`).

### PostgreSQL service needs manual start in remote env + pgvector must be installed separately

The remote container has PostgreSQL 16 but it's not running and `pgvector` extension is absent. Run `service postgresql start` and `apt-get install -y postgresql-16-pgvector` before the first migration, then create the user and database via `sudo -u postgres psql`.

## Session: chat-session-memory-spec (2026-05-24)

### `apply_patch` uses the agent process directory, not the command workdir

When working from a dedicated git worktree, `apply_patch` can still apply relative paths against the original agent process directory. Use absolute paths in patch headers for worktree edits, or verify file placement immediately after patching before running validation.

### GitNexus query can require explicit repo paths in multi-worktree setups

After indexing both the root checkout and a session worktree, `npx gitnexus query` can fail with "Multiple repositories indexed." Pass `--repo "<absolute worktree path>"` for `query`, `context`, `impact`, and `detect-changes` commands to avoid ambiguous repo selection.
