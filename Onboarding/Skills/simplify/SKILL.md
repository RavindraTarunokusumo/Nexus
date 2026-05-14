---
name: simplify
description: Review recent code changes for reuse, code quality, and efficiency issues, then apply behavior-preserving simplifications. Use before PRs, after feature or bugfix work, or when asked to simplify a recent diff. Accept optional focus text and default to the current branch or worktree changes instead of the whole repository.
---

# Simplify

Review the current diff, look for the highest-value simplifications, and make only safe changes.

## Inputs

Parse `$ARGUMENTS` as optional focus text.

Examples:
- `focus on duplication in request routing`
- `simplify the background job changes`
- `only clean up readability issues`

If the focus text narrows the scope, honor it. If it does not, default to recently changed files in the current branch or worktree.

## Scope

Start with the smallest useful review scope:
1. Files with local staged or unstaged changes
2. Files changed on the current branch relative to its base
3. Files explicitly named by the user

Do not widen to unrelated parts of the repo unless the focus text clearly requires it.

## Workflow

1. Identify the review scope from the current diff and any focus text.
2. Review the scoped files through three lenses:
   - reuse
   - quality
   - efficiency
3. If subagents are available and allowed, run the three review lenses in parallel.
4. If subagents are unavailable or not allowed, run the same three passes sequentially in the current agent.
5. Aggregate the findings and remove duplicates, conflicts, and risky suggestions.
6. Apply only the simplifications that preserve behavior.
7. Run the lightest relevant validation for the touched files.
8. Report what changed, what was validated, and what was intentionally left alone.

## Review Lenses

### Reuse

Look for:
- duplicated logic that should reuse an existing helper or pattern
- newly introduced helpers that add indirection without real reuse
- copy-pasted branches that can be collapsed safely

Prefer existing local patterns over inventing new abstractions.

### Quality

Look for:
- awkward naming
- dead or redundant code
- unnecessary nesting
- conditionals or loops that can be made clearer
- comments that exist only because the code is harder to follow than it needs to be

Prefer direct, readable control flow. Keep comments sparse.

### Efficiency

Look for:
- obviously repeated work inside the changed path
- unnecessary conversions, scans, or allocations
- redundant I/O or queries introduced by the recent changes

Do not trade readability for micro-optimizations. Skip speculative tuning unless the waste is clear in the code path being simplified.

## Guardrails

Apply only behavior-preserving simplifications.

Do not:
- add features
- change public behavior intentionally
- perform broad architectural rewrites
- replace understandable code with clever code
- expand the task into unrelated cleanup

If a larger refactor would be better but exceeds the safe scope, leave it as a follow-up note instead of implementing it here.

## Validation

After edits, run targeted validation that matches the touched files:
- focused tests first
- formatting or lint only when relevant
- broader test runs only when the change surface justifies them

If no safe simplifications are found, say so explicitly instead of forcing changes.

## Output

Return a concise summary with:
1. scope reviewed
2. simplifications made, grouped by reuse, quality, and efficiency when helpful
3. validation run
4. deferred issues that were intentionally left out of scope
