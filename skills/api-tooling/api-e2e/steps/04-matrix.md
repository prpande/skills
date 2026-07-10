# Phase 4 — Matrix derivation & scripting

Cross the phase-2 delta list with the invariant categories below. Every
category is considered for every delta; every omission becomes an explicit
coverage-gap row — never silently dropped.

## Invariant categories

- **Auth edges:** no token, wrong-audience token, cross-tenant access.
- **Validation:** every validator rule, asserted on exact message text.
- **Not-found / permission / validation precedence:** probe the ordering.
- **Conflict paths:** each conflict producer, asserted on payload shape,
  with **rollback verified by re-reading** the would-be-mutated object.
- **Happy paths:** every write arm, side effects witnessed through read
  APIs — never assumed from the status code.
- **Attribution proofs:** for behavior depending on ambient state — create
  the cause, observe the effect, remove the cause, observe it vanish. A
  conflict firing against pre-existing state is not proof; one you can
  switch on and off is.
- **Boundary values:** min/max dates, sentinels, zero, off-by-one ranges.
- **Negative controls:** checks that must NOT fire, proving specificity.
- **Regression sweep:** adjacent untouched surface (sibling endpoints,
  older API versions) still behaves as before.

## Rules

- **Probe before choosing.** Never assume a slot/fixture is free —
  enumerate live state first, including inactive/cancelled objects where
  the API hides them by default.
- **Fixture policy (three tiers):** (1) the API under test gets
  run-created disposable fixtures wherever a create API exists;
  (2) surrounding reference data is used-not-mutated, with user
  permission; (3) no-touch objects are never written to, directly or
  observably. Where creation isn't possible via API, ask the user to
  create or designate (phase-1 loop-back).
- **Matrix prioritization — every row carries an explicit tier:**
  - Tier 1 (always executed): the delta's write arms, conflict paths with
    rollback verification, precedence changes.
  - Tier 2 (executed unless the user trims): validation rules, auth
    edges, boundary values, attribution proofs, negative controls.
  - Tier 3 (sampled by default): the regression sweep.
  The full untrimmed matrix is always preserved in matrix.md — anything
  not executed becomes a coverage-gap row.
- **Executed-tier approval gate (standalone, all modes):** fires even when
  the matrix contains no writes; merges with the fixture-plan gate when
  writes exist. The presentation MUST include an excluded-rows summary:
  per-category counts of unexecuted rows, with the highest-risk excluded
  rows named individually.
- **Executable scripts** in `{scratchpad}/api-e2e/scripts/`: bash + curl +
  jq/python; PASS/FAIL asserts on status AND body content; full response
  capture to `{scratchpad}/api-e2e/results/`; fingerprint gates at both
  ends (per fingerprint.md, honoring the rung-3 compensating control);
  cleanup functions; idempotent re-run safety where possible.
- **Fixture-plan approval gate:** before ANY write executes, present what
  will be created, which pre-existing objects will be referenced, anything
  irreversible, and the executed tier. Cross-check every planned
  create/delete against no-touch.md's COLLECTION-LEVEL predicates (not
  just object ids); collisions and unresolved fixture indirection become
  interview questions before approval. Writes begin only on approval.

## Gate

User-approved executed tier (all modes) and fixture plan (when writes
exist), both recorded in run-context.md; scripts exist with fingerprint
gates at both ends.
