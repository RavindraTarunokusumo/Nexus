# Phase 3 CLI + Model Tier Config

**Branch:** `worktree-phase3-cli-testscript`
**PR:** #6
**Merge commit:** `87a869f`
**Date:** 2026-05-19

## What was built

Extended the `nexus` CLI with Phase 3 claim extraction commands and centralised model configuration.

### New CLI commands

- **`nexus extract <doc_id>`** — POSTs to `/documents/{id}/extract-claims`; supports `--force` re-extraction and `--json` output; HTTP timeout raised to 5 min
- **`nexus document --claims`** — appends extracted claims table (or `"claims"` JSON key) to document detail view

### Model tier config

Renamed all model fields in `app/config.py` to a consistent `t1_model` / `t2_model` / `t3_model` scheme. `.env` variable names changed:

| Old | New | Default |
|---|---|---|
| `EMBEDDING_MODEL` | `T1_MODEL` | `BAAI/bge-small-en-v1.5` |
| `OPENROUTER_T2_MODEL` | `T2_MODEL` | `deepseek/deepseek-v4-flash` |
| `OPENROUTER_T3_MODEL` | `T3_MODEL` | `deepseek/deepseek-v4-pro` |

`app/main.py` now passes `settings.t1_model` to `Embedder()` instead of hardcoding the string.

Cost estimate updated to DeepSeek flash pricing (~$0.14/1M tokens).

### Phase 3 validation script

`scripts/run_phase3_cli_validation.ps1` — standalone PowerShell smoke test that resets the DB, seeds a fixture document, waits for embedding, then exercises all Phase 3 CLI paths (extract, --claims, 409 re-run, --force, JSON round-trip).

## Commits

- `37e6832` — feat(cli): add nexus extract command, --claims flag, Phase 3 validation script
- `6b7ee75` — refactor: centralize model config as t1/t2/t3_model in Settings
- `7848a2d` — docs: add nexus extract and --claims flag to CLI reference
- `e3a1280` — chore: update GitNexus index stats
- `a8f1abf` — fix: address Copilot review comments on PR #6
- `5abf9cf` — chore: update GitNexus stats after review fixes

## Review findings addressed

1. `http.py`: `_EXTRACT_TIMEOUT = 300s` for extract; per-call timeout kwarg on `_request`
2. `llm_client.py`: cost constant updated to DeepSeek flash pricing
3. `changelog.md`: Phase 3 entry restored to original; new 2026-05-19 entry with breaking env var rename table
4. `docs/specs/operations.md`, `nexus_lite_mvp_spec_markdown.md`: stale env var names updated
5. `run_phase3_cli_validation.ps1` TEST 3: tightened to require both non-zero exit AND 409 message match
