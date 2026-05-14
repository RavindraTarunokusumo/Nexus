# Agent Harness Bootstrap for a Blank Project

Use this onboarding file to create a ready-to-go repository with a dedicated agent harness, layered docs, strict workflow, TODO-driven implementation, validation gates, PR discipline, and session memory.

This file intentionally does **not** define skill/agent contents. It will be supplied in the `/Onboarding` folder.

**Note: This file assumes a Python-based backend. Adjust depending on the choice of backend in PLAN.md**

---

## 1. Goal

Set up a repository where agents can work safely, predictably, and with reviewable history.

The harness separates:

- repo rules
- technical documentation
- task-specific skills
- active work tracking
- validation gates
- PR and post-PR workflows
- session memory and lessons learned

AI may plan, summarize, implement, and review, but correctness gates must remain explicit, deterministic, testable, and auditable.

---

## 2. Target Repository Structure

Create this structure first:

```text
repo/
  AGENTS.md
  TODO.md

  docs/
    index.md
    architecture.md
    database.md
    patterns.md
    testing.md
    commands.md
    changelog.md
    insights.md
    iterations/
      active/
      archive/
    utils/

  .codex/
    skills/
    agents/

  .github/
    pull_request_template.md
    git_notes_template.md
```

Rules:

- `.codex/skills/` is the canonical skill root.
- Copy the skills and agent files from `/Onboarding` into the folders.

---

## 3. Documentation Layers

### Layer A — Repo Contract

Files:

- `AGENTS.md`

Purpose:

- hard rules for all agents
- branch/worktree expectations
- required workflow
- validation gates
- PR rules
- links to deeper docs

Rules:

- `AGENTS.md` is the primary policy source.
- Any change to one must be applied to the other.

### Layer B — Technical Context

Files:

- `docs/index.md`
- `docs/architecture.md`
- `docs/database.md`
- `docs/patterns.md`
- `docs/testing.md`
- `docs/commands.md`
- `docs/utils/*.md`

Purpose:

- explain system behavior
- document module boundaries
- preserve invariants
- record commands and debugging workflows
- reduce repeated codebase rediscovery

### Layer C — Task Skills/Agents

Directories:

- `.codex/skills/<skill-name>/`
- `.codex/agents/<agent-name>.toml`

Purpose:

- keep task-specific execution instructions separate from repo policy
- avoid bloating `AGENTS.md`
- allow portable agent workflows across runtimes

Do not write the skill/agent files during bootstrap unless the user supplies the contents.

### Layer D — Work Tracking and Memory

Files:

- `TODO.md`
- `docs/iterations/active/*.md`
- `docs/iterations/archive/*.md`
- `docs/changelog.md`
- `docs/insights.md`

Rules:

- `TODO.md` contains active or future work only.
- Completed work moves to `docs/iterations/archive/`.
- Behavior or architecture changes update `docs/changelog.md`.
- Useful workflow lessons go into `docs/insights.md`.

---

## 4. `AGENTS.md`

```markdown
# AGENTS.md

Project: `<project-name>`

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
4. Never force-push, reset `--hard`, merge, or amend unless explicitly asked.
5. Keep comments sparse.
6. Prefer clear naming over clever abstractions.
7. Avoid compatibility shims unless explicitly required.
8. Do not leave important conclusions only in chat memory; write them to docs.

## Pre-Commit Checks

Adapt these commands to the project stack:

```bash
# Python
ruff check . --fix
ruff format .
pytest

# JavaScript / TypeScript, if applicable
npm run lint
npm test
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

## Post-PR

- `TODO.md` contains active or future work only.
- Archive completed TODO sessions into `docs/iterations/archive/`.
- Tag completed sub-items with commit hashes.
- Add session lessons to `docs/insights.md`.

## Reflection

After every completed session, record useful lessons in `docs/insights.md`:

- tools used
- scripts created
- workflow improvements
- recurring failure modes
- skills worth adding or improving
```

---

## 5. `docs/index.md`

**Note: Add more folders as needed for the specific project plan in PLAN.md**

```markdown
# Documentation Index

Use this file as the second layer after `AGENTS.md`. It points to deeper docs without repeating them.

## Core Docs

- [agent-harness.md](agent-harness.md): agent-facing documentation structure and harness rules
- [architecture.md](architecture.md): system design, module boundaries, entry points, request/data flow
- [database.md](database.md): schema, persistence model, migration rules
- [patterns.md](patterns.md): durable coding and state-management rules
- [testing.md](testing.md): test execution, fixtures, validation workflow
- [commands.md](commands.md): common local commands
- [changelog.md](changelog.md): notable behavior and architecture changes
- [insights.md](insights.md): session lessons and reusable workflow observations

## Module Docs

Add module-specific docs here as the codebase grows:

- [utils/](utils/)

## Repo Areas

Document key repo areas here:

- `src/`: application source
- `tests/`: test suite
- `scripts/`: local automation scripts
- `TODO.md`: active work only
- `docs/iterations/archive/`: completed TODO archive

## Fast Path By Task

- Changing app behavior: read `architecture.md`, then relevant module docs
- Changing persistence: read `database.md` and `patterns.md`
- Changing tests: read `testing.md`
- Preparing for review: read `AGENTS.md`, `testing.md`, and PR template
- Adding agent workflow: read `agent-harness.md`

## Core Invariants

List project-specific invariants here.

Examples:

- State must be keyed by stable IDs, not display names.
- External services must be mocked in tests.
- Runtime secrets must not be logged.
- User-facing behavior changes require docs and tests.
```

---

## 6. `docs/agent-harness.md`

```markdown
# Agent Documentation Harness

This repository uses a layered documentation and skill harness for safe agentic development.

## Purpose

Give every agent one clear path to:

- understand repo rules
- understand architecture
- pick the right skill
- execute safely
- validate changes
- keep docs synchronized
- preserve session memory

## Layered Documentation Model

### Layer A — Repo Contract

Files:

- `AGENTS.md`

Responsibilities:

- allowed and forbidden actions
- branch/worktree workflow
- commit/test/lint expectations
- PR expectations
- links to deeper docs

### Layer B — Domain and System Context

Files:

- `docs/architecture.md`
- `docs/database.md`
- `docs/patterns.md`
- `docs/testing.md`
- `docs/commands.md`
- `docs/utils/*.md`

Responsibilities:

- technical truth
- data model
- invariants
- commands
- debugging workflows

### Layer C — Task Skills

Canonical root:

- `.codex/skills/<skill-name>/`

Skill package structure:

- `SKILL.md` required only when supplied by the user
- `references/` optional
- `scripts/` optional
- `assets/` optional
- `agents/` optional

Responsibilities:

- task-specific execution steps
- input conventions
- output expectations
- validation rules
- safety boundaries

### Layer D — Work Tracking and Change History

Files:

- `TODO.md`
- `docs/iterations/active/*.md`
- `docs/iterations/archive/*.md`
- `docs/changelog.md`
- `docs/insights.md`

Responsibilities:

- active work
- completed work
- why changes happened
- session lessons

## Recommended Navigation Order

1. Read `AGENTS.md`.
2. Read `docs/index.md`.
3. Read relevant technical docs.
4. Select the matching skill if available.
5. Implement through `TODO.md`.
6. Validate.
7. Update docs.
8. Prepare PR.
9. Archive completed work.

## Ownership and Source of Truth

- Policy source of truth: `AGENTS.md`
- Work source of truth: `TODO.md`
- Technical source of truth: `docs/`
- Skill source of truth: `.codex/skills/`

If duplicates exist, update canonical content first, then mirror.

## Update Rules

- If source behavior changes, update relevant docs in the same iteration.
- If workflow changes, update `AGENTS.md`.
- If repeated tasks emerge, create or revise a skill.
- Keep skills focused and composable.
```

---

## 7. `docs/architecture.md`

```markdown
# System Architecture

## Entry Points

Document the main runtime entry points.

Example:

- `main.py` or `wsgi.py`: application entry point
- `src/app/__init__.py`: app factory or initialization
- `src/api/`: API routes
- `src/services/`: application services
- `src/models/`: persistence models

## Module Structure

Document each major module.

### `core/`

Infrastructure utilities.

### `data/`

Persistence and state management.

### `services/`

Application services and business workflows.

### `api/`

HTTP or external API surfaces.

### `ui/`

Frontend or templates, if applicable.

### `integrations/`

External systems, credentials, APIs, brokers, queues, cloud services.

## Data Flow

Describe the main runtime flow:

1. startup
2. request/event intake
3. state read/write
4. business logic
5. external side effects
6. response/event emission
7. logging and audit

## Background Jobs

Document schedulers, workers, queues, or cron tasks.

## External Integrations

Document every external dependency:

- API used
- auth method
- env vars
- failure behavior
- test mocking strategy

## Invariants

List architecture invariants that must not be violated.
```

---

## 8. `docs/database.md`

```markdown
# Database and Persistence

## Purpose

Document schema, state ownership, migrations, and persistence rules.

## Storage Backend

Describe the database or storage layer.

## Core Tables / Collections

For each table or collection:

### `<name>`

Purpose:

Fields:

- `id`
- `created_at`
- `updated_at`

Relationships:

Notes:

## Migration Rules

- Migrations must be deterministic.
- Backward compatibility must be explicit.
- Data deletion must be intentional and documented.
- Tests must cover migration-sensitive behavior.

## State Ownership

Document which module owns each state transition.

## Persistence Invariants

Examples:

- Stable IDs are authoritative.
- Display names are not state keys.
- Writes must be atomic where consistency matters.
- External side effects must be auditable.
```

---

## 9. `docs/patterns.md`

```markdown
# Key Patterns

## Identifier Pattern

Document the difference between internal IDs, display names, symbols, slugs, or external IDs.

Rules:

- Use stable IDs for internal state.
- Use display names only for UI.
- Store external IDs separately.

## State Pattern

Document how runtime state is shaped, stored, cached, and invalidated.

## Snapshot Pattern

If mutable configuration affects long-running operations, snapshot the config at operation start.

Purpose:

- preserve reproducibility
- avoid mid-operation config drift
- improve auditability

## Persistence Pattern

Document transaction/session rules.

Examples:

- use context-managed sessions
- rollback on failure
- keep writes atomic
- avoid direct writes outside persistence helpers

## External Side-Effect Pattern

External operations should be isolated behind service or broker layers.

Rules:

- no raw external calls from random modules
- queue or wrap dangerous side effects
- log outcomes
- test with mocks

## Code Style

- Comments should be sparse and useful.
- Prefer clear names.
- Avoid clever abstractions.
- Delete dead code.
- Do not add compatibility shims unless required.
- Keep helpers only when they reduce real duplication or complexity.

## Anti-Patterns

- hidden global state
- broad exception swallowing
- untested external calls
- unexplained background jobs
- docs that duplicate code instead of explaining behavior
```

---

## 10. `docs/testing.md`

```markdown
# Testing Guide

## Purpose

Testing includes both execution and planning. Run automated tests and use `test-plan-writer` when meaningful changes need explicit coverage mapping.

## Prerequisites

- activate the project environment
- run commands from repo root
- mock external services
- avoid real credentials in tests

## Test Layout

Document test groups:

- API tests:
- service tests:
- persistence tests:
- integration tests:
- frontend tests:
- fixtures:

## Core Fixtures

Document shared fixtures and helpers.

## Running Tests

Run all tests:

```bash
pytest
```

Run one file:

```bash
pytest tests/test_example.py
```

Run one test:

```bash
pytest tests/test_example.py::test_name -v
```

Run by keyword:

```bash
pytest -k "keyword"
```

Stop on first failure:

```bash
pytest -x
```

## Validation Workflow

Default sequence before commit:

```bash
ruff check . --fix
ruff format .
pytest
```

Add stack-specific validation commands as needed.

## When To Invoke `test-plan-writer`

Invoke after implementation and before PR-ready when:

- behavior changed
- API changed
- state transitions changed
- persistence changed
- external integrations changed
- acceptance criteria need coverage mapping

Do not invoke for trivial copy, docs-only, or tiny localized edits.

## Test-Plan Output Contract

The test plan should include:

- `VERDICT`
- `MERGE_BLOCKING`
- `FILES`
- `ACCEPTANCE_CRITERIA`
- `REQUIRED_ACTIONS`
- coverage mapping
- explicit test cases
- edge cases
- negative tests
- fixture/setup needs
- out-of-scope items
- open questions

## Coverage Expectations

Meaningful changes should cover:

- happy path
- failure path
- boundary conditions
- state before and after
- persistence effects
- external service mocks
- regression case, if bug fix

## Test Writing Rules

- keep tests deterministic
- isolate state
- mock network and external services
- name tests by behavior
- assert durable outcomes, not implementation trivia
```

---

## 11. `docs/commands.md`

```markdown
# Commands Reference

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

For Windows PowerShell:

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
```

## Development Server

```bash
python main.py
```

Replace with the actual project command.

## Testing

```bash
pytest
```

## Lint and Format

```bash
ruff check . --fix
ruff format .
```

## Frontend, If Applicable

```bash
npm install
npm run lint
npm test
```

## Database

Initialize:

```bash
python scripts/init_db.py
```

Seed local data:

```bash
python scripts/seed_mock_db.py
```

Reset local data:

```bash
python scripts/reset_db.py
```

## Logs

```bash
tail -f logs/*.log
```

## Environment Variables

List required variables:

```bash
APP_ENV=development
DATABASE_URL=
API_KEY=
```

Never commit real secrets.

## Git Notes

Add a structured note for the latest commit:

```bash
git log -1 --format="%H"
git notes add -m "Task: <task name>
Summary: <brief what changed and why>
Docs: <docs paths updated, comma-separated, or N/A>
TODO: <TODO.md section/item reference>
Validation: <checks run>" <commit_hash>
```
```

---

## 12. `TODO.md`

```markdown
# TODO.md

This file contains active or future work only.

Completed sessions must be moved to `docs/iterations/archive/`.

## Backlog

## Session: <Session Name> (<YYYY-MM-DD>)

- [ ] <sub-item 1>
- [ ] <sub-item 2>
- [ ] <sub-item 3>

## Future Backlog

- [ ] <future item>
```

Rules:

- Every implementation task starts here.
- Each meaningful sub-item should become one commit.
- Mark completed sub-items with commit hash.
- Move completed sessions to archive after PR/merge.

---

## 13. `docs/changelog.md`

```markdown
# Changelog

Record notable behavior, architecture, API, persistence, or workflow changes.

## <YYYY-MM-DD> — <Change Title>

Summary:

- What changed:
- Why:
- User-visible impact:
- Migration notes:
- Related PR/commit:
```

---

## 14. `docs/insights.md`

```markdown
# Insights

Record reusable lessons from completed sessions.

## <YYYY-MM-DD> — <Session Name>

- What worked:
- What failed:
- Useful commands:
- Scripts created:
- Workflow improvement:
- Skill worth adding or updating:
```

---

## 15. `.github/git_notes_template.md`

```markdown
Task: <short task title>
Summary: <brief change summary and reason>
Docs: <comma-separated docs paths, or N/A>
TODO: <TODO.md section/item reference>
Validation: <checks run, e.g., ruff, eslint, pytest, manual>
```

---

## 16. `.github/pull_request_template.md`

```markdown
## Summary

- What changed and why?
- Keep this focused on behavior and outcomes.

## Root Cause (for fixes)

- What was broken?
- Why did it happen?
- If not a bug fix, write `N/A`.

## Scope of Changes

| Area | Description |
|------|-------------|
| Backend | |
| Frontend | |
| Data/DB | |
| Services / Integrations | |
| Docs | |
| Tests | |

## Test Plan

- [ ] Lint / format completed
- [ ] Unit tests completed
- [ ] Integration tests completed, if required
- [ ] Manual validation completed, if required

Manual validation notes:

## Risk and Rollback

- Risk level: `low` / `medium` / `high`
- Main risk areas:
- Rollback plan:

## Docs and Backlog

- [ ] Updated docs for behavior/API/architecture changes
- [ ] Updated `docs/changelog.md` when behavior or architecture changed
- [ ] Updated `TODO.md` / moved completed items to `docs/iterations/archive/`
- [ ] Added git notes per commit using `.github/git_notes_template.md`

## Related

- Issue(s):
- TODO/Iteration item:
- PR type: `feat` / `fix` / `chore` / `docs` / `refactor` / `test`

## Targeted UI Checks

List paths or test tags the automated agent should verify after merge.

- [ ] /
```

---

## 17. Core Operating Rules for Agents

The agent must:

- read `AGENTS.md` before implementation
- read `docs/index.md` after `AGENTS.md`
- use technical docs before touching unfamiliar modules
- log work in `TODO.md`
- keep commits small
- validate before committing
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

---

## 18. Ready-to-Go Bootstrap Checklist

Follow this sequence in a blank repo:

1. Create `AGENTS.md`.
2. Create `TODO.md`.
3. Create `docs/index.md`.
4. Create `docs/agent-harness.md`.
5. Create `docs/architecture.md`.
6. Create `docs/database.md`.
7. Create `docs/patterns.md`.
8. Create `docs/testing.md`.
9. Create `docs/commands.md`.
10. Create `docs/changelog.md`.
11. Create `docs/insights.md`.
12. Create `docs/iterations/active/`.
13. Create `docs/iterations/archive/`.
14. Create `.github/pull_request_template.md`.
15. Create `.github/git_notes_template.md`.
16. Create `.codex/skills/`.
17. Create the skill directories only.
18. Do not write skill files until the user supplies them.
19. Adapt commands to the actual stack.
20. Add project-specific invariants to `docs/index.md` and `docs/patterns.md`.
21. Add architecture details once the first source structure exists.
22. Run a dry-run workflow:
    - add a small TODO item
    - make a tiny change
    - validate
    - commit
    - attach git note
    - draft PR
    - archive TODO
    - write an insight

After this checklist, the repo is ready for agentic development.
