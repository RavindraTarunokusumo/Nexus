# CLAUDE.md

Project: `Nexus`

Feature implementation is spec-driven. User or agent queries may create, refine, or supply plans/specs, but implementation work must be driven by an accepted plan/spec — produced via the `brainstorming` skill under `docs/superpowers/plans/` and `docs/superpowers/specs/` — not by chat prompts alone. Follow the 7-Step Workflow strictly against the active plan/spec. Do not start implementation until Steps 1-3 are complete and Step 4 has logged plan-derived TODO items, unless the user explicitly authorizes a different flow. Before editing, state which step you are on. Before finishing, confirm Step 6 and Step 7. After PR submission, complete [Post-PR Cleanup](#post-pr-cleanup) and [Session Reflection](#session-reflection) as applicable.

Any change made to `AGENTS.md` should also be applied to `CLAUDE.md`.

## Project Map

- Architecture: [docs/architecture.md](docs/architecture.md)
- Database / Persistence: [docs/database.md](docs/database.md)
- Patterns: [docs/patterns.md](docs/patterns.md)
- Testing: [docs/testing.md](docs/testing.md)
- Commands: [docs/commands.md](docs/commands.md)
- CLI: [docs/cli.md](docs/cli.md)
- Agent Harness: [docs/agent-harness.md](docs/agent-harness.md)
- Spec Set: [docs/specs/README.md](docs/specs/README.md) (static product/architecture spec set; per-task plans/specs from `/brainstorming` live under `docs/superpowers/plans/` and `docs/superpowers/specs/`)
- Insights: [docs/insights.md](docs/insights.md)
- Full Index: [docs/index.md](docs/index.md)

## Code Graph / Repo Map

This repo is indexed by **GitNexus** — see the GitNexus section below for all rules and resources. Query the graph first, then read files directly. Do not rebuild the index while files are being modified; only rebuild on a clean working tree.

## 7-Step Workflow

1. **Preamble**
   - Ensure you're in a dedicated local branch/worktree under `.worktree/<session-name>` and activate the virtual environment `.venv` located in the root directory.
   - Read `docs/insights.md` and the [Workflow Rules](#workflow-rules).
   - Confirm repo status (`git status`) before editing.
   - Identify the active accepted plan/spec path under `docs/superpowers/plans/` and `docs/superpowers/specs/`, if one exists for this task.

2. **Repo Map**
   - Read the [GitNexus](#gitnexus--code-intelligence) section at the start of every session.
   - Use GitNexus (`gitnexus_query`, `gitnexus_context`) to understand the areas named by the active task before reading files directly.

3. **Planning**
   - Read `AGENTS.md`, `docs/index.md`, the active plan/spec, and relevant docs in the [Project Map](#project-map).
   - If no accepted plan/spec exists, use the `brainstorming` skill to create or refine one before implementation planning.
   - Produce a concise plan and scope derived from the accepted plan/spec.
   - Do not edit until the plan is accepted, unless the user has explicitly granted autonomous execution in the current session.

4. **Implementation**
   - Log plan-derived tasks and sub-items in `TODO.md` before editing; include the active plan/spec path in the `TODO.md` session entry.
   - Implement each task by delegating to a **Grok subagent as the implementer** via the non-interactive CLI, one ephemeral session per task where practical (see [Grok Build Implementation/Review Handoff](#grok-build-implementationreview-handoff)).
   - Grok implementation prompts must be self-contained, point at the active plan/spec and exact file scope, forbid git operations, require full self-checks, and require a final summary plus `sessionId`.
   - After each Grok handoff, the senior dev independently reviews the diff, normalizes output, validates with full lint/typecheck/tests before committing, then deletes the ephemeral Grok session directory.
   - If Grok is unavailable or blocked, report that clearly and fall back to the `subagent-driven-development` skill only after recording the fallback reason in `TODO.md`.

5. **Commit**
   - Run `pre-commit run --all-files` before each commit.
   - Each meaningful TODO sub-item should land as its own commit.
   - Use specific staging; never use `git add -A`.
   - Attach a git note using the [template](.github/git_notes_template.md); include the active plan/spec path in the note.
   - Cross off completed TODO sub-items, tagged with the commit hash.

6. **Pre-PR**
   - Confirm the implementation still matches the accepted plan/spec.
   - Do the [Pre-PR](#pre-pr) workflow.

7. **Submit PR**
   - Follow the instructions in the [Submit PR](#submit-pr) workflow and notify the user once every step has been completed.

## Autopilot Mode

Autopilot Mode allows implementation to proceed through Steps 3-5 without pausing for plan acceptance between each step.

Rules:

- Autopilot Mode must be explicitly granted by the user in the current session; it is never assumed, never carried over from a prior session, and is never granted by a PM/chat-relay instruction alone.
- Autopilot Mode does not waive the accepted-plan/spec requirement: implementation must still be driven by an accepted plan/spec under `docs/superpowers/plans/` + `docs/superpowers/specs/`, or the session must complete plan/spec creation/refinement first.
- Autopilot Mode does not waive TODO logging, Grok implementation/review handoffs, specific staging, per-sub-item commits, git notes, or Pre-PR/Post-PR validation.
- Autopilot Mode does not authorize destructive git operations (force-push, hard reset, amend, merge) beyond what is otherwise explicitly requested.
- If a discovery during implementation contradicts the plan or spec (e.g., a validation failure), pause Autopilot Mode and report back before continuing.

## Workflow Rules

1. Every TODO sub-item should land as its own commit.
2. Any extension or modification to the task must update the active plan/spec first, then be logged in `TODO.md`.
3. Use specific staging, never `git add -A`.
4. Never force-push, reset `--hard`, merge, or amend unless explicitly asked.
5. Keep comments sparse, naming clear, abstractions minimal, and avoid compatibility shims.
6. When `pre-commit run --all-files` fails only on files you did not touch, note it as pre-existing and proceed — do not attempt workarounds that affect other files.
7. After subscribing to PR activity, wait for Copilot Code Review (allow ~20 min) and address all findings before marking the session complete.
8. After context compaction resumes, run `git status` before any other action — the summary describes intent, not exact commit state.
9. Commit any files written by subagents (Grok, doc-updater, security-review, etc.) immediately; do not advance the workflow with a dirty tree.
10. `gitnexus_impact` requires the exact function/class name, not the module or file name. Use the symbol name as indexed (e.g. `answer_chat`, not `routes_chat`).
11. A chat prompt is not implementation authority by itself; it either supplies an accepted plan/spec or starts plan/spec creation/refinement.
12. Do not implement from a plan/spec with unresolved blocking open questions.

## Grok Build Implementation/Review Handoff

The canonical contract for delegating implementation tasks and PR reviews is a short-lived Grok CLI subagent session. Claude is the senior dev: it writes or self-accepts plans/specs where authorized, decomposes work, reviews diffs, validates, commits, and cleans up. Grok is the junior implementer/reviewer for bounded tasks.

**Invoke** (headless, single-turn, no TUI):

```bash
HOME=/root grok -p "<self-contained task instructions>" -m grok-composer-2.5-fast --effort high --yolo --output-format json
```

- Use `--effort high` by default; use `--effort xhigh` for complex cross-module tasks or difficult reviews.
- `--yolo` auto-approves Grok's tools inside the delegated task; the senior dev remains responsible for reviewing all changes before commit.
- `--output-format json` is required so the senior dev can capture `text` and `sessionId`.

**Prompt requirements:**

- Start from cold context: include the active plan/spec path, relevant TODO item, exact scope, files or module boundaries, and validation expectations.
- For implementation tasks, forbid all git operations; the senior dev owns staging, commits, notes, PRs, and cleanup.
- Require deterministic checks relevant to the task and, when practical, full `ruff check`, `mypy app/`, and `pytest` self-checks (plus `npm run lint` / `npm test` in `web/` for frontend changes) before reporting.
- Require a concise final summary with files changed, checks run, blockers, and the returned `sessionId`.

**Senior-dev processing:**

- Parse the JSON result and capture `sessionId`.
- Review the diff directly; do not trust the implementer's self-report.
- Run full project validation before each commit: `pre-commit run --all-files`, plus any plan/spec-required checks.
- Run `gitnexus_detect_changes()` to confirm the diff only touches expected symbols/flows.
- Stage specific files only; never use `git add -A`.
- Attach a git note using `.github/git_notes_template.md`.

**Cleanup (always):**

```bash
find "$HOME/.grok/sessions" -type d -name "$sessionId" -prune -exec rm -rf {} +
```

**PR review handoff:**

- Nexus's primary PR review gate remains GitHub Copilot Code Review (see [Submit PR](#submit-pr)): submit the PR, wait ~20 min, address findings via `/receiving-code-review`.
- Additionally, delegate a Grok security review when the change touches auth, secrets, network calls, privileged operations, user input, or security-sensitive architecture — same trigger as the `security-review` Pre-PR gate.
- If Copilot review isn't available/configured for this repo, fall back to an Opus subagent review before falling back further to a Grok review (see `docs/insights.md` for the established substitution pattern).
- Process findings rigorously: verify each item technically, implement only warranted fixes, push back on incorrect findings, re-run validation, and clean up the Grok session directory.

**Parallelism:**

- Parallel Grok implementation is allowed only for independent tasks with disjoint files and no shared dependency on unlanded work, preferably in isolated worktrees.
- Otherwise, delegate sequentially so each sub-item can be reviewed, validated, committed, and noted independently.

### Pre-PR

Use the following as the final steps before submitting a PR:

- `/simplify` (skill)
- `doc-updater` (subagent)

**Invoke the following subagents IF changes affect security or significant architectural changes (or explicitly stated). Always cite your justification on why you decide to invoke them:**

- `test-plan-writer` (subagent)
- `security-review` (skill) — or the Grok security review handoff above

### Submit PR

- Fill out the **[Template](.github/pull_request_template.md)**.
- Submit the PR and wait for about 20m for the GitHub Copilot Code Review agent to finish writing the reviews.
- Use the `/receiving-code-review` skill to address the issues in the Copilot Code Review.

## Pre-Commit Checks

```bash
# Python backend
ruff check . --fix
ruff format .
mypy app/
pytest

# JS/TS frontend (web/)
npm run lint
npm test
```

If a tool is missing or unavailable, report it clearly at the end of the session.

## Post-PR Cleanup

Archive completed TODO items from `TODO.md` into `docs/iterations/archive/`, including the related plan/spec path, and ensure each subitem in the TODO is tagged with the commit hash and each session is tagged with the merge ID. `TODO.md` should only contain **active or future** work only.

## Session Reflection

After every session completion, you reflect on how the workflow pertaining to the workflow and agent harness - the commands you executed (and which failed consistently), the tools you used, skills invoked, MCP accessed, etc. **Do not include anything feature-specific**. For example, when the Graphify output is too verbose or if certain powershell commands keeps failing. This is not about the features you implemented, but about *how* you implemented them. Write this down in [Insights](docs/insights.md) and then report it to the user in chat. Wait until user gives explicit permission to conclude the session. After receiving confirmation from the user, delete the worktree and branch.

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
