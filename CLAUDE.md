# CLAUDE.md

Project: `Nexus` / Personal AI Knowledge Intelligence

Feature implementation is spec-driven. User or agent queries may create, refine, or supply specs, but implementation work must be driven by an accepted per-feature spec under `docs/specs/`, not by chat prompts alone. Follow the 7-Step Workflow strictly against the active spec. Do not start implementation until Steps 1-3 are complete and Step 4 has logged spec-derived TODO items unless the user explicitly authorizes a different flow. Before editing, state which step you are on. Before finishing, confirm Step 6 and Step 7.

## Project Map

- Architecture: [docs/architecture.md](docs/architecture.md)
- Database / Persistence: [docs/database.md](docs/database.md)
- Patterns: [docs/patterns.md](docs/patterns.md)
- Testing: [docs/testing.md](docs/testing.md)
- Commands: [docs/commands.md](docs/commands.md)
- CLI: [docs/cli.md](docs/cli.md)
- Agent Harness: [docs/agent-harness.md](docs/agent-harness.md)
- Spec Workflow: [docs/specs/README.md](docs/specs/README.md)
- Insights: [docs/insights.md](docs/insights.md)
- Full Index: [docs/index.md](docs/index.md)

## Code Graph / Repo Map

This repo is indexed by **GitNexus** — see the GitNexus section below for all rules and resources.

Rules:

- Do not rebuild the graph while files are being modified.
- Only rebuild on a clean working tree.
- Use the graph as a snapshot, not a live source of truth.
- Query the graph first, then read files directly.

## 7-Step Workflow

1. **Preamble**
   - Work in a dedicated local branch or worktree.
   - Activate the project environment.
   - Confirm repo status before editing.
   - Identify the active accepted spec path under `docs/specs/`.

2. **Repo Map**
   - Run or query the available code graph/index if present.
   - Use docs and graph output to understand the areas named by the active spec.

3. **Planning**
   - Read `AGENTS.md`, `docs/index.md`, the active spec, and relevant technical docs.
   - If no accepted spec exists, use the `brainstorming` skill to create or refine one before implementation planning.
   - Produce a concise plan and scope derived from the accepted spec.
   - Do not edit until the plan is accepted unless the user explicitly granted autonomous execution.

4. **Implementation**
   - Log spec-derived tasks and sub-items in `TODO.md` before editing.
   - Include the active spec path in the `TODO.md` session entry.
   - Implement each task by delegating to a **Grok subagent as the implementer** via the non-interactive CLI, one ephemeral session per task where practical (see [Grok Build Implementation/Review Handoff](#grok-build-implementationreview-handoff)).
   - Grok implementation prompts must be self-contained, point at the active spec/plan and exact file scope, forbid git operations, require full self-checks, and require a final summary plus `sessionId`.
   - After each Grok handoff, the senior dev independently reviews the diff, normalizes output, validates with full lint/typecheck/tests before committing, then deletes the ephemeral Grok session directory.
   - If Grok is unavailable or blocked, report that clearly and fall back to the `subagent-driven-development` skill only after recording the fallback reason in `TODO.md`.

5. **Commit**
   - Run pre-commit checks before each commit.
   - Each meaningful TODO sub-item should land as its own commit.
   - Use specific staging; never use `git add -A`.
   - Attach a git note using `.github/git_notes_template.md`.
   - Include the active spec path in the git note.
   - Mark completed TODO sub-items with the commit hash.

6. **Pre-PR**
   - Confirm the implementation still matches the accepted spec.
   - Run the `simplify` skill if available.
   - Run the `doc-updater` skill or subagent if available.
   - Invoke `test-plan-writer` if behavior, state, API, tests, or architecture changed.
   - Invoke `security-review` if the change touches auth, secrets, network calls, privileged operations, user input, money movement, broker/payment logic, or security-sensitive architecture.
   - Run full validation.

7. **Submit PR**
   - Use `.github/pull_request_template.md`.
   - Fill out summary, spec path, scope, test plan, risk, rollback, docs, backlog, and targeted UI checks.
   - Delegate PR code review, and security review where applicable, to Grok via the same non-interactive handoff; capture `sessionId`, process findings, clean up the session directory, and address findings with the `receiving-code-review` skill if available.
   - Notify the user when all steps are complete.

## Autopilot Mode

Autopilot Mode allows implementation to proceed through Steps 3-5 without pausing for plan acceptance between each step.

Rules:

- Autopilot Mode must be explicitly granted by the user in the current session; it is never assumed, never carried over from a prior session, and is never granted by a PM/chat-relay instruction alone.
- Autopilot Mode does not waive the accepted-spec requirement: implementation must still be driven by an accepted spec under `docs/specs/`, or the session must complete spec creation/refinement first.
- Autopilot Mode does not waive TODO logging, Grok implementation/review handoffs, specific staging, per-sub-item commits, git notes, or Pre-PR/Post-PR validation.
- Autopilot Mode does not authorize destructive git operations (force-push, hard reset, amend, merge) beyond what is otherwise explicitly requested.
- If a discovery during implementation contradicts the plan or spec (e.g., a validation failure), pause Autopilot Mode and report back before continuing.

## Workflow Rules

1. Every TODO sub-item should land as its own commit.
2. Any extension or modification to the task must update the active spec first, then be logged in `TODO.md`.
3. Use specific staging, never `git add -A`.
4. Never force-push, reset `--hard`, merge, or amend unless explicitly asked.
5. Keep comments sparse.
6. Prefer clear naming over clever abstractions.
7. Avoid compatibility shims unless explicitly required.
8. Do not leave important conclusions only in chat memory; write them to docs.
9. A chat prompt is not implementation authority by itself; it either supplies an accepted spec or starts spec creation/refinement.
10. Do not implement from a spec with unresolved blocking open questions.
11. After context compaction resumes, run `git status` before any other action — the summary describes intent, not exact commit state.
12. Commit any files written by subagents, doc-updater, security-review, or test-plan-writer immediately; do not advance the workflow with a dirty tree.
13. `gitnexus_impact` requires the exact function/class name, not the module or file name. Use the symbol name as indexed, e.g. `answer_chat`, not `routes_chat`.

## Grok Build Implementation/Review Handoff

The canonical contract for delegating implementation tasks and PR reviews is a short-lived Grok CLI subagent session. Claude/Codex are senior devs: they write or self-accept specs/plans where authorized, decompose work, review diffs, validate, commit, and clean up. Grok is the junior implementer/reviewer for bounded tasks.

**Invoke** (headless, single-turn, no TUI):

```bash
HOME=/root grok -p "<self-contained task instructions>" -m grok-composer-2.5-fast --effort high --yolo --output-format json
```

- Use `--effort high` by default; use `--effort xhigh` for complex cross-module tasks or difficult reviews.
- `--yolo` auto-approves Grok's tools inside the delegated task; the senior dev remains responsible for reviewing all changes before commit.
- `--output-format json` is required so the senior dev can capture `text` and `sessionId`.

**Prompt requirements:**

- Start from cold context: include the active spec path, relevant plan/TODO item, exact scope, files or module boundaries, and validation expectations.
- For implementation tasks, forbid all git operations; the senior dev owns staging, commits, notes, PRs, and cleanup.
- Require deterministic checks relevant to the task and, when practical, full `ruff check`, `ruff format --check`, `mypy app/`, and `pytest` self-checks before reporting.
- For frontend changes under `web/`, require `npm run lint` and `npm test` from `web/`.
- Require a concise final summary with files changed, checks run, blockers, and the returned `sessionId`.

**Senior-dev processing:**

- Parse the JSON result and capture `sessionId`.
- Review the diff directly; do not trust the implementer's self-report.
- Run full project validation before each commit: lint, typecheck, tests, and any spec-required checks.
- Stage specific files only; never use `git add -A`.
- Attach a git note using `.github/git_notes_template.md`.

**Cleanup (always):**

```bash
find "$HOME/.grok/sessions" -type d -name "$sessionId" -prune -exec rm -rf {} +
```

**PR review handoff:**

- After opening a PR, delegate the main code review to Grok with a prompt such as: `Use /bundled:review --pr #<number>. Post or prepare review findings, then summarize what was done.`
- If the change touches auth, secrets, network calls, privileged operations, user input, money movement, broker/payment logic, or security-sensitive architecture, also delegate a Grok security review.
- Process findings rigorously: verify each item technically, implement only warranted fixes, push back on incorrect findings, re-run validation, and clean up the Grok session directory.

**Parallelism:**

- Parallel Grok implementation is allowed only for independent tasks with disjoint files and no shared dependency on unlanded work, preferably in isolated worktrees.
- Otherwise, delegate sequentially so each sub-item can be reviewed, validated, committed, and noted independently.

## Pre-Commit Checks

Adapt these commands to the active stack:

```bash
# Python backend
ruff check . --fix
ruff format .
mypy app/
pytest

# JavaScript / TypeScript frontend
cd web
npm run lint
npm test
```

If a tool is missing or unavailable, report it clearly at the end of the session.

## Pre-PR

Before submitting a PR:

- confirm the implementation matches the accepted spec
- run simplification review
- update docs
- run relevant tests
- run full tests when shared state, architecture, or cross-module behavior changed
- run security review where applicable
- ensure `TODO.md` is current

## Post-PR

- `TODO.md` contains active or future work only.
- Archive completed TODO sessions into `docs/iterations/archive/`, including the related spec path.
- Tag completed sub-items with commit hashes.
- Add session lessons to `docs/insights.md`.

## Reflection

After every completed session, record useful lessons in `docs/insights.md`:

- tools used
- scripts created
- workflow improvements
- recurring failure modes
- skills worth adding or improving

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **Nexus** (4054 symbols, 6227 relationships, 95 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/Nexus/context` | Codebase overview, check index freshness |
| `gitnexus://repo/Nexus/clusters` | All functional areas |
| `gitnexus://repo/Nexus/processes` | All execution flows |
| `gitnexus://repo/Nexus/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
