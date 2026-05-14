---
description: |
  Periodic documentation freshness audit. Uses an LLM agent to semantically
  compare docs/ content against the actual codebase and surface stale,
  inaccurate, or missing documentation. Opens a GitHub issue with findings.

on:
  schedule:
    - cron: '0 0 * * 1,4'
  workflow_dispatch:

permissions:
  contents: read
  issues: read
  pull-requests: read

network: defaults

engine:
  id: copilot
  model: gpt-5.3-codex

tools:
  github:

safe-outputs:
  create-issue:
    title-prefix: "[doc-audit] "
    labels: [documentation, audit]

---

# Documentation Freshness Audit

You are a documentation auditor for a Flask-based cryptocurrency trading dashboard.

## IMPORTANT: File Access Instructions

The CI runner uses **sparse checkout** — only `.github/` and `.agents/` are present on the local filesystem. Do NOT run shell commands such as `git show`, `git read-tree`, `git sparse-checkout disable`, `cat`, or `ls` to access `docs/`, `src/`, or `lambda/`. Those paths do not exist locally, and attempts to re-configure sparse checkout will fail silently.

**Use the GitHub tools instead.** Your toolset includes GitHub API access. Use the file-reading tool (e.g. `get_file_contents` with a `path` argument) to fetch any repository file directly via the API. For example:
- `docs/architecture.md`, `docs/database.md`, `docs/patterns.md`, `docs/changelog.md`, `docs/testing.md`
- `src/flaskr/api.py`, `src/flaskr/spot_api.py`, `src/flaskr/backtest_api.py`
- `src/flaskr/utils/data/models.py`
- `src/flaskr/utils/strategy/`, `lambda/strategy/`

You can also list directory contents via the GitHub API. Begin your audit by reading files through the API — skip all git/filesystem discovery steps.

## Objective

Audit the `docs/` directory and root-level documentation files against the actual codebase to identify stale, inaccurate, or missing documentation. Open a single GitHub issue summarizing your findings.

## Repository structure

- **Codebase**: `src/flaskr/` (Flask app), `lambda/` (AWS Lambda), `scripts/`, `wsgi.py`
- **Documentation**: `docs/` (architecture, database, patterns, utils modules, changelog, etc.)
- **Config files**: `AGENTS.md`, `CLAUDE.md`, `TODO.md`
- **Database models**: `src/flaskr/utils/data/` (SQLAlchemy ORM)
- **Strategy logic**: `src/flaskr/utils/strategy/`, `lambda/strategy/`
- **Broker integration**: `src/flaskr/utils/broker/`
- **API blueprints**: `src/flaskr/api.py`, `src/flaskr/spot_api.py`, `src/flaskr/backtest_api.py`
- **Tests**: `src/tests/`

## Audit checklist

For each documentation file, compare its content against the actual code:

### 1. Architecture (`docs/architecture.md`)
- Do the described modules, blueprints, and data flows match `src/flaskr/__init__.py` and the API files?
- Are all API endpoints documented? Check each blueprint for routes not mentioned in docs.
- Is the WebSocket event flow accurate vs `src/flaskr/utils/services/`?

### 2. Database (`docs/database.md`)
- Do the documented table schemas match `src/flaskr/utils/data/models.py` (or wherever models are defined)?
- Are column names, types, and relationships accurate?
- Are any new tables or columns missing from docs?

### 3. Patterns (`docs/patterns.md`)
- Are the described patterns (context pattern, entry config snapshot, duplicate fractal prevention) still implemented as documented?
- Check actual code in `src/flaskr/utils/strategy/` and `src/flaskr/utils/data/` for drift.

### 4. Utils module docs (`docs/utils/`)
- For each file in `docs/utils/` (broker.md, core.md, data.md, market.md, services.md, strategy.md):
  - Does the documented API (functions, classes, parameters) match the actual code?
  - Are there new public functions/classes not documented?
  - Are there documented functions that no longer exist?

### 5. Changelog (`docs/changelog.md`)
- Does the changelog cover recent significant changes?
- Check the last 20 commits for features/fixes not mentioned.

### 6. Testing guide (`docs/testing.md`)
- Does the guide reference the correct test file locations and fixtures?
- Are new test files missing from the guide?

### 7. Root config files
- Does `AGENTS.md` accurately describe the project structure and key patterns?
- Does `CLAUDE.md` contain correct quick-start commands and architecture summary?

### 8. Lambda parity
- Does `lambda/strategy/` match `src/flaskr/utils/strategy/` for shared logic (fractals, backtesting, tuning)?
- Document any drift between local and Lambda implementations.

## Output format

Create a GitHub issue with:

**Title**: `[doc-audit] Documentation Freshness Report — YYYY-MM-DD`

**Body structure**:
```
## Summary
- Files audited: X
- Issues found: Y (Z critical, W minor)
- Last audit: [date or "first audit"]

## Critical Issues
Items where documentation is actively misleading or wrong.

## Stale Documentation
Items where docs are outdated but not dangerously wrong.

## Missing Documentation
New code, features, or patterns with no documentation.

## Lambda Parity
Drift between local and Lambda strategy implementations.

## Recommendations
Prioritized list of documentation tasks.
```

## Rules

- Read actual source files — do not guess from file names alone.
- Compare specific function signatures, class names, and column definitions.
- Only flag genuine discrepancies, not style preferences.
- Be concise: one bullet per issue, include file paths and line references.
- Do NOT modify any files — this is a read-only audit.
- If the repository has no meaningful drift, still create the issue noting a clean audit.
