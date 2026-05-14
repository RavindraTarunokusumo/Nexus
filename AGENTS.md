# AGENTS.md

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

If a code graph, dependency map, or architecture index exists, use it before touching unfamiliar code.

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
