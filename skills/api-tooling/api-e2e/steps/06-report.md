# Phase 6 — Report

Assemble `{scratchpad}/api-e2e/report.md`. Run phase 7 (cleanup) before
final delivery so the residual-state and cleanup-verification sections are
real, then deliver.

## Mandatory sections

Sources: the matrix rows and `## Disposition ledger` in
`{scratchpad}/api-e2e/matrix.md`, fingerprint evidence from
`{scratchpad}/api-e2e/fingerprint.md`, captured responses in
`{scratchpad}/api-e2e/results/`, and the residual-state / cleanup sections
from phase 7.

- **Build identity + fingerprint evidence** — what was asserted, when, at
  both ends of every matrix; the ladder rung used. Rung-3 runs MUST state
  they carry undetectable-flip risk.
- **Counts** — asserted checks, passes, failures by disposition.
- **Per-delta verification table** — delta → verified behavior → check ids.
- **Every FAIL and its disposition** — including "the build was right"
  cases; they are positive evidence, not embarrassments.
- **Coverage gaps** — every matrix row not executed, categorized by reason
  (not constructible, not reachable, not approved / lower tier, derivation
  skipped), why, and where that behavior is covered instead
  (unit/contract). Never silent.
- **Residual state** — everything the run left behind, exactly (from
  phase 7).
- **Cleanup verification results** (from phase 7).

## Redaction before delivery

Strip Authorization headers, tokens, and all credential material, plus
personally identifying fixture fields, from the ENTIRE assembled report —
every mandatory section, including residual state, not just captured
responses and reproductions. The user's approval pass reviews
already-sanitized content and is never the only defense.

## Delivery

The report goes to the durable destination agreed at the interview, and in
BOTH modes the user approves the content before it is published — PR
comment in PR mode; the per-service canonical destination in deployed
mode. The scratchpad copy remains the working artifact; the skill never
commits reports to a repo, and no future run reads a past report as
authority.

## Gate

Report assembled with all mandatory sections, redacted, user-approved, and
delivered to the durable destination.
