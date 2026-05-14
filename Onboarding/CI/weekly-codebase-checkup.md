---
description: |
  Weekly integrated agentic codebase check-up. A normal GitHub Actions job
  collects deterministic code-quality, complexity, security, dependency, and
  Graphify evidence as an artifact. The LLM agent then triages that artifact and
  creates a GitHub issue only when actionable follow-up work is warranted.

on:
  schedule:
    - cron: 'weekly on monday'
  workflow_dispatch:

permissions:
  actions: read
  contents: read
  issues: read
  pull-requests: read

env:
  CODE_HEALTH_DIR: /tmp/code-health

network: defaults

engine:
  id: copilot
  model: gpt-5.3-codex

tools:
  github:

safe-outputs:
  create-issue:
    title-prefix: "[code-health] "
    labels: [code-health, technical-debt, agent-proposed]
    max: 4
  noop:
    max: 1
    report-as-issue: false

steps:
  - name: Checkout repository
    uses: actions/checkout@v6
    with:
      persist-credentials: false

  - name: Download code-health evidence
    uses: actions/download-artifact@v6
    with:
      name: code-health-evidence
      path: artifacts/code-health-evidence

  - name: Verify code-health evidence
    shell: bash
    run: |
      test -f artifacts/code-health-evidence/EVIDENCE_INDEX.md
      test -f artifacts/code-health-evidence/tool-availability.txt
      test -f artifacts/code-health-evidence/ruff-check.txt
      test -f artifacts/code-health-evidence/pytest.txt

jobs:
  collect-evidence:
    name: Collect deterministic code-health evidence
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - name: Checkout repository
        uses: actions/checkout@v6

      - name: Set up Python
        uses: actions/setup-python@v6
        with:
          python-version: '3.10'
          cache: pip

      - name: Set up Node
        uses: actions/setup-node@v5
        with:
          node-version: '20'

      - name: Install Python dependencies and audit tools
        shell: bash
        run: |
          set +e
          mkdir -p "$CODE_HEALTH_DIR"
          python -m venv .venv > "$CODE_HEALTH_DIR/setup-venv.txt" 2>&1
          source .venv/bin/activate
          python -m pip install --upgrade pip > "$CODE_HEALTH_DIR/setup-pip-upgrade.txt" 2>&1
          python -m pip install -r requirements.txt > "$CODE_HEALTH_DIR/setup-requirements.txt" 2>&1
          python -m pip install ruff pytest pytest-cov radon xenon lizard vulture deptry bandit pip-audit basedpyright > "$CODE_HEALTH_DIR/setup-checkup-tools.txt" 2>&1
          {
            echo "python=$(command -v python || true)"
            echo "pip=$(command -v pip || true)"
            echo "ruff=$(command -v ruff || true)"
            echo "pytest=$(command -v pytest || true)"
            echo "radon=$(command -v radon || true)"
            echo "xenon=$(command -v xenon || true)"
            echo "lizard=$(command -v lizard || true)"
            echo "vulture=$(command -v vulture || true)"
            echo "deptry=$(command -v deptry || true)"
            echo "bandit=$(command -v bandit || true)"
            echo "pip-audit=$(command -v pip-audit || true)"
            echo "basedpyright=$(command -v basedpyright || true)"
            echo "node=$(command -v node || true)"
            echo "npm=$(command -v npm || true)"
            echo "npx=$(command -v npx || true)"
          } > "$CODE_HEALTH_DIR/tool-availability.txt" 2>&1

      - name: Run code-health checks
        shell: bash
        run: |
          set +e
          source .venv/bin/activate || true
          mkdir -p "$CODE_HEALTH_DIR"

          ruff check . > "$CODE_HEALTH_DIR/ruff-check.txt" 2>&1 || true
          ruff format --check . > "$CODE_HEALTH_DIR/ruff-format.txt" 2>&1 || true
          pytest src/tests > "$CODE_HEALTH_DIR/pytest.txt" 2>&1 || true
          npx eslint app/ > "$CODE_HEALTH_DIR/eslint.txt" 2>&1 || true

          radon cc src -s -a > "$CODE_HEALTH_DIR/radon-cc.txt" 2>&1 || true
          radon mi src -s > "$CODE_HEALTH_DIR/radon-mi.txt" 2>&1 || true
          xenon --max-absolute B --max-modules B --max-average A src > "$CODE_HEALTH_DIR/xenon.txt" 2>&1 || true
          lizard src > "$CODE_HEALTH_DIR/lizard.txt" 2>&1 || true

          vulture src --min-confidence 80 > "$CODE_HEALTH_DIR/vulture.txt" 2>&1 || true
          deptry . > "$CODE_HEALTH_DIR/deptry.txt" 2>&1 || true
          pip-audit > "$CODE_HEALTH_DIR/pip-audit.txt" 2>&1 || true
          bandit -r src > "$CODE_HEALTH_DIR/bandit.txt" 2>&1 || true
          basedpyright src > "$CODE_HEALTH_DIR/basedpyright.txt" 2>&1 || true

          git status --short > "$CODE_HEALTH_DIR/git-status.txt" 2>&1 || true

      - name: Capture Graphify snapshot context
        shell: bash
        run: |
          set +e
          mkdir -p "$CODE_HEALTH_DIR"
          if [ -f graphify-out/GRAPH_REPORT.md ]; then
            cp graphify-out/GRAPH_REPORT.md "$CODE_HEALTH_DIR/graphify-graph-report.md"
          fi
          if [ -d graphify-out ]; then
            find graphify-out -maxdepth 2 -type f | sort > "$CODE_HEALTH_DIR/graphify-files.txt"
          else
            echo "graphify-out directory not present" > "$CODE_HEALTH_DIR/graphify-files.txt"
          fi

      - name: Create compact evidence index
        shell: bash
        run: |
          set +e
          {
            echo "# Code Health Evidence Index"
            echo
            echo "Generated: $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
            echo "Commit: ${GITHUB_SHA}"
            echo
            echo "## Files"
            find "$CODE_HEALTH_DIR" -maxdepth 1 -type f -printf '- %f\n' | sort
            echo
            echo "## Tool Availability"
            cat "$CODE_HEALTH_DIR/tool-availability.txt" 2>/dev/null || true
            echo
            echo "## Setup Tail"
            for f in setup-venv.txt setup-pip-upgrade.txt setup-requirements.txt setup-checkup-tools.txt; do
              echo "### $f"
              tail -80 "$CODE_HEALTH_DIR/$f" 2>/dev/null || true
              echo
            done
          } > "$CODE_HEALTH_DIR/EVIDENCE_INDEX.md"

      - name: Upload code-health evidence
        uses: actions/upload-artifact@v7
        with:
          name: code-health-evidence
          path: /tmp/code-health
          if-no-files-found: warn
          retention-days: 14

---

# Weekly Codebase Check-Up

You are the weekly code-health auditor for Nexus Lite, a private FastAPI application with background workers, PostgreSQL plus pgvector, Redis, local embeddings, an LLM gateway, and an ingestion-to-brief pipeline.

A normal GitHub Actions job named `collect-evidence` runs before you. It collects deterministic scanner outputs into an artifact named `code-health-evidence`. Your job is to download/read that artifact, incorporate Graphify context, triage the evidence, and create scoped GitHub issues only when actionable follow-up work is warranted.

Do not modify repository files. Do not open a PR. Do not perform broad cleanup. This workflow is inspection, triage, and issue creation only.

## Operating principles

- Deterministic tool output is the evidence layer.
- Your agentic role is triage, prioritization, and issue writing.
- Graphify findings must be incorporated into your context before final triage.
- Prefer small, reviewable follow-up tasks over broad cleanup proposals.
- Treat ingestion, document cleaning, chunking, embeddings, claim extraction, retrieval, synthesis, query answering, worker orchestration, scheduler, database, secrets, and deployment code as higher risk.
- Do not recommend behavior-changing refactors casually.
- Do not create an issue when the run is clean or only contains low-confidence/noisy findings.
- Do create an issue when the workflow cannot run its core audit tools and therefore cannot verify code health.
- If you create issues, group them into a small number of remediation buckets so future remediation agents do not spend duplicate context-loading and startup cost.

## Required context to read first

Read these repository files before interpreting the audit:

- `README.md`
- `TODO.md`
- `AGENTS.md`
- `requirements.txt`
- `.github/workflows/doc-freshness-audit.md`
- `.github/workflows/daily-repo-status.md`
- `docs/architecture.md` if present
- `docs/testing.md` if present

Use GitHub tools if filesystem reading is unavailable.

## Evidence artifact to inspect

Download or inspect the `code-health-evidence` artifact from the current workflow run. It should contain:

- `EVIDENCE_INDEX.md`
- `tool-availability.txt`
- `setup-venv.txt`
- `setup-pip-upgrade.txt`
- `setup-requirements.txt`
- `setup-checkup-tools.txt`
- `ruff-check.txt`
- `ruff-format.txt`
- `pytest.txt`
- `eslint.txt`
- `radon-cc.txt`
- `radon-mi.txt`
- `xenon.txt`
- `lizard.txt`
- `vulture.txt`
- `deptry.txt`
- `pip-audit.txt`
- `bandit.txt`
- `basedpyright.txt`
- `git-status.txt`
- `graphify-graph-report.md` if available
- `graphify-files.txt`

Do not attempt to reinstall the scanner tools inside the agent runtime unless the artifact is missing. The scanner tools are intentionally run in the `collect-evidence` job to avoid agent-runtime proxy/package-install limitations.

## Core audit blocked rule

Before deciding whether to create an issue, determine whether the artifact contains enough deterministic evidence to be meaningful.

The audit is considered **blocked** if most core checks could not run because tools were unavailable, dependency installation failed, network/proxy restrictions blocked package installation, or the workflow environment prevented scanner execution.

Core checks are:

- `ruff check`
- `ruff format --check`
- `pytest src/tests`
- at least one complexity scanner: `radon`, `xenon`, or `lizard`
- at least one security/dependency scanner: `bandit`, `pip-audit`, or `deptry`

If the audit is blocked, create a GitHub issue even if no repository code defect was proven. Classify it as workflow/tooling debt, not application-code debt. Do not use `noop` for a blocked audit.

For blocked audits, use this issue title:

```text
Weekly Codebase Check-Up Blocked — YYYY-MM-DD
```

The issue should include:

```markdown
## Summary
- Overall status: Blocked
- Reason: core audit tools could not run
- Likely cause: network/proxy restriction / package install failure / missing Node/npm project setup / unknown
- Code defect evidence produced: Yes / No
- Graphify context: Available / Partially available / Unavailable

## Failed Setup / Tooling Evidence
Summarize setup logs, tool availability, and command failures.

## What Still Worked
Mention any checks or Graphify/source context that did work.

## Recommended Fix
- [ ] Decide whether this workflow should use dependency caching, a prebuilt tool image, or repo-pinned tool dependencies.
- [ ] Re-run the workflow after toolchain availability is fixed.

## Guardrail
No application code defect should be inferred from this blocked run alone.
```

## Graphify context requirement

Graphify findings must be part of final triage.

Prefer `graphify-graph-report.md` from the evidence artifact. If unavailable, inspect `graphify-files.txt` and then relevant repository files. Do not rebuild or update the graph in this workflow.

Use Graphify to weight findings. A complex function in a highly central execution module is more important than a complex helper in a low-risk script.

## Triage rules

Create an issue when at least one of these is true:

- The audit is blocked under the **Core audit blocked rule**.
- Tests fail for reasons that look like real repo failures.
- Ruff finds real lint/format issues.
- Bandit reports medium/high findings or findings involving live trading, secrets, auth, requests, config, or exchange integration.
- `pip-audit` reports vulnerable dependencies.
- Complexity tools flag clear hotspots in central or high-risk modules.
- Graphify suggests architecture coupling or boundary drift that matches tool findings.
- Vulture/Deptry findings are high-confidence and likely actionable.
- The workflow cannot run key checks because of a repository setup issue that should be fixed.

Do not create an issue for:

- low-confidence Vulture noise,
- missing optional tools such as Graphify or `npx` when core audit evidence still exists,
- style preferences,
- broad architectural opinions without concrete paths or tool evidence,
- a clean run with no meaningful follow-up.

Important: a blocked audit is not a clean run. If core tools cannot run, create a blocked-audit issue.

## Risk buckets

Classify each actionable finding:

### A — Safe cleanup candidate

Examples:

- Ruff-only issues
- formatting drift
- obvious unused imports
- simple dead local variables

Recommended next step: small cleanup PR may be acceptable.

### B — Refactor candidate

Examples:

- complex functions
- oversized modules
- duplication
- maintainability warnings

Recommended next step: create one grouped refactor issue covering the related high-complexity hotspots. Do not create one issue per function.

### C — High-risk scoped remediation

Examples:

- live trading execution
- Binance integration
- order sizing
- stop loss / take profit behavior
- strategy signal logic
- backtest correctness
- database schema changes
- deployment or secrets handling

Recommended next step: include the high-risk function in the grouped refactor issue with explicit behavior-preservation notes, characterization-test requirements, and acceptance checks.

### D — Report only

Examples:

- low-confidence Vulture output
- optional dependency cleanup
- ambiguous architecture concerns
- optional tool failures when core audit evidence still exists

Recommended next step: mention only if useful; otherwise noop.

### E — Workflow/tooling debt

Examples:

- dependency installation fails before core tools are available
- core scanners cannot run because the GitHub Actions environment lacks required runtime support
- tool PATH/global npm location failures prevent the audit from producing evidence
- the evidence artifact is missing or incomplete

Recommended next step: create a blocked-audit issue. Do not infer application-code defects from this alone.

## Issue creation policy

Create at most four GitHub issues per run.

If the audit is blocked, use the blocked-audit title and format from the **Core audit blocked rule**.

If application-code action is needed, create one issue per remediation bucket, not one issue per finding.

Use this bucket split:

- One dependency/security bucket for vulnerable packages and declaration drift.
- One grouped refactor bucket for all high-complexity code hotspots that are suitable for behavior-preserving refactor PRs.
- One test/lint bucket for failing tests, ruff/format issues, or focused JavaScript lint cleanup.
- One workflow/tooling bucket for blocked audit infrastructure or environment failures.

When there are too many actionable findings for a bucket, include the highest-risk findings first. Prioritize ingestion, retrieval, synthesis, query answering, worker orchestration, scheduler, database, secrets, and deployment paths. Mention omitted lower-priority findings in the bucket issue's "Deferred Findings" section.

Do not split high-complexity refactors into separate issues solely because they involve different functions. The goal is one grouped refactor issue and one grouped refactor PR to reduce token cost and Copilot rate-limit pressure. Keep dependency/security and workflow/tooling buckets separate from the refactor bucket.

Use this title format for each application-code issue:

```text
Weekly Codebase Check-Up — YYYY-MM-DD — <bucket name>
```

The safe-output configuration adds the `[code-health]` prefix. Do not include it yourself.

Use this body format for application-code findings. Each issue body must be self-contained and must include only the findings in that bucket.

```markdown
## Summary
- Overall status: Pass / Needs attention / Blocked
- Issue severity: Low / Medium / High
- Recommended next step: Small cleanup PR / Grouped refactor PR / Dependency patch PR / Workflow fix PR
- Remediation bucket: Dependency/security / Refactor hotspots / Test-lint cleanup / Workflow-tooling
- Remediation scope: one sentence naming the package cluster, commands, files/functions, or workflow to fix
- Graphify context: Available / Partially available / Unavailable

## Tool Evidence
| Check | Status | Notes |
| --- | --- | --- |
| ruff check | ... | ... |
| ruff format | ... | ... |
| pytest | ... | ... |
| eslint | ... | ... |
| radon/xenon/lizard | ... | ... |
| vulture | ... | ... |
| deptry | ... | ... |
| pip-audit | ... | ... |
| bandit | ... | ... |
| basedpyright | ... | ... |

## Graphify Findings
Summarize only the Graphify context relevant to this issue's scope.

## Actionable Findings

### Finding N: short title
- Bucket: A / B / C / D / E
- Evidence: command + relevant excerpt
- Files involved: paths
- Functions involved: exact function names, when applicable
- Why it matters: concise explanation
- Required remediation: concrete action the remediation workflow should implement
- Acceptance checks: exact tests or commands the remediation workflow should run
- Risk notes: especially if trading execution, strategy behavior, backtesting, secrets, or deployment are involved

## Refactor Plan
- Required for refactor bucket issues only.
- List every high-complexity function included in this grouped issue.
- For each function, name the intended behavior-preserving extraction target and the targeted characterization tests.
- State that the remediation workflow should open one PR for the grouped refactor bucket.

## Scope Boundary
- In scope: exact files/functions/packages this bucket is allowed to change.
- Out of scope: unrelated buckets intentionally split into separate issues.

## Deferred Findings
- Optional. Use only when lower-priority findings were omitted from the current bucket.

## Non-Actionable Noise Ignored
Mention noisy categories you intentionally ignored and why.
```

## Noop policy

Use `noop` only when no issue is necessary and the audit produced enough deterministic evidence to be meaningful.

Do not use `noop` when core audit tools could not run.

Noop format:

```markdown
Weekly codebase check-up completed. No GitHub issue created because no actionable maintenance item crossed the threshold.

Summary:
- Tests: ...
- Lint/format: ...
- Security/dependencies: ...
- Complexity: ...
- Graphify context: ...
- Notes: ...
```

## Hard constraints

- Do not edit files.
- Do not create PRs.
- Do not create more than four issues.
- Do not recommend broad codebase cleanup.
- Do group high-complexity refactor findings into one refactor issue when they can be handled with behavior-preserving extractions in one PR.
- Do not suggest changing trading behavior casually.
- Do not hide failed checks. If a tool fails, say why and whether that failure itself is actionable.
- Treat live trading, exchange integration, order execution, TP/SL, strategy signals, backtesting correctness, secrets, and deployment as high-risk areas.
- Prefer small, reviewable follow-up tasks over large refactor plans.
