---
name: security-review
description: Review the current diff for newly introduced high-confidence security vulnerabilities. Use before PRs, on active branches, or when asked to perform a focused security review of pending changes. Report only concrete HIGH findings and obvious MEDIUM findings, preserve the upstream false-positive exclusions, and keep the review scoped to the current diff rather than the whole repository.
---

# Security Review

Review only the pending code changes and report only real, newly introduced security issues with a high confidence bar.

## Scope

Review the current branch diff against its base when available.

If a branch diff is unavailable, review local staged and unstaged changes instead.

Do not review the entire repository. Do not report pre-existing issues that are unrelated to the current diff.

## Objective

Perform a focused security review of the diff and identify only HIGH-confidence vulnerabilities with real exploitation potential.

This is not a general code review. Focus only on security implications newly added by the diff.

## Core Rules

1. Minimize false positives. Only flag issues where you are at least `8/10` confident there is a real vulnerability.
2. Avoid noise. Skip theoretical issues, style concerns, and low-impact findings.
3. Focus on impact. Prioritize vulnerabilities that could lead to unauthorized access, data exposure, code execution, privilege escalation, or compromise of business-critical operations.
4. Better to miss speculative issues than flood the report with noise.

## Review Areas

Examine the diff for concrete issues in areas such as:
- input validation vulnerabilities such as SQL injection, command injection, template injection, path traversal, unsafe deserialization, or code execution
- authentication and authorization bypasses
- session or token handling flaws
- unsafe cryptography or certificate-validation bypasses
- XSS only when unsafe rendering methods are actually used
- sensitive data exposure in logs, responses, or persisted state

## Repo-Local Priority Surfaces

Within this repository, look first at:
- request handlers, RPC surfaces, CLI entrypoints, and privileged automation endpoints
- external service integrations, state-changing workflows, and business-critical operations
- authentication and authorization logic around privileged actions
- query construction, ORM usage, and persistence boundaries
- sensitive logging paths involving API keys, secrets, credentials, account data, or PII
- template or frontend rendering paths only when unsafe APIs are actually used

These are review hints only. They do not lower the confidence bar or widen the scope beyond the diff.

## Hard Exclusions

Do not report:
- denial of service, memory, CPU, or other resource exhaustion issues
- secrets or sensitive data stored on disk when they are otherwise secured
- rate limiting concerns
- lack of input validation on non-security-critical fields without proven impact
- vague hardening advice or a lack of best practices by itself
- theoretical race conditions or timing issues without a concrete exploit path
- outdated third-party libraries or general dependency currency issues
- memory-safety issues in memory-safe languages
- unit-test-only or test-runner-only files
- log spoofing
- SSRF findings that control only the path rather than host or protocol
- prompt injection into AI system prompts by itself
- regex injection or regex DoS
- insecure documentation or findings in markdown files
- lack of audit logging
- attacks that depend on controlling trusted environment variables or CLI flags
- subtle low-impact browser issues unless they are extremely high confidence
- React or Angular XSS unless unsafe rendering APIs are used
- client-side-only auth or permission-check findings
- notebook-only issues unless the exploit path is concrete
- shell-script command injection unless untrusted input has a concrete path into the shell

## Severity And Confidence

Use these thresholds:
- `HIGH`: directly exploitable vulnerabilities leading to code execution, authentication bypass, privilege escalation, or meaningful data exposure
- `MEDIUM`: concrete vulnerabilities with a specific exploit path and meaningful impact, but requiring more conditions

Only include `MEDIUM` findings when they are obvious and concrete.

Assign confidence on a `1-10` scale and discard anything below `8`.

## Workflow

1. Understand the diff and the surrounding code context needed to assess the changed lines.
2. Perform an initial pass to identify candidate vulnerabilities.
3. For each candidate, run a false-positive filtering pass.
4. If subagents are available and allowed, use one subtask for initial identification and parallel subtasks for false-positive filtering.
5. If subagents are unavailable or not allowed, perform the same stages sequentially in the current agent.
6. Drop any finding that does not survive the false-positive filter or falls below confidence `8`.

Do not run reproduction commands just to prove a vulnerability if the code is already clear enough to assess by inspection.

## Output

Return markdown only.

For each finding include:
- file
- line number
- severity
- category
- description
- exploit scenario
- fix recommendation
- confidence

If no qualifying findings remain, return a markdown report stating that no high-confidence newly introduced security vulnerabilities were found in the reviewed diff.
