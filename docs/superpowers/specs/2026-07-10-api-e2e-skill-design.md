# api-e2e — Fresh-Context E2E Validation of Backend API PRs and Endpoints

**Date:** 2026-07-10
**Status:** Approved design (pre-implementation)
**Location:** `skills/api-tooling/api-e2e/` (new `api-tooling` category)

## Purpose

A distributable skill that drives a thorough, staging-level end-to-end test pass
against a backend API — either an open PR whose build must first reach the
environment, or an already-deployed API/endpoint. The skill encodes the *method*
that produced high-yield manual E2E passes (exhaustive diff-to-wire-expectation
mapping, build fingerprinting, attribution proofs, rollback verification,
disciplined failure triage) so that any teammate can run an equivalent pass
without prior knowledge of the *method*. The operator still brings the
environment knowledge: phase 1 states explicit operator prerequisites (access,
base URLs, safe tenant, token-mint recipes, data-permission authority), and
when the operator cannot supply an answer the run degrades to read-only
rather than guessing.

Primary target: Mindbody/Arcus staging services (shared platform mechanics:
Identity-token auth, `staging.*` bases, ADO deploy pipelines). Secondary: any
company backend API, because nothing platform-specific is hard-coded — auth,
deploy, and fingerprinting are all derived or interviewed per run.

## Doctrine (non-negotiables, stated at the top of SKILL.md)

1. **Three information sources.** A run derives everything from exactly:
   (a) the deployed repository head, (b) live probing of the environment,
   (c) the user interview. Nothing else is authoritative.
2. **Memory policy.**
   - *Read — allowed as hypotheses only.* Local Claude memories may inform a
     run (fixture recipes, platform quirks), but every environment fact taken
     from memory is untrusted until re-verified live. Memory never substitutes
     for repo-head derivation or for pre-write probing.
   - *Write — local per-user memory only.* Runs may save durable learnings to
     the user's local Claude memory, with provenance (date, run context).
     Anything saved is scrubbed of personally identifying fixture fields
     first, using the same rule phase 6 applies before report delivery.
   - *The repo and the skill text carry zero run state, ever.* No fixture
     inventories, testbed files, or environment profiles are committed
     anywhere. Run reports go to a durable user-approved destination
     (phase 6) so coverage evidence survives the session — but they are
     outputs only: no future run reads a past report as authority. A run
     that discovers a durable *method* improvement proposes a skill-text PR
     to the user (executed in phase 7); it never self-writes it.
   - Rationale — blast-radius containment first, ensemble diversity second:
     a wrong "fact" cached in shared state would poison every teammate's
     runs, while a wrong local memory is contained to one user and is
     error-corrected by the verify-live rule. Independent fresh runs are also
     nondeterministic in different ways, so across many runs by many
     teammates the team gets wider coverage than any curated matrix. This
     deliberately trades team-level knowledge pooling for containment:
     per-user memories will diverge, and that is accepted.
3. **Skill text contains method, zero environment facts.** No service names,
   IDs, URLs, tenant numbers, or quirks in the skill. All examples generic.
4. **Never presume — interview.** Any missing capability, credential,
   permission, or fixture becomes a question to the user. This includes asking
   the user to create fixtures in domains they have not exposed to the run
   (e.g., "I need a client configured with X; the client domain isn't available
   to me — please create one and give me its id").
5. **Hard gates.** No test execution before the build fingerprint passes. No
   writes before the contract-test no-touch list is derived and the fixture
   plan is user-approved. No run is complete without cleanup verification and
   the report.
6. **Secrets are session-scoped.** Token-mint curls and credentials pasted by
   the user live in the session scratchpad only — never in any committed,
   persistent, or memory file.

## Architecture

`SKILL.md` (orchestrator, ~150 lines: trigger phrases, doctrine, phase
sequence, gate summary) plus one file per phase under `steps/`. This mirrors
the existing `pr-autopilot` convention in this repo. Each step file ends with
its exit gate. Optional intensity — not architecture: for large diffs, the
matrix-derivation step may fan out per-category subagents and reconcile.

Trigger phrases: "run e2e against PR #N", "e2e-validate this endpoint",
"/api-e2e". Argument hint: `[PR number / PR URL / endpoint description]`.

## Phases

### 0 — Preflight: tooling & access probe (`steps/0-preflight.md`)

Detect what exists on the machine: `gh`, `az`, ADO MCP tools, `curl`,
`jq`/`python`, a local checkout of the target repo. Every gap degrades to
"ask the user":

- Repo access: local checkout at the right commit → GitHub token → (last
  resort) user pastes specific files on request.
- Pipeline visibility: ADO MCP → plain REST with a user-supplied PAT
  (Build-read scope, Basic auth) → user runs the check and pastes the result.
  Zero ADO access is acceptable: the build fingerprint, not the pipeline, is
  ground truth for what is deployed. A raw `dev.azure.com` URL is not
  directly fetchable without auth — never assume it is.

**Gate:** the run knows, for each capability it will need, either a working
tool or the user-mediated fallback.

### 1 — Interview (`steps/1-interview.md`)

Structured, back-and-forth, one topic at a time. The interview is where the
operator's environment knowledge enters the run — the skill supplies the
method, the operator supplies the environment.

**Operator prerequisites (stated up front):** access to the target
environment; base URL(s) and a safe tenant/subscriber; a token-mint recipe
per domain the tests will call; authority to designate mutable data and to
create fixtures in domains not exposed to the run. An operator missing one
of these is told exactly what is missing, not silently blocked.

**Memory-seeded fast path:** when local memory carries prior answers for the
target service (base URLs, tenant, token-mint recipe, data permissions),
present them as prefilled hypotheses for one-shot confirm-or-correct instead
of asking each topic cold — consistent with the read-as-hypotheses doctrine.
Confirmed values remain subject to live verification.

Collect:

- **Mode:** open PR (deploy + fingerprint + test) vs. already-deployed.
- **Target:** service under test; the specific PR or endpoint(s); any
  secondary domains the tests will need to call.
- **Deployed ref** (deployed mode): which commit/branch/tag is currently
  deployed — the input phase 2 derives from and phase 3 verifies.
- **Environment:** base URL(s), tenant/subscriber to use.
- **Auth:** one token-mint curl per domain. Each is verified immediately with
  a benign read before proceeding; expiry behavior noted for mid-run re-mint.
- **Data permissions:** which pre-existing data the run may *reference*
  (clients, staff, rooms, locations, …) and which objects, if any, the user
  designates as *mutable*. Explicitly ask about anything ambiguous.
  **Read-only fallback:** if the user cannot confidently answer a
  data-permission or tenant-safety question, the run proceeds in read-only
  mode until an authoritative answer arrives. Read-only means safe verbs
  only — write-verb requests, including expected-rejection probes (e.g., a
  POST asserted to 400), count as write coverage and are recorded as gaps.
  When the phase-2 delta map shows the target's coverage is predominantly
  write-dependent, the run states the projected coverage of a read-only
  pass and obtains an explicit proceed-or-defer decision before continuing
  past phase 2.
- **Deploy preference** (PR mode): user deploys (preferred — deployment
  variables are theirs to set), user provides a run URL to monitor, or user
  authorizes the skill to trigger the pipeline after confirming its identity.
- **Report destination:** a durable, user-approved destination is mandatory
  in both modes, alongside the session scratchpad working copy. PR mode uses
  the PR itself (comment). Deployed mode uses one canonical per-service
  destination (e.g., a fixed per-service wiki index page every deployed-mode
  run appends its report to), agreed once and confirmed at interview — so
  the union of runs stays observable instead of scattering across ad-hoc
  locations. The skill never commits reports to a repo, and no future run
  reads a past report as authority.

**Gate:** every interview-known domain has a verified token; the mode,
target, and data permissions are explicit. **Re-interview loop-back:** any
later phase that discovers a newly required domain (e.g., a side-effect
witness API surfaced by phase 2 derivation) returns to this phase's
token/permission procedure for that domain before proceeding.

### 2 — Ground truth from repo head (`steps/2-ground-truth.md`)

All derivation from the deployed commit, freshly, this run:

a. **Wire-observable behavior map.** In PR mode, map every commit in the diff
   to its observable effects: status codes, exact validation messages, error
   payload shapes (type/title/detail/extensions), precedence ordering among
   failures, headers (e.g., Retry-After), side effects and the read APIs that
   witness them. In deployed mode, do the same for the target endpoint's
   handlers, validators, and data access. The output is an explicit list of
   expected behaviors, each traceable to a code location. Commits with no
   wire-observable surface (pure refactors, comment- or test-only changes)
   get a justified skip — derive just enough to demonstrate the absence of
   observable effect, and record the skip as a coverage-gap entry exactly
   like an unexecuted matrix row.
b. **No-touch inventory.** Read the repo's contract/behavioral test sources
   and extract every fixture the tests depend on (hardcoded ids, seeded
   objects, counted collections). Record collection-level predicates, not
   just object ids — a test that counts or enumerates a collection is
   violated by *creating* an object that joins it, not only by mutating a
   member. Fixtures the run cannot resolve from source (env-var indirection,
   CI-time constants, external seed scripts) are surfaced as explicit
   interview questions, never assumed absent. These objects must not be
   mutated, and writes that would change their observable state (e.g., adding
   a child row a test counts) are equally off-limits. Supplement by asking
   the user for additional off-limits objects.
c. **Deployment model.** Derive from the repo's infra/pipeline config how a
   build reaches the environment (canary vs. direct, promotion behavior,
   racing deploys). Never assume; verify empirically in phase 3.
d. **Build fingerprint.** Establish how the run will recognize the build
   under test, via a fallback ladder: (1) a build-identity endpoint
   (version/build-info/assembly hash) whenever the service exposes one —
   defect-independent, so preferred; (2) a *read-observable* behavior unique
   to the build (e.g., a new validation message or endpoint the previous
   build lacks) — write-dependent behaviors are ineligible, since the
   fingerprint must pass before any write is permitted; (3) user-confirmed
   deploy evidence (pipeline run + commit SHA), explicitly recorded in the
   report as a weaker fingerprint. The fingerprint is asserted at the start
   AND end of every matrix script; a flip invalidates intervening results.
   **Behavior-fingerprint failure vs. build defect:** repeated rung-2
   fingerprint failure combined with confirmed deploy evidence is escalated
   as a candidate build defect in the fingerprint behavior itself — it
   enters the phase-5 disposition process rather than looping the
   environment gate as "not deployed". **Rung-3 compensating control:** with
   no wire-observable fingerprint to assert, each matrix script instead
   re-queries the service's deploy/pipeline history at start and end (via
   whatever access preflight established, or user re-confirmation when
   access is zero); any deploy record newer than the confirmed one counts as
   a flip and triggers the phase-5 abort/taint procedure, and the report's
   fingerprint-evidence section must state that rung-3 runs carry
   undetectable-flip risk.

**Gate:** delta list, no-touch inventory, deployment model, and fingerprint
all exist and are traceable to repo head.

### 3 — Environment gate — both modes (`steps/3-environment-gate.md`)

Verify the live environment is the build the run derived from, in both modes.

*Deployed mode:* verify the live build corresponds to the deployed ref
collected in phase 1, using the phase-2d fingerprint ladder (build-identity
endpoint, unique read-observable behavior, or user-confirmed deploy
evidence). On mismatch, stop and reconcile with the user — re-derive phase 2
from the correct ref or fix the environment; never test against expectations
derived from a different commit.

*PR mode:* fingerprint the live environment. If it already matches, proceed.
If not:

1. Prefer the user deploys. If they provide a pipeline run URL, monitor it via
   whatever access preflight established.
2. If the user asks the skill to trigger the deploy, first present the exact
   pipeline (name, id, project) derived from repo config and get explicit
   confirmation it is the right one.
3. Regardless of who deploys, converge on the *fingerprint*: poll until 3
   consecutive hits (default; guards against canary windows, promotion
   delays, and racing deploys silently replacing the build).

**Gate:** 3 consecutive fingerprint passes (or, on the ladder's weakest rung,
user-confirmed deploy evidence recorded in the report). No matrix executes
before this.

### 4 — Matrix derivation & scripting (`steps/4-matrix.md`)

Cross the phase-2 delta list with invariant categories — every category is
considered for every delta, and omissions are recorded as explicit coverage
gaps, never silently dropped:

- **Auth edges:** no token, wrong-audience token, cross-tenant access.
- **Validation:** every validator rule, asserted on exact message text.
- **Not-found / permission / validation precedence:** probe the ordering.
- **Conflict paths:** each conflict producer, asserted on payload shape, and
  **rollback verified by re-reading** the would-be-mutated object.
- **Happy paths:** every write arm, with side effects witnessed through read
  APIs (not assumed from the status code).
- **Attribution proofs:** for any behavior that depends on ambient state,
  create the cause → observe the effect → remove the cause → observe the
  effect vanish. A conflict that fires against pre-existing state is not
  proof; a conflict you can switch on and off is.
- **Boundary values:** min/max dates, sentinels, zero, off-by-one on ranges.
- **Negative controls:** checks that must NOT fire, proving specificity.
- **Regression sweep:** adjacent untouched surface (sibling endpoints, older
  API versions) still behaves as before.

Rules:

- **Probe before choosing.** Never assume a slot/fixture is free; enumerate
  live state first (including inactive/cancelled objects where the API hides
  them by default).
- **Fixture policy (three tiers):** (1) the API under test gets run-created
  disposable fixtures wherever a create API exists; (2) surrounding reference
  data is used-not-mutated, with user permission; (3) no-touch objects are
  never written to, directly or observably. Where creation isn't possible via
  API, ask the user to create or designate.
- **Matrix prioritization:** every derived row carries an explicit risk
  tier. Tier 1 (always executed): the delta's write arms, conflict paths
  with rollback verification, and precedence changes. Tier 2 (executed
  unless the user trims): validation rules, auth edges, boundary values,
  attribution proofs, and negative controls. Tier 3 (sampled by default):
  the regression sweep of adjacent untouched surface. The full untrimmed
  matrix is always preserved — anything not executed is recorded as an
  explicit coverage gap, never silently dropped.
- **Executed-tier approval gate:** a standalone pre-execution gate in all
  modes — it fires even when the matrix contains no writes, and merges with
  the fixture-plan gate when writes exist. The approval presentation
  includes an excluded-rows summary: per-category counts of unexecuted
  rows, with the highest-risk excluded rows named individually.
- **Executable scripts** in the session scratchpad: bash + curl + jq/python,
  PASS/FAIL asserts on status AND body content, full response capture to a
  results file, fingerprint gates at both ends, cleanup functions, idempotent
  re-run safety where possible.
- **Fixture-plan approval gate:** before any write executes, present the user
  a plan of what will be created, which pre-existing objects will be
  referenced, anything irreversible, and the executed matrix tier. Every
  planned create/delete is cross-checked against the no-touch inventory's
  collection-level predicates (not just object ids); collisions and
  unresolved test-fixture indirection become interview questions before
  approval. Writes begin only on approval.

**Gate:** user-approved executed tier (all modes) and fixture plan (when
writes exist); scripts exist with fingerprint gates.

### 5 — Execution & triage (`steps/5-execute.md`)

Run matrices serially (shared staging: concurrent probes corrupt each other's
fixtures). Every FAIL must be dispositioned into exactly one of:

1. **Build defect** — the deployed code deviates from the derived expectation.
   Report it with reproduction.
2. **Environment/fixture assumption wrong** — prove by probing (e.g., the slot
   was organically occupied), fix the fixture, rerun.
3. **Harness bug** — script/capture error; fix, rerun.
4. **Expectation mis-derived** — re-read the code, correct the expectation,
   rerun.

Rule: a FAIL is not a build defect until the fixture assumption has been
verified live. Mid-run events: token expiry → re-mint from the interview
curl; fingerprint flip (racing deploy) → abort, mark tainted checks, re-enter
the phase-3 environment gate (both modes), rerun tainted checks.

**Gate:** zero undispositioned FAILs.

### 6 — Report (`steps/6-report.md`)

Mandatory sections:

- Build identity + fingerprint evidence (what was asserted, when, both ends).
- Counts: asserted checks, passes, failures by disposition.
- Per-delta verification table (delta → verified behavior → check ids).
- Every FAIL and its disposition, including "the build was right" cases.
- **Coverage gaps:** every matrix row not executed, categorized by reason
  (not constructible, not reachable, not approved / lower tier, derivation
  skipped), why, and where that behavior is covered instead (unit/contract).
  Never silent.
- Residual state: everything the run left behind, exactly.
- Cleanup verification results.

**Redaction before delivery:** strip Authorization headers, tokens, and other
credential material, plus personally identifying fixture fields, from the
entire assembled report — every mandatory section, including residual state,
not just captured responses and reproductions. The user's approval pass
reviews already-sanitized content and is never the only defense.

Delivery: the report goes to the durable destination agreed in phase 1, and
in both modes the user approves the content before it is published (PR
comment in PR mode; the per-service canonical destination in deployed mode),
so coverage gaps survive the session.

### 7 — Cleanup (`steps/7-cleanup.md`)

- Delete run-created fixtures; verify each deletion **by observation**
  (re-read/enumerate), never by trusting the delete's status code.
- Restore user-designated mutables to their interviewed state if the user
  asked for restoration.
- Re-read a sample of no-touch objects to confirm they are untouched.
- Enumerate all unavoidable leftovers into the report's residual-state
  section.
- If the run discovered a durable *method* improvement, draft the skill-text
  diff and present it to the user for approval — the doctrine-2 "propose a
  skill-text PR" behavior executes here, before the run is complete.

**Gate:** cleanup verified; report delivered; any method-improvement proposal
presented.

## Non-goals

- Not a load/performance tool.
- Not a substitute for contract/unit/behavioral tests — it reports where
  those are the coverage for non-constructible paths.
- No CI integration in v1; the skill is interactive by design (the interview
  is the interface).
- No automated fixture creation in domains the user has not exposed.
- No run-state persistence of any kind outside local per-user memory; run
  reports are delivered to user-owned durable destinations but are never
  consumed as inputs by later runs.

## Acceptance test for the skill itself

Two criteria:

1. **Replay (mechanism).** Point the built skill at a previously validated PR
   of a known repo in deployed mode, with a fresh session. First derive the
   fingerprint from a commit known NOT to be deployed and verify the run
   refuses to execute; then re-derive from the deployed head and proceed.
   Seed one deliberate harness bug so at least one FAIL flows through the
   four-way disposition process. Verify the run (a) derives a matrix covering
   the known delta classes, (b) enforced the refusal, (c) enforces the
   fixture-plan approval gate before any write, and (d) produces a report
   containing all mandatory sections.
2. **Transfer (the actual product claim).** A teammate who neither authored
   the skill nor the original manual passes — but who satisfies the phase-1
   operator prerequisites — completes a full run (phases 0–7) against a
   service they have not previously tested. Stalls and misunderstandings
   about the *method* (what to do next, gate confusion, derivation steps)
   are skill-text defects; a stall on an operator prerequisite counts as a
   defect only if the skill failed to name the missing prerequisite
   precisely. The run satisfies the criterion only if it reaches a
   user-approved tier that includes executed write coverage — a
   read-only-degraded run does not count as a transfer pass.

Neither criterion persists artifacts beyond the report's durable destination.

## Decisions log (from brainstorming)

- Scope: primarily Arcus/Mindbody staging, generalizes to any company API;
  both PR mode and already-deployed mode. (user)
- Strict fresh context: no cross-run persistence; repo head + live probing +
  interview are the only sources; ensemble-of-independent-runs is the
  coverage mechanism. (user)
- Amendment: local Claude memories may be read (as unverified hypotheses) and
  written (per-user only); the repo/skill never carries state. (user)
- Deploys: offer to run but confirm pipeline identity first; prefer
  user-run deploys; accept run URLs for monitoring. (user)
- Fixtures: create-your-own for the API under test; reuse pre-existing
  surrounding data with permission; never touch contract-test objects or
  their observable state. (user)
- Architecture: orchestrator SKILL.md + steps/ files, matching pr-autopilot;
  subagent fan-out as optional intensity in matrix derivation. (user chose
  recommendation)
- ce-doc-review round 1 (2026-07-10): 6 personas, 14 actionable findings —
  13 applied via best-judgment routing, 1 deferred below. (review)
- ce-doc-review round 2 (2026-07-10): 6 personas re-run with decision primer;
  12 actionable findings on the round-1 fixes' composition — all 12 applied
  (transfer criterion made evaluable, rung-3 compensating control, ladder
  reorder, read-only write-verb boundary + checkpoint, full tier enumeration,
  standalone tier-approval gate, whole-report redaction, both-modes delivery
  approval, canonical per-service destination, memory PII scrub, derivation
  skip rule, coverage-gap definition unified). (review)

## Deferred / Open Questions

### From 2026-07-10 review

- **Subagent fan-out threshold (Architecture / Phase 4):** "large diffs" has
  no defined criterion (commit count, endpoint count, file count), so
  implementers must guess per run whether matrix derivation fans out — and
  the acceptance replay cannot verify the path deterministically. Decide:
  a fixed threshold in the skill text, or a per-run user choice at the
  interview. (scope-guardian, P2, confidence 75)
