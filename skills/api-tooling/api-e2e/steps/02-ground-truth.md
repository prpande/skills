# Phase 2 — Ground truth from repo head

Everything is derived from the deployed commit, freshly, this run. The
three information sources are the repo head, live probing, and the
interview — a memory hint may point you at code, but the code decides.

## a. Wire-observable behavior map → delta-map.md

PR mode: map EVERY commit in the diff to its observable effects — status
codes, exact validation messages, error payload shapes
(type/title/detail/extensions), precedence ordering among failures,
headers (e.g., Retry-After), side effects and the read APIs that witness
them. Deployed mode: do the same for the target endpoint's handlers,
validators, and data access. Each expected behavior must be traceable to a
code location (`path:line`).

Commits with no wire-observable surface (pure refactors, comment- or
test-only changes) get a justified skip — derive just enough to
demonstrate the absence of observable effect, and record the skip in
delta-map.md as a coverage-gap entry exactly like an unexecuted matrix row.

**Fan-out (optional intensity):** derive inline until the running delta
count crosses 10 or more wire-observable deltas (default threshold; the
interview may override either way), then fan out the remaining derivation
across per-effect-class subagents — one per effect class (status codes,
validation messages, payload shapes, precedence ordering, headers,
side-effect witnesses) — and reconcile all outputs into one delta-map.md.

## b. No-touch inventory → no-touch.md

Read the repo's contract/behavioral test sources and extract every fixture
the tests depend on: hardcoded ids, seeded objects, counted collections.
Record COLLECTION-LEVEL predicates, not just object ids — a test that
counts or enumerates a collection is violated by *creating* an object that
joins it, not only by mutating a member. Fixtures the run cannot resolve
from source (env-var indirection, CI-time constants, external seed
scripts) become explicit interview questions — never assumed absent.
These objects must not be mutated, and writes that would change their
observable state (adding a child row a test counts) are equally
off-limits. Ask the user for additional off-limits objects and append them.

## c. Deployment model → deploy-model.md

Derive from the repo's infra/pipeline config how a build reaches the
environment: canary vs. direct, promotion behavior, racing deploys. Never
assume; phase 3 verifies empirically.

## d. Build fingerprint → fingerprint.md

Establish how the run recognizes the build under test, via this ladder
(record the selected rung and the exact assertion command):

1. **Build-identity endpoint** (version/build-info/assembly hash) whenever
   the service exposes one — defect-independent, so preferred.
2. **Unique read-observable behavior** (a new validation message or
   endpoint the previous build lacks). Write-dependent behaviors are
   INELIGIBLE — the fingerprint must pass before any write is permitted.
3. **User-confirmed deploy evidence** (pipeline run + commit SHA),
   explicitly recorded in the report as a weaker fingerprint.

The fingerprint is asserted at the start AND end of every matrix script; a
flip invalidates intervening results.

**Behavior-fingerprint failure vs. build defect:** repeated rung-2 failure
combined with confirmed deploy evidence is escalated as a candidate build
defect in the fingerprint behavior itself — route it into the phase-5
disposition process; do NOT loop the environment gate as "not deployed".

**Rung-3 compensating control:** with nothing wire-observable to assert,
each matrix script instead re-queries the service's deploy/pipeline
history at start and end (via whatever access preflight established, or
user re-confirmation when access is zero); any deploy record newer than
the confirmed one counts as a flip and triggers the phase-5 abort/taint
procedure. The report's fingerprint-evidence section must state that
rung-3 runs carry undetectable-flip risk.

## Gate

delta-map.md, no-touch.md, deploy-model.md, and fingerprint.md all exist
and every entry is traceable to repo head. If a new domain surfaced (a
witness API in an uninterviewed domain), run the phase-1 re-interview
loop-back before declaring this gate passed.
