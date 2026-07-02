AGENTS.md

Project: `Nexus` / Personal AI Knowledge Intelligence

**Follow the [Workflow](#workflow) strictly for feature implementation**. Do not start implementation until Steps 1-3 are complete. Before editing, show which step you are on.

Any change made to `CLAUDE.md` should also be applied to `AGENTS.md`.

## Project Map

- Architecture: [docs/architecture.md](docs/architecture.md)
- Database / Persistence: [docs/database.md](docs/database.md)
- Patterns: [docs/patterns.md](docs/patterns.md)
- Testing: [docs/testing.md](docs/testing.md)
- Commands: [docs/commands.md](docs/commands.md)
- CLI: [docs/cli.md](docs/cli.md)
- Agent Harness: [docs/agent-harness.md](docs/agent-harness.md)
- Spec Set: [docs/specs/README.md](docs/specs/README.md) (static product/architecture spec set; per-task specs/plans live under `docs/superpowers/specs/` and `docs/superpowers/plans/`)
- Insights: [docs/insights.md](docs/insights.md)
- Full Index: [docs/index.md](docs/index.md)

## Code Graph / Repo Map

This repo is indexed by **GitNexus** — see the [GitNexus](#gitnexus--code-intelligence) section below for all rules and resources. Use it before touching unfamiliar code.

Rules:

- Do not rebuild the graph while files are being modified.
- Only rebuild on a clean working tree.
- Use the graph as a snapshot, not a live source of truth.
- Query the graph first, then read files directly.

## Workflow

1. **(Preamble)** Ensure you're in a dedicated local branch/worktree under `.worktree/<session-name>` and activate the project environment (Python `.venv` in the repo root; `npm install` in `web/` for frontend work — see [docs/commands.md](docs/commands.md)). Read `docs/insights.md` and the [Workflow Rules](#workflow-rules).
2. **(GitNexus)** Read the [GitNexus](#gitnexus--code-intelligence) section at the start of every session.
3. **(Spec Writing + Lightweight Plan)** For feature implementation, write a detailed specification document following a spec-driven process (requirements, data models, interfaces, workflows, edge cases, success criteria, constraints) under `docs/superpowers/specs/`. Do not write implementation plans or code until the spec is complete and accepted — use the `brainstorming` skill to produce or refine it. Read the docs (see [Project Map](#project-map)) and use GitNexus as your primary means to understand the codebase. For debugging or minor patching, skip this step. Once the spec is accepted, produce a **lightweight implementation plan** under `docs/superpowers/plans/` that serves as the Grok implementer's contract — file structure, task decomposition, per-task **Interfaces** (Consumes/Produces signatures), build order, and risks. Do **not** inline verbatim per-step code or exact shell commands; the implementer regenerates those from the contract. The plan's value is the cross-task contract (who calls what, in what order), not transcribed code — that contract is what catches the class of bug a narrowly-scoped implementer cannot see (e.g. a changed signature breaking another caller). This preserves the spec→plan→implementation independent-verification chain at a fraction of the planning cost.
4. **(Implementing)** Log tasks and sub-items in `TODO.md` first, then implement each task by delegating to a **Grok subagent as the implementer** via the non-interactive CLI (`grok -p "<task instructions>" -m grok-composer-2.5-fast --effort high --yolo --output-format json`), one ephemeral session per task (per the [Grok Build Implementation/Review Handoff](#grok-build-implementationreview-handoff)). Capture the `sessionId` from the JSON result, review and validate the produced changes, run the full validation suite (`ruff check`, `ruff format --check`, `mypy app/`, `pytest`; `npm run lint` + `npm test` from `web/` for frontend changes) before each commit, attach a git note afterwards using the [template](.github/git_notes_template.md), then delete the ephemeral `~/.grok/sessions/.../<sessionId>` directory for that implementation subagent. Commit any files the subagent wrote immediately (per Workflow Rule 9). Cross each sub-item and item off once done. Where the task graph allows — independent tasks with disjoint files and no shared dependency on unlanded work — run multiple implementer subagents in parallel; otherwise implement sequentially. After each delegated task, independently validate with the **full** test suite plus typecheck and lint before committing — never trust the implementer's scoped self-report (it grades only against its narrow task scope and will report green while a cross-cutting change, e.g. a modified signature breaking another caller, stays broken). Also review the diff and normalize implementer output (e.g. trailing newlines) during review. Before moving to Step 5, complete the [Pre-PR](#pre-pr) gates. If Grok fails, fall back to the `subagent-driven-development` skill.
5. **(Submit PR)** Follow the instructions in the [Submit PR](#submit-pr) workflow — using non-interactive `grok -p` commands where possible to trigger reviews — and notify the user once every step has been completed. If Grok fails, spawn native subagents as a fallback.
6. **(Post-PR)** Update documentation files once the PR has been merged and archive completed TODO items from `TODO.md` into `docs/iterations/archive/`; ensure each subitem in the TODO is tagged with the commit hash and each session is tagged with the merge ID — `TODO.md` should only contain **active or future** work. These Post-PR doc/archive commits are pushed **directly to `main`** (no PR — the feature PR is already merged); fast-forward only, never force.
7. **(Reflection)** Conclude the session by doing the [Reflection](#reflection) exercise; the Reflection commit is likewise pushed **directly to `main`** (no PR). After receiving confirmation from the user, delete the worktree and branch.

### Workflow Rules

1. Every TODO sub-item should land as its own commit.
2. Any extension or modification to the task should update the active spec first, then be logged in `TODO.md`.
3. Use specific staging, never `git add -A`.
4. Never force-push, reset `--hard`, merge or amend unless explicitly asked.
5. Keep comments sparse, naming clear, abstractions minimal, and avoid compatibility shims.
6. When lint/typecheck/test fails only on files you did not touch, note it as pre-existing and proceed — do not attempt workarounds that affect other files.
7. After submitting the PR, delegate the code review (and optional security review) to Grok as ephemeral subagent sessions via the non-interactive CLI (`grok -p ... -m grok-composer-2.5-fast --effort high --yolo --output-format json`). Capture the `sessionId` from the JSON result, process the review output/side-effects (e.g. PENDING review posts), then immediately delete the corresponding `~/.grok/sessions/.../<sessionId>` directory. See the detailed examples and cleanup logic in the [Submit PR](#submit-pr) section. Do not rely on GitHub Copilot Code Review (not reliably configured for this repo — see `docs/insights.md`). Rigorously address findings using the `receiving-code-review` reception protocol.
8. After context compaction resumes, run `git status` before any other action — the summary describes intent, not exact commit state.
9. Commit any files written by subagents immediately; do not advance the workflow with a dirty tree. For Grok-based subagents, always capture the `sessionId` via `--output-format json` and delete the ephemeral session directory after the delegation completes and findings are processed.
10. After a delegated implementation task, validate with the **full** suite + typecheck + lint (not the implementer's scoped tests) before committing. A per-task implementer self-scopes its own verification and structurally cannot see cross-task breakage (e.g. a changed signature breaking another caller); only the full project-level run catches it.
11. `gitnexus_impact` requires the exact function/class name, not the module or file name. Use the symbol name as indexed (e.g. `answer_chat`, not `routes_chat`).

### Pre-PR

Before moving from Implementing to Submit PR. **All subagent delegations in this repo — implementation, review, docs, or any other spawned sub-work — use the Grok handoff below, not Claude's native `Agent` tool**, unless Grok is unavailable/blocked (see the fallback note in each step):

- Confirm the implementation still matches the accepted spec.
- Run `/simplify` (skill) — delegate each of its review angles as a separate Grok handoff (parallel where the angles are independent) instead of Claude subagents; apply the fixes yourself as senior dev.
- Invoke `security-review` (skill) if the change touches auth, secrets, network calls, privileged operations, user input, money movement, broker/payment logic, or security-sensitive architecture — via Grok handoff. Always cite the justification for invoking (or skipping) it.
- Run full validation (`ruff check`, `ruff format --check`, `mypy app/`, `pytest`; `npm run lint` + `npm test` from `web/` for frontend changes).
- Ensure `TODO.md` is current.

### Grok Build Implementation/Review Handoff

The canonical contract for delegating any unit of work — implementation tasks (Step 4), Pre-PR gates (`/simplify`, `security-review`), or PR reviews ([Submit PR](#submit-pr)) — to an ephemeral Grok subagent. All flows share this mechanism; only the prompt and the post-processing differ. Grok is the default delegate for every subagent-shaped task in this repo; fall back to Claude's native `Agent` tool only when Grok is unavailable/blocked, and record the fallback reason in `TODO.md`.

**Invoke** (headless, single-turn, no TUI):

```bash
HOME=/root grok -p "<self-contained prompt>" -m grok-composer-2.5-fast --effort <LEVEL> --yolo --output-format json
```

- `-p`: headless single-turn mode; creates an ephemeral chat session.
- `-m`: model name; use `grok-composer-2.5-fast` for implementation and review tasks.
- `--effort`: `high` by default; `xhigh` for complex cross-module tasks or difficult reviews.
- `--yolo`: auto-approves tools so the delegation runs unattended; the senior dev remains responsible for reviewing all changes before commit.
- `--output-format json`: returns structured output including `text` (final summary) and `sessionId` (required for cleanup).

**Prompt** must be self-contained — the subagent starts cold with no session context: point it at the exact spec/plan section, name the precise file scope, and state the boundaries. For implementation, forbid all git operations (the main agent commits), require it to run the **full** `ruff check` + `ruff format --check` + `mypy` + `pytest` (or `npm run lint` + `npm test` from `web/` for frontend work) as its own self-check before reporting — not just the task's own tests, to surface cross-task breakage before the round-trip back — and require a single trailing newline on every file. For review, let the invoked skill post its PENDING GitHub review as a side-effect. The orchestrator's own full-suite gate ([Workflow Rule 10](#workflow-rules)) still runs regardless.

**Capture + process** the JSON `text` and `sessionId`:
- *Implementation:* review the diff, normalize output, then validate per [Workflow Rule 10](#workflow-rules) (full suite + typecheck + lint) and commit with specific staging + a git note.
- *Review:* process findings via the `receiving-code-review` reception protocol (see the [Submit PR](#submit-pr) section).

**Clean up (always)** — delete the ephemeral session directory under `~/.grok/sessions/<encoded-cwd>/<sessionId>/`:

```bash
find "$HOME/.grok/sessions" -type d -name "$sessionId" -prune -exec rm -rf {} +
```

**Parallelism:** where the task graph allows (disjoint files, no shared dependency on unlanded work), run multiple handoffs in parallel — isolated git worktrees where the tasks share risk of git-state collision, or the same worktree when they only touch disjoint files and no git operations are involved; otherwise sequential.

### Submit PR

1. Fill out the **[Template](.github/pull_request_template.md)** and submit the PR (capture the PR number/URL, e.g. via `gh pr create --json number,url`).

2. If the changes affect security (or explicitly stated), delegate a non-interactive security review to a Grok subagent (ephemeral session). Always cite justification. Capture the session ID and clean it up afterwards. Example:
   ```bash
   prNum=$(gh pr view --json number -q .number)
   prompt="Use the /security-review skill on PR #$prNum. Report only HIGH-confidence newly introduced vulnerabilities from the diff."
   json=$(HOME=/root grok -p "$prompt" -m grok-composer-2.5-fast --effort high --yolo --output-format json)
   sessionId=$(echo "$json" | python3 -c "import json,sys;print(json.load(sys.stdin)['sessionId'])")

   # Main agent processes the review text here (incorporate findings, address via receiving-code-review logic)

   find "$HOME/.grok/sessions" -type d -name "$sessionId" -prune -exec rm -rf {} +
   ```

3. Generate the main professional code review by delegating the Grok bundled reviewer per the [Grok Build Implementation/Review Handoff](#grok-build-implementationreview-handoff). Capture the PR number first and use the review prompt:
   ```
   Use /bundled:review --pr #$prNum. The skill should post a PENDING GitHub review. After it completes, provide a very brief summary of what was done.
   ```
   The skill does the heavy lifting (diff collection, reviewer persona, posting the PENDING GitHub review as a side-effect); the handoff is just the delegation + cleanup wrapper. Capture the returned `sessionId`, process the summary, then delete the session per the handoff. Do not rely on GitHub Copilot Code Review.

- Rigorously address the review findings before considering the task complete. Use the reception protocol defined in the `receiving-code-review` skill:
  - Read the full feedback first.
  - Verify each item technically against the actual codebase.
  - Push back (with clear technical reasoning) on items that seem incorrect, unclear, or low-value.
  - Implement one change at a time and test it.
  - Avoid performative agreement ("You're right!", "Great catch!"); just state what was done or ask for clarification.

**Fallback:** if Grok is unavailable, use `/code-review` (the Claude Code plugin) or a native Opus subagent review instead, and note the fallback reason in `TODO.md`.

### Reflection

After every session completion, you reflect on how the workflow pertaining to the workflow and agent harness — the commands you executed (and which failed consistently), the tools you used, skills invoked, MCP accessed, etc. **Do not include anything feature-specific**. For example, when the GitNexus output is too verbose or if certain shell commands keep failing. This is not about the features you implemented, but about *how* you implemented them. Write this down in [Insights](docs/insights.md) and then report it to the user in chat. Wait until user gives explicit permission to conclude the session.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **Nexus** (5173 symbols, 8070 relationships, 113 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely. (If MCP tools aren't registered in the current session, fall back to the CLI: `npx gitnexus <command> --repo .`.)

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` (or `npx gitnexus impact --repo . symbolName`) and report the blast radius (direct callers, affected processes, risk level) to the user.
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

## Core Operating Rules for Agents

The agent must:
- read `AGENTS.md`/`CLAUDE.md` before implementation
- read `docs/index.md` after that
- use technical docs before touching unfamiliar modules
- log work in `TODO.md`
- keep commits small
- validate before committing (lint, typecheck, relevant tests)
- attach git notes
- update docs with behavior changes
- archive completed work
- record useful insights

The agent must not:
- force-push
- hard reset
- amend commits
- merge branches
- use `git add -A`
- run graph rebuilds on dirty mid-edit trees
- silently expand task scope
- rely on AI memory as the source of truth
- skip validation unless explicitly blocked and reported
