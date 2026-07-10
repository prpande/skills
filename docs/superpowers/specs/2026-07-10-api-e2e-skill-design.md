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
without prior knowledge of the service.

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
   - *The repo and the skill text carry zero run state, ever.* No fixture
     inventories, testbed files, environment profiles, or run reports are
     committed anywhere. A run that discovers a durable *method* improvement
     proposes a skill-text PR to the user; it never self-writes it.
   - Rationale: independent fresh runs are nondeterministic in different ways;
     across many runs by many teammates this yields wider coverage than any
     curated matrix, and no shared cache exists for one run's wrong "fact" to
     poison. Per-user local memory is tolerated because it is contained to one
     user and is error-corrected by the verify-live rule.
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

Structured, back-and-forth, one topic at a time. Collect:

- **Mode:** open PR (deploy + fingerprint + test) vs. already-deployed.
- **Target:** service under test; the specific PR or endpoint(s); any
  secondary domains the tests will need to call.
- **Environment:** base URL(s), tenant/subscriber to use.
- **Auth:** one token-mint curl per domain. Each is verified immediately with
  a benign read before proceeding; expiry behavior noted for mid-run re-mint.
- **Data permissions:** which pre-existing data the run may *reference*
  (clients, staff, rooms, locations, …) and which objects, if any, the user
  designates as *mutable*. Explicitly ask about anything ambiguous.
- **Deploy preference** (PR mode): user deploys (preferred — deployment
  variables are theirs to set), user provides a run URL to monitor, or user
  authorizes the skill to trigger the pipeline after confirming its identity.
- **Report destination:** a file in the session scratchpad always (handed to
  the user, never committed by the skill); PR comment offered in PR mode.

**Gate:** every domain the matrix will touch has a verified token; the mode,
target, and data permissions are explicit.

### 2 — Ground truth from repo head (`steps/2-ground-truth.md`)

All derivation from the deployed commit, freshly, this run:

a. **Wire-observable behavior map.** In PR mode, map every commit in the diff
   to its observable effects: status codes, exact validation messages, error
   payload shapes (type/title/detail/extensions), precedence ordering among
   failures, headers (e.g., Retry-After), side effects and the read APIs that
   witness them. In deployed mode, do the same for the target endpoint's
   handlers, validators, and data access. The output is an explicit list of
   expected behaviors, each traceable to a code location.
b. **No-touch inventory.** Read the repo's contract/behavioral test sources
   and extract every fixture the tests depend on (hardcoded ids, seeded
   objects, counted collections). These objects must not be mutated, and
   writes that would change their observable state (e.g., adding a child row
   a test counts) are equally off-limits. Supplement by asking the user for
   additional off-limits objects.
c. **Deployment model.** Derive from the repo's infra/pipeline config how a
   build reaches the environment (canary vs. direct, promotion behavior,
   racing deploys). Never assume; verify empirically in phase 3.
d. **Build fingerprint.** Choose a wire-observable behavior unique to the
   build under test (e.g., a new validation message or endpoint the previous
   build lacks). The fingerprint is asserted at the start AND end of every
   matrix script; a flip invalidates intervening results.

**Gate:** delta list, no-touch inventory, deployment model, and fingerprint
all exist and are traceable to repo head.

### 3 — Deploy gate — PR mode only (`steps/3-deploy-gate.md`)

Fingerprint the live environment. If it already matches, proceed. If not:

1. Prefer the user deploys. If they provide a pipeline run URL, monitor it via
   whatever access preflight established.
2. If the user asks the skill to trigger the deploy, first present the exact
   pipeline (name, id, project) derived from repo config and get explicit
   confirmation it is the right one.
3. Regardless of who deploys, converge on the *fingerprint*: poll until 3
   consecutive hits (default; guards against canary windows, promotion
   delays, and racing deploys silently replacing the build).

**Gate:** 3 consecutive fingerprint passes. No matrix executes before this.

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
- **Executable scripts** in the session scratchpad: bash + curl + jq/python,
  PASS/FAIL asserts on status AND body content, full response capture to a
  results file, fingerprint gates at both ends, cleanup functions, idempotent
  re-run safety where possible.
- **Fixture-plan approval gate:** before any write executes, present the user
  a plan of what will be created, which pre-existing objects will be
  referenced, and anything irreversible. Writes begin only on approval.

**Gate:** user-approved fixture plan; scripts exist with fingerprint gates.

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
curl; fingerprint flip (racing deploy) → abort, mark tainted checks, re-gate
via phase 3, rerun tainted checks.

**Gate:** zero undispositioned FAILs.

### 6 — Report (`steps/6-report.md`)

Mandatory sections:

- Build identity + fingerprint evidence (what was asserted, when, both ends).
- Counts: asserted checks, passes, failures by disposition.
- Per-delta verification table (delta → verified behavior → check ids).
- Every FAIL and its disposition, including "the build was right" cases.
- **Coverage gaps:** what was not constructible or reachable, why, and where
  that behavior is covered instead (unit/contract). Never silent.
- Residual state: everything the run left behind, exactly.
- Cleanup verification results.

PR mode: offer to post as a PR comment; user approves content before posting.

### 7 — Cleanup (`steps/7-cleanup.md`)

- Delete run-created fixtures; verify each deletion **by observation**
  (re-read/enumerate), never by trusting the delete's status code.
- Restore user-designated mutables to their interviewed state if the user
  asked for restoration.
- Re-read a sample of no-touch objects to confirm they are untouched.
- Enumerate all unavoidable leftovers into the report's residual-state
  section.

**Gate:** cleanup verified; report delivered.

## Non-goals

- Not a load/performance tool.
- Not a substitute for contract/unit/behavioral tests — it reports where
  those are the coverage for non-constructible paths.
- No CI integration in v1; the skill is interactive by design (the interview
  is the interface).
- No automated fixture creation in domains the user has not exposed.
- No run-state persistence of any kind outside local per-user memory.

## Acceptance test for the skill itself

One-time manual replay: point the built skill at a previously validated PR of
a known repo in deployed mode, with a fresh session. Verify it independently
(a) derives a matrix covering the known delta classes, (b) refuses to execute
when the fingerprint fails, (c) enforces the fixture-plan approval gate before
any write, and (d) produces a report containing all mandatory sections. The
replay produces no persisted artifacts.

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
