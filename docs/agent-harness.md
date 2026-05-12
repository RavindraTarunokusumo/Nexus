# Agent Harness

This repository uses a layered onboarding harness:

- `AGENTS.md` is the repo contract and workflow gate.
- `docs/` captures technical context, commands, and historical notes.
- `.codex/skills/` stores task-specific workflow instructions.
- `.codex/agents/` stores reusable agent configs.
- `TODO.md` tracks active and future work.

GitNexus is wired into the local Codex workflow through `.codex/config.toml`.
Use it as the first repo map when you need architectural context:

- `gitnexus status` to check whether the repository is indexed
- `gitnexus analyze` to build or refresh the local graph
- `gitnexus query`, `gitnexus context`, and `gitnexus impact` to explore relationships before editing
- `gitnexus detect-changes` before commits when you want a diff-to-graph check

If GitNexus says the repo is stale or unindexed, re-run `gitnexus analyze` from the repository root before continuing.

The initial scaffold is intentionally minimal. As the codebase grows, this file should describe the actual repo workflow, validation gates, and any code-graph or task-routing conventions that become important.
