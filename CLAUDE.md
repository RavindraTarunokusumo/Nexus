# CLAUDE.md

Project: `Nexus`

Follow the 7-Step Workflow strictly for feature implementation. Do not start implementation until Steps 1-5 are complete unless the user explicitly authorizes a different flow. Before editing, state which step you are on. Before finishing, confirm Step 6 and Step 7.

## Project Map

- Architecture: [docs/architecture.md](docs/architecture.md)
- Database / Persistence: [docs/database.md](docs/database.md)
- Patterns: [docs/patterns.md](docs/patterns.md)
- Testing: [docs/testing.md](docs/testing.md)
- Commands: [docs/commands.md](docs/commands.md)
- Agent Harness: [docs/agent-harness.md](docs/agent-harness.md)
- Full Index: [docs/index.md](docs/index.md)

## Code Graph / Repo Map

This repo is indexed by **GitNexus** — see the GitNexus section below for all rules and resources.

## 7-Step Workflow

1. **Preamble**
   - Work in a dedicated local branch or worktree.
   - Activate the project environment.
   - Confirm repo status before editing.

2. **Repo Map**
   - Read `gitnexus://repo/Nexus/context` — confirms index freshness and shows clusters/flows.
   - Use `gitnexus_query({query: "concept"})` to find relevant execution flows.
   - Use docs and graph output to understand the relevant area before reading files.

3. **Planning**
   - Read `CLAUDE.md`, `docs/index.md`, and relevant technical docs.
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

*Once everything is done: Do [Post-PR](#post-pr)*

## Workflow Rules

1. Every TODO sub-item should land as its own commit.
2. Any extension or modification to the task must be logged in `TODO.md`.
3. Use specific staging, never `git add -A`.

## Post-PR

- `TODO.md` contains **active or future** work only.
- Archive completed TODO items from `TODO.md` into `docs/iterations/archive/`.
- Each subitem in the TODO must be tagged with the commmit hash and each session must be tagged with the merge ID.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **Nexus** (2234 symbols, 3098 relationships, 52 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

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
