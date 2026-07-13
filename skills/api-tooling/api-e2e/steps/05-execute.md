# Phase 5 — Execution & triage

Run matrices SERIALLY — shared staging means concurrent probes corrupt
each other's fixtures. Capture everything to `{scratchpad}/api-e2e/results/`.

## The four-way FAIL disposition

Every FAIL must land in exactly one bucket, recorded with evidence in the
disposition ledger — a `## Disposition ledger` section appended to
`{scratchpad}/api-e2e/matrix.md` (phase 6 reads it from there):

1. **Build defect** — deployed code deviates from the derived expectation.
   Report with reproduction (redaction happens at phase 6).
2. **Environment/fixture assumption wrong** — prove it by probing (e.g.,
   the slot was organically occupied), fix the fixture, rerun.
3. **Harness bug** — script/capture error; fix the script, rerun.
4. **Expectation mis-derived** — re-read the code, correct
   `{scratchpad}/api-e2e/delta-map.md`, rerun.

**Rule: a FAIL is not a build defect until the fixture assumption has been
verified live.** The build being right and your fixture being wrong looks
identical to a defect until you probe.

**Fixture ledger:** as each write that creates a fixture succeeds, append a
row `fixture id | type | domain | created-by check id` to a `## Fixture
ledger` section of `{scratchpad}/api-e2e/run-context.md`. Phase 7 tears down
from this ledger — a fixture that never made the ledger is a cleanup failure
waiting to happen, so record it in the same breath as the write.

## Mid-run events

- **Token expiry** → re-mint from `{scratchpad}/api-e2e/secrets/mint-<domain>.sh`; resume.
- **Fingerprint flip** (racing deploy; on rung 3, a newer deploy record) →
  abort the current script, mark every check since the last passing
  fingerprint assertion as TAINTED, re-enter the phase-3 environment gate,
  and rerun tainted checks only after it passes again.
- **Newly required domain** (a witness read needs an uninterviewed
  domain) → phase-1 re-interview loop-back, then resume.

## Gate

Zero undispositioned FAILs. Every row in the executed tier is PASS,
dispositioned, or explicitly moved to the coverage-gap list with a reason.
