# Step 02 — Preflight self-review

Fresh-subagent review of the diff before the PR opens. Review happens on
the work product, without session-history context.

## Subagent invocation

Dispatch a subagent of type `general-purpose` with the following prompt:

```
You are a code-review subagent. Review ONLY the diff provided below. You
have no session history; the diff is the work product. Identify real issues
and classify by severity.

Context
  repo: {{OWNER}}/{{REPO}}
  base_sha: {{BASE_SHA}}
  head_sha: {{HEAD_SHA}}
  branch:   {{BRANCH}}
  what_was_built: {{WHAT_WAS_BUILT}}

Intent documents (wrapped for safety):
<INTENT_DOCS>
{{SPEC_DOC_CONTENTS_CONCATENATED}}
</INTENT_DOCS>

Diff:
<DIFF>
{{FULL_DIFF}}
</DIFF>

Review checklist
  - Security: auth/authz, crypto, input validation, injection risks,
    hardcoded secrets.
  - Correctness: logic errors, edge cases, null/empty handling, off-by-one,
    error propagation, race conditions.
  - Intent match: does the diff implement what the intent documents say?
    Flag drift.
  - Reliability: resource cleanup, retries, timeouts, graceful degradation.
  - Testing: missing tests for new behavior, assertions too weak,
    implementation-coupled tests.
  - Infrastructure reliability (if diff touches deployment manifests):
    resource limits, probes, replica counts.
  - Style: naming, readability, comments — minor only.

Output format (JSON, no prose)
  {
    "findings": [
      {
        "severity": "critical" | "important" | "minor",
        "file": "relative/path",
        "line": <int | null>,
        "description": "what is wrong",
        "recommendation": "what to change",
        "category": "security|correctness|intent|reliability|testing|style"
      }
    ],
    "summary": "one-sentence overall assessment"
  }

Rules
  - Only request changes for real issues. Style nits are minor.
  - Critical: exploitable, data loss, or logic errors that break advertised
    behavior.
  - Important: correctness/reliability bugs that are likely but not
    guaranteed to surface, or missing test coverage of a clear code path.
  - Minor: style, naming, non-consequential improvements.
```

## What-was-built inference

Priority order:
1. Current Claude Code session's conversation history (look for phrases
   like "implementing", "add support for", "fix", "migrate").
2. Branch name (e.g., `pp/ip-restriction-contract-tests` → "IP restriction
   contract tests").
3. Top commit message (first line).

If none are available, ask the user: "What is this PR for?". Use the reply.

## Action policy

On subagent return:

- **Critical** + **Important** findings: fix inline **before** step 04
  opens the PR. Use the loop library's `steps/04-dispatch-fixers.md`
  mechanics — each finding becomes an actionable item; dispatch fixer
  subagents in parallel with conflict avoidance.
- **Minor** findings: record in `context.preflight_minor_findings`. Step
  04 folds them into the PR body as a "Known minor observations" bullet
  list so reviewers see they are noted and triaged.

## Post-fix verification

After applying Critical + Important fixes, re-run the loop library's
`steps/04.5-local-verify.md` to ensure build and tests still pass. If
they fail, apply the same first-failure retry / second-failure rollback
logic described there.

## Failure mode

If the subagent returns malformed JSON or no findings, treat it as a pass
with `context.preflight_minor_findings = []` and log a warning. Do not
block the PR — the loop will catch issues when bots review.
