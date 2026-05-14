---
description: |
  Automatic remediation workflow for Weekly Codebase Check-Up issues. It reads
  generated code-health reports, resolves concrete findings across the codebase,
  and opens a pull request with verification evidence.

on:
  issues:
    types:
      - opened
      - edited
      - labeled
  workflow_dispatch:
    inputs:
      issue_number:
        description: Code-health issue number to remediate
        required: false
        type: string

permissions:
  contents: read
  issues: read
  pull-requests: read

network:
  allowed:
    - python
    - api.binance.com
    - data-api.binance.vision
    - dataapi.binance.vision
    - stream.binance.com

engine:
  id: copilot
  model: gpt-5.3-codex

tools:
  github:

safe-outputs:
  create-pull-request:
    title-prefix: "[code-health-fix] "
    labels: [code-health, remediation, agent-proposed]
    protected-files: allowed
  noop:
    max: 1
    report-as-issue: false

steps:
  - name: Set up Python
    uses: actions/setup-python@v6
    with:
      python-version: '3.10'
      cache: pip

  - name: Prepare remediation tooling
    shell: bash
    run: |
      set +e
      {
        echo "# Code Health Remediation Tooling"
        echo
        echo "Generated: $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
        echo
        echo "## Setup"
      } > code-health-remediation-tooling.md

      python -m venv .venv >> code-health-remediation-tooling.md 2>&1
      source .venv/bin/activate >> code-health-remediation-tooling.md 2>&1
      python -m pip install --upgrade pip >> code-health-remediation-tooling.md 2>&1
      python -m pip install -r requirements.txt >> code-health-remediation-tooling.md 2>&1
      python -m pip install ruff pytest pytest-cov pip-audit >> code-health-remediation-tooling.md 2>&1

      {
        echo
        echo "## Tool paths"
        echo "python=$(command -v python || true)"
        echo "ruff=$(command -v ruff || true)"
        echo "pytest=$(command -v pytest || true)"
        echo "pip-audit=$(command -v pip-audit || true)"
      } >> code-health-remediation-tooling.md

  - name: Capture remediation issue input
    shell: bash
    run: |
      set -euo pipefail
      python - <<'PY'
      import json
      import os

      event_path = os.environ.get("GITHUB_EVENT_PATH", "")
      event_name = os.environ.get("GITHUB_EVENT_NAME", "")
      issue_number = ""

      if event_path and os.path.exists(event_path):
          with open(event_path, encoding="utf-8") as handle:
              event = json.load(handle)
          issue_number = str(
              event.get("inputs", {}).get("issue_number")
              or event.get("issue", {}).get("number")
              or ""
          )

      with open("code-health-remediation-input.md", "w", encoding="utf-8") as handle:
          handle.write("# Code Health Remediation Input\n\n")
          handle.write(f"- Event name: {event_name}\n")
          handle.write(f"- Issue number: {issue_number}\n")
      PY
---

# Code Health Remediation

You are the code-health remediation agent for Nexus Lite, a private FastAPI application with background workers, PostgreSQL plus pgvector, Redis, local embeddings, and an LLM gateway.

## Goal

Read the triggering Weekly Codebase Check-Up issue, resolve the concrete findings with meaningful code changes, verify them, and open a pull request.

Do not push directly to `main`. Do not perform unrelated cleanup. The maintainer has approved remediation of the findings reported by the code-health issue; do not require additional approval merely because a finding touches trading, scheduler, strategy, backtest, API, dependency, workflow, or documentation code. Use tests and small reviewable changes as the guardrail.

The weekly audit may create multiple bucketed issues in one run. Treat the triggering issue as your complete and exclusive remediation bucket. Do not combine separate code-health issues into one PR, and do not leave the triggering issue's primary findings for another run.

## Trigger Validation

1. Read `code-health-remediation-input.md`. If it contains a non-empty `Issue number`, use that exact issue and do not search for a newer issue.
2. Read the triggering issue from the GitHub event or from the captured issue number.
3. Continue only when all are true:
   - the issue has label `code-health`;
   - the title starts with `[code-health] Weekly Codebase Check-Up`;
   - the body contains `<!-- gh-aw-workflow-id: weekly-codebase-checkup -->`.
4. If the captured issue number is empty and the event does not provide an issue number, find the newest open issue matching those same criteria.
5. If no valid code-health issue is found, call `noop` with a short explanation and stop.

## Required Repository Context

Before editing, read:

- `code-health-remediation-input.md`
- `code-health-remediation-tooling.md`
- `AGENTS.md`
- `TODO.md`
- `requirements.txt`
- `docs/testing.md` if present
- `.github/workflows/weekly-codebase-checkup.md`
- the exact files named in the issue findings before modifying them

If the workspace is sparse-checked out, run:

```bash
git sparse-checkout disable || true
```

## Finding Triage Rules

Classify each actionable issue finding before editing:

- **Must fix:** concrete findings with named files/functions and deterministic evidence, including vulnerable pinned dependencies, ruff/format failures, high complexity in named runtime paths, focused type/test failures, and narrow security/tooling defects.
- **Best-effort fix:** findings that are real but may need a larger sequence of behavior-preserving extractions. For grouped refactor bucket issues, implement the listed refactor plan in one PR with tests instead of producing a dependency-only or single-function PR.
- **Noisy/report-only:** baseline-scale static-analysis debt, low-confidence security findings, test `assert` warnings, unused fixture placeholders, and broad dependency declarations without a specific runtime problem.

Implement **Must fix** findings. For **Best-effort fix** findings, make a targeted code improvement when a named file/function is provided and verification is possible. For **Noisy/report-only** findings, mention that they were intentionally left untouched.

Do not open a PR that only bumps a dependency when the triggering issue's bucket contains concrete code-quality findings in named files. In that case, the PR must include non-dependency code remediation for the named bucket or a clearly evidenced `missing_data`/`missing_tool` result explaining why remediation was impossible.

If the issue contains a `Scope Boundary` section, obey it strictly:

- Change files/functions/packages listed as "In scope".
- Do not change items listed as "Out of scope" unless they are required test fixtures or direct callers needed to keep the scoped change working.
- If the issue contains a `Refactor Plan`, remediate the functions listed there in this PR. Do not punt listed high-complexity functions to separate runs.

## Remediation Policy

- Keep changes as small as possible.
- Prefer behavior-preserving extraction and characterization tests for complex runtime functions.
- Prefer updating pinned versions over broad dependency reshuffles.
- Preserve existing code style and workflow patterns.
- Do not change `AGENTS.md` without updating the matching docs/specs files and TODO entries.
- Do not edit generated lock files except by running the appropriate generator/compile command.
- Never force-push, amend, reset hard, or merge.
- Use a branch named `agent/code-health-remediation-<issue-number>`.
- Use specific staging; never use `git add -A`.

## Dependency Findings

For vulnerable pinned dependencies:

1. Confirm the package and patched version from the issue body.
2. Update the relevant pinned requirement to the patched version or a newer compatible safe version.
3. If a lock/compiled/generated dependency file exists for that dependency, update it using the repository's normal tool.
4. Run the narrow verification first, then broaden if practical:
   - package installation or import check if available;
   - `pip-audit`;
   - affected tests if identifiable;
   - `pytest src/tests` when runtime dependency risk is non-trivial.

If package resolution fails, revert only your attempted dependency edit and call `missing_data` or `missing_tool` with exact failure evidence.

## Complexity Findings

For complexity findings in ingestion, document cleaning, chunking, embeddings, claim extraction, retrieval, synthesis, query answering, worker orchestration, scheduler, or API paths:

- Verify the named files/functions exist.
- Work through the issue's `Refactor Plan` function by function.
- Add or identify characterization tests that exercise the current behavior before editing when practical.
- Extract helpers, split validation/persistence/decision branches, or simplify duplicated conditionals without changing observable behavior.
- Prefer meaningful complexity reductions across the grouped bucket over shallow whitespace or comment churn.
- Do not change evidence linking, retrieval ranking, claim/brief semantics, worker side effects, or database schema unless the finding explicitly identifies that behavior as the bug.
- If no safe characterization path exists, call `missing_data` with exact evidence rather than creating an unrelated or dependency-only PR.

## Verification

Run the most relevant checks for the changes you made. Prefer:

```bash
source .venv/bin/activate
ruff check . --fix
ruff format .
pytest src/tests
pip-audit
```

If JavaScript files change, also run:

```bash
npx eslint --fix app/
```

If a command is unavailable or fails for an unrelated baseline reason, record the exact command and result in the PR body. Do not hide failed verification.

## Pull Request Requirements

If no edits are warranted, call `noop` and stop.

If you make edits:

1. Create or switch to `agent/code-health-remediation-<issue-number>`.
2. Commit only the relevant files with a concise message.
3. Create a pull request using `create_pull_request`.

The PR body must include:

- source issue number and URL;
- findings implemented;
- findings intentionally left untouched and why;
- exact files changed;
- verification commands and outcomes;
- residual risks.

Use this title format, without the safe-output prefix:

```text
Remediate code-health issue #<issue-number>
```
