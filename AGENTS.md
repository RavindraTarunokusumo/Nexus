AGENTS.md

Project: `Nexus`

Follow the 7-Step Workflow strictly for feature implementation. Do not start implementation until Steps 1-5 are complete unless the user explicitly authorizes a different flow. Before editing, state which step you are on. Before finishing, confirm Step 6 and Step 7.

Any change made to `CLAUDE.md` should also be applied to `AGENTS.md`.

## Project Map

- Architecture: [docs/architecture.md](docs/architecture.md)
- Database / Persistence: [docs/database.md](docs/database.md)
- Patterns: [docs/patterns.md](docs/patterns.md)
- Testing: [docs/testing.md](docs/testing.md)
- Commands: [docs/commands.md](docs/commands.md)
- CLI: [docs/cli.md](docs/cli.md)
- Agent Harness: [docs/agent-harness.md](docs/agent-harness.md)
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

2. **Repo Map**
   - Run or query the available code graph/index if present.
   - Use docs and graph output to understand the relevant area.

3. **Planning**
   - Read `AGENTS.md`, `docs/index.md`, and relevant technical docs.
   - Use the `brainstorming` skill for implementation planning if available.
   - Produce a concise plan and scope.
   - Do not edit until the plan is accepted unless the user explicitly granted autonomous execution.

4. **Implementation**
   - Log tasks and sub-items in `TODO.md` before editing.
   - Use the `subagent-driven-development` skill where applicable.
   - Keep edits focused.

5. **Commit**
   - Run pre-commit checks before each commit.
   - Each meaningful TODO sub-item should land as its own commit.
   - Use specific staging; never use `git add -A`.
   - Attach a git note using `.github/git_notes_template.md`.
   - Mark completed TODO sub-items with the commit hash.

6. **Pre-PR**
   - Run the `simplify` skill if available.
   - Run the `doc-updater` skill or subagent if available.
   - Invoke `test-plan-writer` if behavior, state, API, tests, or architecture changed.
   - Invoke `security-review` if the change touches auth, secrets, network calls, privileged operations, user input, money movement, broker/payment logic, or security-sensitive architecture.
   - Run full validation.

7. **Submit PR**
   - Use `.github/pull_request_template.md`.
   - Fill out summary, scope, test plan, risk, rollback, docs, backlog, and targeted UI checks.
   - Address automated review with the `receiving-code-review` skill if available.
   - Notify the user when all steps are complete.

## Workflow Rules

1. Every TODO sub-item should land as its own commit.
2. Any extension or modification to the task must be logged in `TODO.md`.
3. Use specific staging, never `git add -A`.
4. Never force-push, reset `--hard`, merge, or amend unless explicitly asked.
5. Keep comments sparse.
6. Prefer clear naming over clever abstractions.
7. Avoid compatibility shims unless explicitly required.
8. Do not leave important conclusions only in chat memory; write them to docs.
9. When `pre-commit run --all-files` fails only on files you did not touch, note it as pre-existing and proceed — do not attempt workarounds that affect other files.
10. After subscribing to PR activity, wait for Copilot Code Review (allow ~20 min) and address all findings before marking the session complete.
11. After context compaction resumes, run `git status` before any other action — the summary describes intent, not exact commit state.
12. Commit any files written by subagents immediately; do not advance the workflow with a dirty tree.
13. `gitnexus_impact` requires the exact function/class name, not the module or file name. Use the symbol name as indexed (e.g. `answer_chat`, not `routes_chat`).

## Pre-Commit Checks

Adapt these commands to the project stack:

```bash
# Python
ruff check . --fix
ruff format .
mypy app/
pytest

# JavaScript / TypeScript, if applicable
cd web && npm run lint && npm test
```

If a tool is missing or unavailable, report it clearly at the end of the session.

## Pre-PR

Before submitting a PR:

- run simplification review
- update docs
- run relevant tests
- run full tests when shared state, architecture, or cross-module behavior changed
- run security review where applicable
- ensure `TODO.md` is current

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
