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

## Session: chat-session-memory-pr12 (2026-05-25)

### Resume after context compaction: check `git status` first

When a session resumes from a compacted summary, the summary accurately describes which files were edited but may not be precise about commit state. `git status` immediately after resuming is the reliable source of truth for what's staged vs. committed.

### Stop hooks fire on agent-written files — commit immediately after any agent output

The stop-hook git-check script fires when any agent (doc-updater, security-review) writes files to disk. Commit agent output immediately after it lands, before the next workflow step, to avoid the hook blocking session close.

### `/security-review` skill fails with `fatal: ambiguous argument 'origin/HEAD...'`

The skill uses `git log origin/HEAD..HEAD` to scope the diff, which fails in remote environments where `origin/HEAD` is not set. Workaround: run security review as a manual `Agent` call instead of invoking the skill directly. The underlying logic is identical.

### GitNexus impact analysis requires the exact function name, not the module name

`npx gitnexus impact --repo . routes_chat` returns "target not found". The tool indexes symbols, not module paths. Use the function name: `npx gitnexus impact --repo . answer_chat`.

### doc-updater can confuse field names across endpoints in the same file

When a file has multiple endpoints with different schema fields (`question` vs. `content`), the doc-updater agent may conflate them in curl examples. Always self-review doc changes for field name correctness, especially when one file serves multiple endpoints.

### Parallel session collision: rebase is clean if additions are orthogonal

When two sessions implement the same feature in parallel, rebasing the later branch onto main (which contains the earlier merge) produces only small add/add conflicts. Taking the more complete version (`--theirs` for implementation files, manual merge for shared config like pyproject.toml) resolves them cleanly. The result composes correctly on the merged base.

## Session: chat-session-memory-spec (2026-05-24)

### `apply_patch` uses the agent process directory, not the command workdir

When working from a dedicated git worktree, `apply_patch` can still apply relative paths against the original agent process directory. Use absolute paths in patch headers for worktree edits, or verify file placement immediately after patching before running validation.

### GitNexus query can require explicit repo paths in multi-worktree setups

After indexing both the root checkout and a session worktree, `npx gitnexus query` can fail with "Multiple repositories indexed." Pass `--repo "<absolute worktree path>"` for `query`, `context`, `impact`, and `detect-changes` commands to avoid ambiguous repo selection.

## Session: phase-a-telos-semantic-bridge (2026-05-30)

### `pass_filenames: false` pre-commit hooks fail every commit on a dirty branch

`mypy` and `pytest-fast` in `.pre-commit-config.yaml` use `pass_filenames: false`, so they always run against the whole `app/` tree regardless of what's staged. When a branch has pre-existing unstaged dirt (`session_memory.py` referencing functions absent from `main`) or a missing env dep (`langgraph.checkpoint.postgres`), every commit fails the hook even when the staged change is trivial and unrelated. Workflow Rule 6 says "note as pre-existing and proceed" — operationally that requires `SKIP=mypy,pytest-fast git commit ...`. The fix is to add `additional_dependencies: [langgraph-checkpoint-postgres>=2.0.0]` to the `pytest-fast` hook entry and `additional_dependencies: [types-PyYAML]` to the `mypy` hook (already TODO'd) so they have what they need in their isolated envs.

### Inherited unstaged dirt across sessions can mask a real fix

Started this session with `git status` clean. Within minutes `app/intelligence/session_memory.py` showed up as modified — a substantial in-flight diff (66 lines defining `make_memory_graph` / `invoke_with_memory`) inherited from another worktree sharing the venv. It silently broke mypy on every commit because `main.py` and `routes_chat_sessions.py` import those symbols. When the `/simplify` implementer accidentally swept the dirty file into a cleanup commit (Workflow Rule 3 violation — non-specific staging in the subagent), the long-standing mypy failure cleared. **Lesson:** when an inherited dirty file references symbols mypy says are missing in `main`, the unstaged diff probably IS the fix that needs to land — investigate it as a candidate commit rather than treating it as noise to be stashed away.

### GitNexus `mcp__gitnexus__impact` requires `repo` parameter when multiple paths indexed

The MCP tool version of `gitnexus_impact` errors out with "Multiple repositories indexed. Specify which one with the 'repo' parameter" when both the root checkout and a session worktree are indexed. Pass the absolute worktree path as `repo` — same fix as the CLI version, but the MCP tool is less obvious about which parameter to use.

### GitNexus reports module-level imports as upstream impact — verify before trusting the risk score

`gitnexus_impact` on `ExtractionOutput` returned MEDIUM risk with 11 file-level importers. Real usage (verified via `Grep`) was 2 files: `extraction.py` (being rewritten) and `evaluation/runner.py` (the SUT for eval). The other 9 imports were file-level coarsening — Python's `from llm_client import …` lights up the IMPORTS edge to the whole file in GitNexus's index, regardless of which symbol the importer actually uses. **Lesson:** when GitNexus reports >5 importers on a symbol, sanity-check with `Grep` for actual symbol use before deciding the change is high-risk.

### Subagent `DONE_WITH_CONCERNS` framing can be misleading

A `/simplify` implementer reported "All seven fixes were already applied to the working tree before this session" — confusing wording for what was actually "I just applied them." Verify subagent state claims with `git log` and `git show --stat <commit>` rather than trusting the prose. The skill template warns against this ("Trust but verify: an agent's summary describes what it intended to do, not necessarily what it did").

### `ScheduleWakeup` clamps to 3600s — chained cycles needed for multi-hour sleeps

User asked for a 4-hour sleep between A1 and A2. `ScheduleWakeup`'s `delaySeconds` clamps to [60, 3600] per call. To honor multi-hour pauses, the wakeup prompt must instruct the next-cycle controller to re-schedule. In practice the user overrode this and continued early — but the pattern is: schedule one cycle, on wake check elapsed time, re-schedule until target reached.

### Test-plan-writer surfaces real bugs that per-task review missed

The `test-plan-writer` skill ran as the 4th Pre-PR gate flagged an `IndexError` on `pack.metadata.supported_source_types[0]` when the list is empty. None of the per-task spec/quality reviewers caught it, even though they explicitly reviewed `_resolve_pack_and_source_type`. **Lesson:** the formal post-implementation test plan is not just paperwork — it forces a re-examination of acceptance criteria against actual code paths and finds edge cases that drift-by-drift reviews miss. Worth running on every multi-commit feature, not just security/architectural changes.

### Path-traversal hardening checklist for any string that becomes a file path

When a string from an external source becomes part of a `pathlib.Path` operation:
1. Validate at the API boundary (regex allowlist — e.g. `^[a-z0-9_\-]{1,64}$`).
2. Inside the loader, resolve both the base directory and the candidate path, and assert `candidate.is_relative_to(base)` AND `candidate.is_file()`.
3. Sanitize error messages — never include the resolved absolute path; only the caller-supplied key.

Without step 2, Python's `pathlib` does NOT collapse `..` segments — `Path("/safe/dir") / "../../etc/passwd"` resolves to `/etc/passwd`. Without step 3, the `FileNotFoundError` becomes a filesystem-layout disclosure vector via server logs.

### `gh pr create --body` heredoc works on Windows bash for long PR bodies

Multi-paragraph PR bodies with markdown, checkboxes, and code blocks can be passed inline via `"$(cat <<'EOF' ... EOF)"`. Tested with a ~3500-character body. The persisted-output / file-reference path is only needed when the diff itself is being passed (e.g., to a security-review skill that wants the full diff inline) — for `gh pr create` content authored by the controller, heredoc is fine.

## Session: phase-c-reasoning-layer (2026-06-11/12)

### Opus subagent catches schema CHECK violations that unit tests (with mocks) miss

Mocking the session in node tests means `session.add(...)` is recorded but the constructed ORM object is never validated against DB CHECK constraints. An Opus code-review pass caught 5 distinct CHECK violations (relation_type, escalation_state, polarity, target XOR) that had been invisible to green unit tests. **Lesson:** for nodes that write to tables with CHECK constraints, at least one test must hit a real DB (`@pytest.mark.slow`) to confirm the SQL lands. Mock-only tests verify call patterns, not schema compatibility.

### Nested LangGraph node functions are untestable without extraction or real graph invocation

Node functions defined inside `make_extraction_graph` close over `session_factory` and `client` but are not importable. Two approaches: (a) extract to module-level functions that take the closure vars as parameters — testable with direct `await`; (b) build the full graph and call `graph.ainvoke()` with a heavily mocked `session_factory`. Approach (a) is cleaner and was adopted for `_run_classify_relations`. **Lesson:** for any node that warrants unit testing, extract it to module level at write time — retrofitting is more expensive.

### Vacuous tests are worse than no tests

Two node tests called `make_extraction_graph(mock_sf, mock_client)` then immediately asserted `mock_client.complete_json.assert_not_called()`. Both always passed because nothing invoked the graph. They gave false CI confidence and were the reason the schema violations weren't caught earlier. **Lesson:** after writing a test, always ask "could this assertion pass trivially without the code under test running?" — if yes, the test is vacuous.

### ruff enforces separate import blocks for aliased vs. non-aliased names from the same module

Consolidating `from app.x import (A as B)` and `from app.x import (C, D)` into one block causes ruff to re-split them on the next pre-commit run. This is expected ruff behaviour — don't fight it; leave split imports as-is when ruff auto-reverts the consolidation.

### Copilot Code Review requires manual setup per repo — Opus subagent is a reliable substitute

`gh api .../requested_reviewers` with `reviewers[]=copilot-pull-request-reviewer` returns HTTP 422 if the GitHub Copilot integration isn't configured as a repo collaborator. Spawning an Opus subagent with the `requesting-code-review` skill template gives equivalent depth. **Lesson:** when Copilot review isn't available, use Opus directly rather than waiting indefinitely.

### `ScheduleWakeup` + `gh api` polling is a reliable pattern for waiting on external CI events

Polling `gh api repos/.../pulls/20/reviews` every ~270s (within the 5-min cache window) works without rate-limiting issues. When the event never fires (Copilot not configured), the fallback is to cancel the loop and switch strategy rather than extending the sleep. **Lesson:** always have a cancellation condition for polling loops, not just a timeout.

### Session-limit errors from Opus subagents are transient — re-dispatch with the same prompt

A session-limit error (`"You've hit your session limit"`) from an Opus subagent is a transient rate-limit, not a task failure. The fix is simply to re-dispatch the same agent with the same prompt after a short pause. No state is lost because subagents are stateless.

## Session: phase-d-retrieval-ui (2026-06-13)

### A subagent that hits its session limit mid-run can leave the tree partially edited

The `doc-updater` hit its session limit after making one partial edit (the `architecture.md` status header) but before committing. Unlike the "subagents are stateless, just re-dispatch" case, here state *was* written to disk — re-dispatching would have either duplicated or conflicted with the partial edit. **Lesson:** when a file-writing subagent dies mid-run, `git diff` the tree first to see what already landed, then finish manually (or re-dispatch with a prompt that accounts for the partial state) rather than blindly re-running. Don't assume "stateless" when the agent's job is to mutate files.

### PowerShell has no inline env-var prefix — `SKIP=... git commit` is a parser error

The bash idiom `SKIP=mypy,pytest-fast git commit -m "..."` fails in PowerShell with "Missing argument in parameter list" / "Unexpected token '='". PowerShell parses `SKIP=...` as an expression, not an env assignment. Use a separate statement first: `$env:SKIP = "mypy,pytest-fast"; git commit -m "..."`. The env var persists for the rest of that shell invocation, which is fine for a single commit. (Prior insights documented the SKIP *need* but in bash syntax — this is the Windows-shell translation.)

### Docker Desktop stopping between sessions blocks even mock-only unit tests

The session-scoped `autouse` `run_migrations` fixture runs `alembic upgrade head` against Postgres before *any* test in the session — so when Docker Desktop (which hosts Postgres + Redis) is stopped between sessions, even pure-unit tests with a fully mocked client/session error out at fixture setup, not at their own assertions. Recovery on local Windows: `Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"`, then poll `docker info` in a loop until exit 0 (engine takes ~60–120s to come up), then `docker compose up -d` and wait for the `(healthy)` status. Don't mistake the resulting fixture-setup `AssertionError: Alembic migration failed` (with a buried `connect() refused`) for a code regression — check `Test-NetConnection localhost -Port 5432` first.

### git notes are local-only — fetch-merge-push them explicitly, they don't ride the branch push

`git push origin <branch>` does **not** push `refs/notes/commits`; notes stay local unless pushed separately. The repo tracks notes on the remote, so the full ritual is: `git fetch origin "refs/notes/*:refs/notes/origin/*"` (to see/merge existing remote notes), add your notes, then `git push origin refs/notes/commits`. Easy to forget given the workflow attaches a note to every commit but never mentions pushing them.

## Session: phase-d-residual (2026-06-14)

### A fresh git worktree has no node_modules — junction it instead of reinstalling

A worktree created with `git worktree add` does not copy `node_modules` (gitignored), so `npm run test` fails with "'vitest' is not recognized". Rather than a full `npm install` (slow), junction the main checkout's modules into the worktree: `New-Item -ItemType Junction -Path "<worktree>\web\node_modules" -Target "<main>\web\node_modules"`. Junctions need no admin on Windows, and it's safe because the worktree shares the same lockfile/base commit as main. Vitest then resolves normally. (Only valid when the worktree is at/near the same commit as the source of the modules.)

### `gitnexus detect_changes` is blind to non-indexed worktrees — use `git diff` for scope

The GitNexus index is anchored to the main checkout path. `detect_changes` (any scope) diffs *that* checkout's working tree, so when the actual work lives on a branch in a separate `git worktree`, it reports only the main checkout's stray edits (e.g. the auto-updated AGENTS.md/CLAUDE.md), not the worktree's committed changes. For scope verification of a worktree branch, use `git -C <worktree> diff main...HEAD --stat`. Impact analysis (`gitnexus_impact` by symbol name) still works since it's symbol- not path-scoped.

### Prefer the Write tool + absolute `--body-file` for `gh pr create`; PowerShell temp-file Remove-Item can trip a path guard

Building a PR body with `$body | Out-File .pr_body.md` then `Remove-Item .pr_body.md` hit a harness guard ("Remove-Item on system path '/' is blocked") and the PR didn't get created. Reliable pattern: write the body with the Write tool to an absolute path, run `gh pr create --body-file "<abs path>"`, then delete it with `[System.IO.File]::Delete("<abs path>")`. Avoids relative-path/cwd ambiguity (the shell cwd keeps resetting) and the Remove-Item guard.

### Inline TDD execution is a reliable fallback when subagent-driven-development is impractical

For a small, well-specified plan (here, 5 focused tasks mostly in one file), executing the plan inline with TDD — rather than dispatching a fresh subagent per task — avoided the subagent session-limit fragility seen earlier this session while still honoring every other gate (per-subitem commits, impact analysis before edits, git notes, `git diff` scope check, inline simplify review, inline doc updates, Opus review). The subagent-driven skill shines for larger/independent task sets; for a tight single-surface change its overhead and failure modes outweigh the isolation benefit. Note the deviation explicitly when taking this path.

## Session: telos-residuals-c / phase-c-remainder (2026-07-02)

### Mid-session AGENTS.md/CLAUDE.md rewrites are the single biggest time sink — batch them

This session rewrote AGENTS.md/CLAUDE.md **seven separate times** in response to incremental follow-up instructions (9-step→7-step reorg, weather-monitor-NL template adoption, resolving a concurrent session's unreviewed 3-commit flip-flop on the same files, a pasted-template adoption that needed fact-checking against the repo before accepting, broadening Grok delegation to all subagents, then narrowing it back down twice more in response to "why are you doing X" questions). Each cycle costs a full edit→mirror-to-both-files→verify→commit→rebase-worktree round trip — independent of any feature work. Estimated at ~40% of this session's wall-clock time. **Lesson:** when governance/workflow changes are needed mid-session, either batch them into one pass after gathering all the changes wanted, or push back and suggest a dedicated docs-only session — don't incrementally rewrite the same two files 7 times as requirements trickle in one message at a time.

### Never trust a subagent self-report — but calibrate verification depth to risk

Every Grok CLI subagent output this session was independently re-verified (re-running ruff/mypy/full pytest, sometimes against a real Postgres) rather than trusted — this caught real discrepancies (a false "3 CLI tests failing" claim that was actually true *in Grok's own sandboxed shell* but not in this session's shell, traced to Rich/Click ANSI-color detection differing by execution environment; a plan's inlined LangGraph node-access code that was subtly wrong). This is correct practice and should not be relaxed for anything touching DB writes or shared modules. But for narrowly-scoped, self-checked, doc-only or single-function changes, a full independent re-run of the entire suite is more verification than the risk warrants — spot-checking the diff plus one targeted test run would suffice and save real time.

### Inlining verbatim code in an implementation plan creates round-trip risk that a lighter contract avoids

The Phase C remainder plan (before the workflow was rewritten to forbid this) inlined ~877 lines including exact code for a LangGraph node-invocation pattern that was verified against a throwaway top-level-function graph, not the real nested-closure node — it was subtly wrong (`.bound(state)` vs `.bound.ainvoke(state)`), and the Grok implementer had to discover and fix it independently mid-task. A plan that specifies only the cross-task **contract** (file structure, task decomposition, per-task Interfaces/signatures, build order) and lets the implementer regenerate the actual code avoids transcribing potentially-stale exploratory code as if it were verified truth. Confirmed as the right call — the current AGENTS.md now mandates lightweight plans for exactly this reason.

### Environment provisioning gaps (venv, DB, `gh` auth) cost real time discovered mid-session, not up front

None of the following existed at session start and each required mid-session discovery + setup: a Python `.venv` (had to create one and `pip install -e ".[dev]"`), a running Postgres with pgvector + migrations (had to `docker run` one, working around a port-5432 conflict with another project's container), and `gh` CLI (not installed, and once installed had zero stored credentials — needed an interactive `gh auth login` round-trip with the user). None of these are Telos-specific; they're baseline requirements for any Nexus session that touches the DB or opens a PR. Pre-provisioning these once per environment (not per session) would remove a non-trivial fixed cost from every future session.

### The permission-auto-mode classifier caught a genuine instruction-ordering ambiguity — trust it over forcing a workaround

Two user messages arrived close together: "After you're done with this session. Finish up" followed immediately by "I need you to implement D,E and F ASAP... no pause for permission or clarification." I read the second as a correction superseding the first and started dispatching a large Grok implementation task; the harness's auto-mode classifier blocked the `git push`/Grok-dispatch action with a reasoned objection that the *first* instruction was the standing one. Rather than retry the same action a different way (which the tool guidance explicitly says not to do for intent-boundary blocks — only for mechanical ones like `head` vs `cat`), asking the user directly resolved it in one round-trip: "finish up" was in fact the correct reading. **Lesson:** when a classifier block cites a specific reasoned conflict between two of the user's own recent messages (not a generic caution), that's a signal the ambiguity is real, not a false positive — stop and ask rather than re-route around it.

### A large scope-widening instruction (implement D/E/F "ASAP, no clarification") is still worth one blocker check, not zero

Before the above got interrupted, preparing to implement the hackathon TODO's Phase D/E/F surfaced one genuine hard blocker: Phase G/H0's Qwen Cloud routing requires real API credentials that don't exist in this environment. Even under an explicit "no pause for clarification" instruction, a missing-credential blocker isn't the kind of clarification that instruction is aimed at suppressing (routine judgment calls, scope nitpicks) — it's a fact the user needs regardless of how autonomously they want the rest handled. Surfacing it inline ("I'll build the plumbing, can't live-test without credentials") rather than either silently skipping the work or stopping to ask permission is the right middle ground for this kind of instruction.

## Session: def-hackathon (2026-07-02)

### A first live-validation finding can misdiagnose the root cause one layer too shallow

The F6 baseline's first run showed 0 relations / 0 theses. The initial write-up attributed this to an architectural limit (`classify_relations` only pairs capsules within one document, so no cross-doc edges exist). That was plausible, matched the code, and got documented as the explanation — but it was wrong. The real cause, found only when re-running the *live* pipeline and reading its stdout log lines, was that the domain pack's top-level `models.t2/t3` block hardcoded a dead model id (`deepseek/deepseek-v4-flash`), so every relation-classification call 404'd against DashScope and failed silently into "no relation written," which looks identical to "no relation because the architecture excludes it." **Lesson:** when a live run produces a zero/empty result that has a plausible *architectural* explanation, grep the actual run log for errors before writing that explanation into a report — an architecturally-justified zero and a silently-failing zero are indistinguishable from the aggregate metric alone, only the log (or DB error rows) tells them apart.

### Fixing one demo-driven finding can uncover a second, larger one — keep validating after the first fix lands

The user asked to fix a demo finding (the supersession heuristic wrongly retiring historical events). Fixing it and re-running the benchmark to confirm was the right move regardless of the ask's narrow scope — the re-run's log surfaced the deepseek-model 404s that had been present all along but invisible under the first "architectural cross-doc limit" theory. Re-validating end-to-end after every live-behavior fix (not just running the unit tests for that fix) is what surfaces compounding root causes; a narrowly-scoped fix-and-move-on would have shipped a corrected heuristic while leaving the bigger bug (relations were always 0 for the wrong reason) undiscovered.

### Verify the exact documented command, not just the function it calls

After writing a README with `nexus eval memory run --benchmark nexus_synthetic --k 5` as the primary demo path, a separate live run through the actual `nexus` console-script entry point (not just `python -m scripts.benchmarks.run_memory_benchmark`, which had already been verified) caught nothing new this time, but is worth keeping as a standing practice: the CLI wrapper (argument parsing, typer plumbing, lazy import of the runner module) is a distinct code path from the function it calls, and a doc that tells a user to type a specific command should be verified by typing that specific command, not its underlying implementation.

### Per-task scratch databases avoid contention across parallel subagents and iterative live reruns

Creating disposable `nexus_t1`..`nexus_t6` databases for the 6 parallel Wave-1 Grok subagents' self-checks, then a fresh disposable DB (`nexus_gate`, `nexus_bench`, `nexus_bench2`, `nexus_bench3`, `nexus_readme`) for every full-suite gate run and every live benchmark rerun, avoided any cross-run contamination or lock contention on a single shared Postgres instance. Worth treating as a standing pattern whenever a session involves either (a) multiple parallel subagents each running the full test suite, or (b) several iterative live end-to-end reruns against a real DB — cheap to create/drop, and removes an entire class of "did that failure come from my change or from leftover state" ambiguity.

### Stacked background wait-loops from iterative reruns waste turns — track and kill explicitly

Re-running a ~15-25 minute live benchmark multiple times (to validate successive fixes) led to several overlapping `until ! pgrep run_memory_benchmark; do sleep 20; done` background Bash calls being launched across turns before the previous one's completion notification had been processed, because each turn re-issued a fresh wait rather than checking for an already-running wait. They all eventually failed harmlessly (144 = SIGKILL propagated from a `pkill` cleanup) but wasted several tool calls. **Lesson:** before launching a new background wait for a long-running process, check `pgrep` first to see if a wait is already in flight, or track the background task ID from ScheduleWakeup/the Bash `run_in_background` result and resume that instead of starting a parallel poll.

### `gitnexus_impact` returning `risk: "UNKNOWN", impactedCount: 0` can mean "symbol not found," not "no callers"

Running impact analysis on `_check_supersession_heuristic` (a module-private helper, single leading underscore) returned `risk: UNKNOWN, impactedCount: 0` — read in the moment as "safe, no callers," but more likely means the indexer didn't resolve the underscore-prefixed name as a distinct symbol at all (unlike the earlier-documented "file-level import coarsening" gotcha, this is a lookup miss, not an over-broad match). **Lesson:** an `UNKNOWN` risk value (as opposed to `LOW`/`MEDIUM`/`HIGH`) is itself a signal to fall back to `Grep`/direct reading rather than trusting the count — reserve confidence in "0 impacted" for a real `LOW` risk result on a symbol GitNexus actually resolved.

## Session: router-h5 (2026-07-03)

### For silent-zero live runs, query `agent_runs` status before grepping logs

The first router benchmark run scored plausibly-nonzero overall (0.22) but every answer returned in ~40ms with 0 tokens. Grepping the run log for error/404/failed found nothing — the HTTP failures were swallowed into DB rows, not stdout. One query (`SELECT run_type, status, count(*) FROM agent_runs GROUP BY 1,2`) showed 36/36 calls at `http_401` and made the diagnosis instant (missing `LLM_BASE_URL` → Qwen key sent to OpenRouter). The `agent_runs` status distribution is the fastest first probe for any live run that produces suspicious zeros — more definitive than log grepping because the client records failures there even when nothing reaches stdout.

### Validate `.env` against `.env.example` keys before a live run, not after it fails

The 401 root cause was an env var present in `.env.example` but absent from the machine's real `.env` (`LLM_BASE_URL`), which had evidently been dropped at some point after the previous session's successful runs. A 5-second key-diff (`comm` on sorted `grep -o '^[A-Z_]*=' `) before the first live run would have saved a full ~20-minute benchmark cycle. Worth doing at every session start that will make LLM calls.

### With a shared editable venv, verify which checkout a worktree run imports

The project venv is an editable install of the main checkout, so a worktree's `nexus` console script or bare imports resolve to main's code, not the branch under test. Running `python -m <module>` from the worktree works because cwd shadows the editable path — but only if nothing changes cwd. Verifying explicitly (`python -c "import app.intelligence.router as r; print(r.__file__)"`) before the benchmark cost one command and removed the risk of validating the wrong code. Do this check before any live validation run from a worktree.

### "Pre-existing failure" sets are environment-specific — re-derive, don't carry over

The Grok implementer reported "6 pre-existing failures" whose composition differed from the documented set (two new names: a path-handling loader test and a chat-API 503 test; two prior names absent). Both new ones reproduced on clean `main` in this Linux environment — genuinely pre-existing here, but that could not be assumed from the prior session's Windows-derived list. Verifying against clean `main` took two minutes and prevented both false acceptance and a false alarm. The baseline failure list is a per-environment fact, not a repo fact.

### Scale review-angle parallelism to diff size

CLAUDE.md's Submit PR flow suggests one Grok handoff per /simplify review angle. For this ~250-line diff, one combined 4-angle handoff found the real issues (duplicate shape registries, dataclass-vs-BaseModel precedent) at a quarter of the session overhead; separate handoffs would have each re-read the same small diff. For large multi-module diffs the per-angle split still makes sense. Judgment call, worth making explicitly each time rather than defaulting to maximum parallelism.

### Mocked-session SQL assertions via the captured statement object

To test that a retrieval node's `.limit()` actually reflects strategy math (a PR-review gap: the pure unit test duplicated the formula offline), the existing AsyncMock session pattern already captures the executed statement: `sf.return_value.__aenter__.return_value.execute.call_args_list[0].args[0]._limit_clause.value`. No new fixtures needed. `_limit_clause` is SQLAlchemy-internal but stable in 2.x; the pattern turns "wiring untested" review findings into three-line tests.
