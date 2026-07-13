# api-e2e Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `api-e2e` skill — interview-driven, fresh-context staging E2E validation of a backend API PR or deployed endpoint — per the approved spec `docs/superpowers/specs/2026-07-10-api-e2e-skill-design.md` (two ce-doc-review rounds applied, commit `617a379`).

**Architecture:** Orchestrator `SKILL.md` (~150 lines: frontmatter, doctrine, phase table, gate summary) plus eight step files under `steps/`, one per phase, each ending with its exit gate. New `api-tooling` category directory alongside `pr-tooling`. All deliverables are markdown; run-time artifacts live in the session scratchpad under `{scratchpad}/api-e2e/`.

**Tech Stack:** Markdown + YAML frontmatter (skill file format). The skill itself drives `bash`/`curl`/`jq`/`python` at run time; nothing here installs anything.

**Working directory:** `C:\src\skills-wt\api-e2e-skill` on branch `api-e2e-skill` (worktree of `C:\src\skills`). All paths below are repo-relative to that worktree.

**"Testing":** Markdown prose — no unit-test runner. Structural validation via existing `python scripts/validate.py` (UTF-8, frontmatter, placeholder markers, internal `steps/NN-*.md` reference resolution). Per-task cadence: write file → validate → commit. The spec's acceptance tests (replay + transfer) are post-implementation manual exercises, out of this plan's scope.

## Global Constraints

- Doctrine 3 (spec): skill text contains **method only — zero environment facts**. No service names, URLs, tenant/subscriber numbers, IDs, or platform quirks in the skill text under `skills/api-tooling/api-e2e/` (the design docs under `docs/superpowers/` may name concrete context). All examples in the skill generic ("the service", "domain A").
- Doctrine 6 (spec): token-mint curls and credentials are **session-scoped** — the skill text must direct them to the session scratchpad only, never to committed/persistent/memory files.
- Step files are named with **two-digit prefixes** (`steps/00-preflight.md` … `steps/07-cleanup.md`), matching the pr-autopilot convention and the validator's `steps/NN-*.md` reference pattern.
- The validator rejects line-initial `[TBD]`, `TODO: `, `[fill in`, `XXX ` outside code fences — never leave them in any file.
- Every file UTF-8, LF or CRLF both tolerated.
- **Resolved open question** (spec's Deferred section, decided by this plan and recorded back into the spec in Task 10): subagent fan-out in phase 2/4 triggers at a **fixed default of ≥ 10 wire-observable deltas** in the phase-2 delta map; the interview may override in either direction. Deterministic for the acceptance replay.
- Run artifacts contract (consumed across step files — exact paths):
  - `{scratchpad}/api-e2e/run-context.md` — capability table, interview answers, mode, permissions
  - `{scratchpad}/api-e2e/secrets/mint-<domain>.sh` — token-mint scripts (session-scoped)
  - `{scratchpad}/api-e2e/delta-map.md` — phase-2a output
  - `{scratchpad}/api-e2e/no-touch.md` — phase-2b inventory
  - `{scratchpad}/api-e2e/deploy-model.md` — phase-2c
  - `{scratchpad}/api-e2e/fingerprint.md` — phase-2d (rung, assertion command)
  - `{scratchpad}/api-e2e/matrix.md` — full untrimmed matrix with tiers
  - `{scratchpad}/api-e2e/scripts/matrix-<n>.sh`, `{scratchpad}/api-e2e/results/` — executables + captures
  - `{scratchpad}/api-e2e/report.md` — assembled report

**File map** (all NEW unless noted):

```
skills/api-tooling/api-e2e/SKILL.md                    (Task 9)
skills/api-tooling/api-e2e/steps/00-preflight.md       (Task 1)
skills/api-tooling/api-e2e/steps/01-interview.md       (Task 2)
skills/api-tooling/api-e2e/steps/02-ground-truth.md    (Task 3)
skills/api-tooling/api-e2e/steps/03-environment-gate.md(Task 4)
skills/api-tooling/api-e2e/steps/04-matrix.md          (Task 5)
skills/api-tooling/api-e2e/steps/05-execute.md         (Task 6)
skills/api-tooling/api-e2e/steps/06-report.md          (Task 7)
skills/api-tooling/api-e2e/steps/07-cleanup.md         (Task 8)
README.md                                              (EDIT, Task 10)
docs/superpowers/specs/2026-07-10-api-e2e-skill-design.md (EDIT, Task 10 — record resolved open question)
```

---

## Deviations discovered during execution (2026-07-10)

- **Spec references must be two-digit, not "illustrative":** the validator
  scans `docs/` for backticked `steps/NN-*.md` references; the spec's
  original single-digit names would never resolve. Spec updated to the real
  filenames (committed alongside this note).
- **Per-task validator green is unachievable; Tasks 2–9 consolidated into
  one commit + one review.** Two causes: (a) the committed spec/plan
  reference all eight step files, which only resolve once every file
  exists; (b) until `SKILL.md` exists directly in `api-e2e/`,
  `discover_skill_roots()` registers `steps/` itself as a skill root named
  `steps`, and `check_file()`'s first-segment-exclusive resolution then
  breaks every `steps/NN-*.md` reference repo-wide (37 false failures).
  All references resolve only at the all-nine-files boundary, so that is
  the commit boundary. Review coverage is unchanged: one consolidated
  review checks all nine files against their per-task briefs.
- **Upstream note (not fixed here):** `scripts/validate.py`'s exclusive
  first-segment branch silently changes resolution semantics repo-wide
  when a new skill directory temporarily lacks a direct `.md` — worth a
  separate hardening PR.
- **Phase-7 gate de-circularized (5f529de):** delivery is phase 6's gate;
  07-cleanup's gate is cleanup-verified + sections handed to phase 6. Spec
  gate line aligned in this commit.
- **Phase-4 fan-out rule added to 04-matrix.md (5f529de):** SKILL.md
  promised it, the step file lacked it.
- **Script numbering convention (5f529de):** `scripts/matrix-<n>.sh`
  numbering convention documented in 04-matrix.md.
- **Disposition-ledger location pinned (5f529de):** the ledger lives at
  `{scratchpad}/api-e2e/matrix.md` per 05-execute.md, so phase 6 has a
  producer.
- **Final-review fix set (this commit):** fixture-ledger producer added to
  05/07; `{scratchpad}` token defined in SKILL.md + 00; SKILL.md step
  links made validator-visible (backticked link text); doctrine 3 scoped
  to target-environment facts; fixture-policy "tiers" renamed "classes"
  (spec mirrored); phase-2a fan-out recorded in the spec with an
  effect-class partition; spec phase-7 gate aligned to the built files.

## Phase A — Step files (each self-contained; validator passes without SKILL.md, per the pr-loop-lib precedent)

### Task 1: Create `steps/00-preflight.md`

**Files:**
- Create: `skills/api-tooling/api-e2e/steps/00-preflight.md`

**Interfaces:**
- Consumes: nothing (first phase).
- Produces: `{scratchpad}/api-e2e/run-context.md` with a **Capabilities** table (`capability | status: tool|user-mediated | detail`) that steps 01/03/05 read.

- [ ] **Step 1: Write the file**

````markdown
# Phase 0 — Preflight: tooling & access probe

Detect what exists on this machine. Every gap degrades to "ask the user" —
nothing is assumed installed, and no missing tool blocks the run.

Create the run workspace first:

```bash
mkdir -p "{scratchpad}/api-e2e/secrets" "{scratchpad}/api-e2e/scripts" "{scratchpad}/api-e2e/results"
```

## Probe (non-fatal, one pass)

Run each probe; record the outcome in the Capabilities table:

```bash
gh --version        # GitHub CLI
az --version        # Azure CLI (optional, heaviest dependency — never required)
curl --version
jq --version || python --version   # at least one JSON processor
git rev-parse --show-toplevel      # inside the target repo? (run from the repo if known)
```

For MCP-provided pipeline tools (e.g., an Azure DevOps MCP server), use
ToolSearch with a keyword query like "pipelines get build" — presence of
matching tools means MCP access exists. Interactively-authenticated MCP
servers may be absent in headless runs; treat absence as a normal gap.

## Access ladders (record the selected rung per capability)

**Target repo access** — the run derives everything from the deployed repo
head, so one of these must exist:
1. A local checkout the run can `git -C <path>` into at the right commit.
2. A GitHub (or equivalent) token the user pastes — verify with one benign
   API read before recording it as working.
3. Last resort: the user pastes specific files on request. Acceptable but
   slow; tell the user derivation quality depends on what they paste.

**Pipeline visibility** (PR mode deploy monitoring only — zero pipeline
access is acceptable because the build fingerprint, not the pipeline, is
ground truth for what is deployed):
1. MCP pipeline tools (if the probe found them).
2. Plain REST with a user-supplied PAT (read scope for builds), Basic auth
   via curl. A raw pipeline URL (e.g., `dev.azure.com/...`) is NOT directly
   fetchable without auth — never assume it is.
3. The user runs the check themselves and pastes the result.

## Capabilities table

Write `{scratchpad}/api-e2e/run-context.md` starting with:

```markdown
# api-e2e run context
## Capabilities
| capability | status | detail |
|---|---|---|
| repo access | tool / user-mediated | <rung + how verified> |
| pipeline visibility | tool / user-mediated / none | <rung> |
| http client | tool | curl <version> |
| json processor | tool | jq / python |
```

Secrets never go into this file — mint scripts live in
`{scratchpad}/api-e2e/secrets/` only.

## Gate

The run knows, for each capability it will need, either a working tool or
the user-mediated fallback. Do not proceed to the interview until the
Capabilities table has a row for repo access, pipeline visibility, http
client, and JSON processor.
````

- [ ] **Step 2: Validate**

Run: `cd /c/src/skills-wt/api-e2e-skill && python scripts/validate.py`
Expected: exit 0, `OK`

- [ ] **Step 3: Commit**

```bash
git add skills/api-tooling/api-e2e/steps/00-preflight.md
git commit -m "feat(api-e2e): phase-0 preflight step"
```

### Task 2: Create `steps/01-interview.md`

**Files:**
- Create: `skills/api-tooling/api-e2e/steps/01-interview.md`

**Interfaces:**
- Consumes: Capabilities table from `{scratchpad}/api-e2e/run-context.md` (Task 1 shape).
- Produces: interview sections appended to `run-context.md` (`## Mode`, `## Target`, `## Environment`, `## Data permissions`, `## Report destination`); `secrets/mint-<domain>.sh` per domain. The **re-interview loop-back** procedure defined here is invoked by steps 02 and 04.

- [ ] **Step 1: Write the file**

````markdown
# Phase 1 — Interview

Structured, back-and-forth, one topic at a time. The interview is where the
operator's environment knowledge enters the run — the skill supplies the
method, the operator supplies the environment. Never presume: any missing
capability, credential, permission, or fixture becomes a question. Use
AskUserQuestion for crisp either/or choices; plain prose for open answers.

## Operator prerequisites — state these up front

The operator must bring: access to the target environment; base URL(s) and
a safe tenant; a token-mint recipe per domain the tests will call;
authority to designate mutable data and to create fixtures in domains not
exposed to the run. If a prerequisite is missing, name exactly which one —
never silently block.

## Memory-seeded fast path

If local memory carries prior answers for this service (base URLs, tenant,
token-mint recipe, data permissions), present them as prefilled hypotheses
for one-shot confirm-or-correct instead of asking each topic cold.
Confirmed values remain hypotheses until verified live — memory never
substitutes for probing.

## Collect (in order; append each answer to run-context.md)

1. **Mode** — open PR (deploy + fingerprint + test) vs. already-deployed.
2. **Target** — service under test; the PR or endpoint(s); any secondary
   domains the tests will call.
3. **Deployed ref** (deployed mode only) — which commit/branch/tag is live.
   This is what phase 2 derives from and phase 3 verifies. If the ref is a
   branch name, resolve and record the commit SHA now — branches move.
4. **Environment** — base URL(s); tenant/subscriber to use.
5. **Auth** — one token-mint curl per domain. Save each as
   `{scratchpad}/api-e2e/secrets/mint-<domain>.sh`; run it; verify the
   token with a benign read against that domain before accepting it; note
   expiry behavior for mid-run re-mint. Secrets live ONLY under
   `secrets/` — never in run-context.md, reports, memory, or any commit.
6. **Data permissions** — which pre-existing data the run may *reference*
   (read/associate, never mutate) and which objects the user designates
   *mutable*. Ask explicitly about anything ambiguous.
   **Read-only fallback:** if the user cannot confidently answer a
   data-permission or tenant-safety question, the run proceeds read-only
   until an authoritative answer arrives. Read-only means safe verbs only —
   write-verb requests, INCLUDING expected-rejection probes (a POST
   asserted to 400), count as write coverage and are recorded as gaps.
   If the phase-2 delta map later shows coverage is predominantly
   write-dependent, state the projected coverage of a read-only pass and
   get an explicit proceed-or-defer decision before continuing past
   phase 2.
7. **Deploy preference** (PR mode) — prefer the user deploys (deployment
   variables are theirs); or the user provides a pipeline run URL to
   monitor; or the user authorizes the skill to trigger the pipeline —
   only after confirming its exact identity (phase 3).
8. **Report destination** — a durable, user-approved destination is
   mandatory in both modes, alongside the scratchpad working copy.
   PR mode: the PR itself (comment). Deployed mode: ONE canonical
   per-service destination (e.g., a fixed per-service wiki index page every
   deployed-mode run appends to), agreed once and confirmed here — so the
   union of runs stays observable. The skill never commits reports to a
   repo; no future run reads a past report as authority.

## Re-interview loop-back (referenced by later phases)

When any later phase discovers a newly required domain (e.g., a
side-effect witness API surfaced by phase-2 derivation), return HERE for
that domain only: collect its token-mint curl, verify with a benign read,
record its data permissions, then resume the interrupted phase.

## Gate

Every interview-known domain has a verified token; mode, target, and data
permissions are explicit in run-context.md. Do not start derivation until
this holds.
````

- [ ] **Step 2: Validate**

Run: `python scripts/validate.py`
Expected: exit 0, `OK`

- [ ] **Step 3: Commit**

```bash
git add skills/api-tooling/api-e2e/steps/01-interview.md
git commit -m "feat(api-e2e): phase-1 interview step"
```

### Task 3: Create `steps/02-ground-truth.md`

**Files:**
- Create: `skills/api-tooling/api-e2e/steps/02-ground-truth.md`

**Interfaces:**
- Consumes: `run-context.md` (mode, target, deployed ref); repo access rung from Capabilities.
- Produces: `delta-map.md`, `no-touch.md`, `deploy-model.md`, `fingerprint.md` (with `rung: 1|2|3` and the exact assertion command). Steps 03/04/05 read all four.

- [ ] **Step 1: Write the file**

````markdown
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

**Fan-out (optional intensity):** if the delta map reaches 10 or more
wire-observable deltas (default threshold; the interview may override
either way), fan out per-category derivation subagents and reconcile their
outputs into one delta-map.md. Below the threshold, derive inline.

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
````

- [ ] **Step 2: Validate**

Run: `python scripts/validate.py`
Expected: exit 0, `OK`

- [ ] **Step 3: Commit**

```bash
git add skills/api-tooling/api-e2e/steps/02-ground-truth.md
git commit -m "feat(api-e2e): phase-2 ground-truth derivation step"
```

### Task 4: Create `steps/03-environment-gate.md`

**Files:**
- Create: `skills/api-tooling/api-e2e/steps/03-environment-gate.md`

**Interfaces:**
- Consumes: `fingerprint.md` (rung + assertion command), `deploy-model.md`, deploy preference from `run-context.md`.
- Produces: gate verdict appended to `run-context.md` (`## Environment gate: PASSED <timestamp, rung, evidence>`). Step 05 re-enters this file on mid-run flips.

- [ ] **Step 1: Write the file**

````markdown
# Phase 3 — Environment gate (both modes)

Verify the live environment is the build the run derived from. No matrix
executes before this gate passes. This phase is re-entered by phase 5
whenever a mid-run fingerprint flip is detected.

## Deployed mode

Verify the live build corresponds to the deployed ref recorded in the
interview, using the phase-2d ladder (build-identity endpoint, unique
read-observable behavior, or user-confirmed deploy evidence). On mismatch,
STOP and reconcile with the user — either re-derive phase 2 from the
correct ref or fix the environment. Never test against expectations
derived from a different commit.

## PR mode

Assert the fingerprint against the live environment. If it already
matches, record and proceed. If not:

1. **Prefer the user deploys.** If they provide a pipeline run URL,
   monitor it via whatever access preflight established (MCP tools, REST
   with PAT, or the user pasting status).
2. **If the user asks the skill to trigger the deploy:** first present the
   exact pipeline — name, id, project — derived from the repo's pipeline
   config, and get explicit confirmation it is the right one. Deployment
   variables are the user's to set; offer, don't insist.
3. **Regardless of who deploys, converge on the fingerprint:** poll until
   3 consecutive hits (default). This guards against canary analysis
   windows, promotion delays, and racing deploys silently replacing the
   build — trust the fingerprint, not the pipeline's "succeeded" status.
   Consult deploy-model.md for how long promotion is expected to take and
   pick a polling cadence that matches; report progress to the user while
   waiting.

## Gate

3 consecutive fingerprint passes (or, on rung 3, user-confirmed deploy
evidence recorded in the report). Append the verdict, timestamp, rung, and
evidence to run-context.md. No matrix executes before this.
````

- [ ] **Step 2: Validate**

Run: `python scripts/validate.py`
Expected: exit 0, `OK`

- [ ] **Step 3: Commit**

```bash
git add skills/api-tooling/api-e2e/steps/03-environment-gate.md
git commit -m "feat(api-e2e): phase-3 environment gate step"
```

### Task 5: Create `steps/04-matrix.md`

**Files:**
- Create: `skills/api-tooling/api-e2e/steps/04-matrix.md`

**Interfaces:**
- Consumes: `delta-map.md`, `no-touch.md`, `fingerprint.md`, data permissions from `run-context.md`.
- Produces: `matrix.md` (every row: `id | delta | category | tier | fixture needs | expected`), executable `scripts/matrix-<n>.sh`, and two user approvals recorded in `run-context.md` (`## Executed-tier approval`, `## Fixture-plan approval`). Step 05 executes the scripts; step 06 reads `matrix.md` for gap accounting.

- [ ] **Step 1: Write the file**

````markdown
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
````

- [ ] **Step 2: Validate**

Run: `python scripts/validate.py`
Expected: exit 0, `OK`

- [ ] **Step 3: Commit**

```bash
git add skills/api-tooling/api-e2e/steps/04-matrix.md
git commit -m "feat(api-e2e): phase-4 matrix derivation and gates step"
```

### Task 6: Create `steps/05-execute.md`

**Files:**
- Create: `skills/api-tooling/api-e2e/steps/05-execute.md`

**Interfaces:**
- Consumes: `scripts/matrix-<n>.sh`, `fingerprint.md` (flip semantics), `secrets/mint-<domain>.sh` (re-mint), phase-3 re-entry.
- Produces: `results/` captures + a **disposition ledger** appended to `matrix.md` (per FAIL: `check id | disposition 1-4 | evidence`). Step 06 consumes both.

- [ ] **Step 1: Write the file**

````markdown
# Phase 5 — Execution & triage

Run matrices SERIALLY — shared staging means concurrent probes corrupt
each other's fixtures. Capture everything to results/.

## The four-way FAIL disposition

Every FAIL must land in exactly one bucket, recorded in the disposition
ledger with evidence:

1. **Build defect** — deployed code deviates from the derived expectation.
   Report with reproduction (redaction happens at phase 6).
2. **Environment/fixture assumption wrong** — prove it by probing (e.g.,
   the slot was organically occupied), fix the fixture, rerun.
3. **Harness bug** — script/capture error; fix the script, rerun.
4. **Expectation mis-derived** — re-read the code, correct delta-map.md,
   rerun.

**Rule: a FAIL is not a build defect until the fixture assumption has been
verified live.** The build being right and your fixture being wrong looks
identical to a defect until you probe.

## Mid-run events

- **Token expiry** → re-mint from `secrets/mint-<domain>.sh`; resume.
- **Fingerprint flip** (racing deploy; on rung 3, a newer deploy record) →
  abort the current script, mark every check since the last passing
  fingerprint assertion as TAINTED, re-enter the phase-3 environment gate,
  and rerun tainted checks only after it passes again.
- **Newly required domain** (a witness read needs an uninterviewed
  domain) → phase-1 re-interview loop-back, then resume.

## Gate

Zero undispositioned FAILs. Every row in the executed tier is PASS,
dispositioned, or explicitly moved to the coverage-gap list with a reason.
````

- [ ] **Step 2: Validate**

Run: `python scripts/validate.py`
Expected: exit 0, `OK`

- [ ] **Step 3: Commit**

```bash
git add skills/api-tooling/api-e2e/steps/05-execute.md
git commit -m "feat(api-e2e): phase-5 execution and triage step"
```

### Task 7: Create `steps/06-report.md`

**Files:**
- Create: `skills/api-tooling/api-e2e/steps/06-report.md`

**Interfaces:**
- Consumes: `matrix.md` (rows + disposition ledger), `results/`, `fingerprint.md`, report destination from `run-context.md`.
- Produces: `{scratchpad}/api-e2e/report.md` (sanitized), delivered to the durable destination after user approval. Step 07's residual-state output is appended here before delivery — cleanup (07) runs BEFORE final delivery.

- [ ] **Step 1: Write the file**

````markdown
# Phase 6 — Report

Assemble `{scratchpad}/api-e2e/report.md`. Run phase 7 (cleanup) before
final delivery so the residual-state and cleanup-verification sections are
real, then deliver.

## Mandatory sections

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
````

- [ ] **Step 2: Validate**

Run: `python scripts/validate.py`
Expected: exit 0, `OK`

- [ ] **Step 3: Commit**

```bash
git add skills/api-tooling/api-e2e/steps/06-report.md
git commit -m "feat(api-e2e): phase-6 report step"
```

### Task 8: Create `steps/07-cleanup.md`

**Files:**
- Create: `skills/api-tooling/api-e2e/steps/07-cleanup.md`

**Interfaces:**
- Consumes: fixture ledger from `matrix.md` / `run-context.md` (what the run created), `no-touch.md`.
- Produces: residual-state + cleanup-verification sections for `report.md` (step 06 embeds them before delivery); optional memory writes; optional skill-text PR proposal presented to the user.

- [ ] **Step 1: Write the file**

````markdown
# Phase 7 — Cleanup & close-out

Runs before the report's final delivery so its output sections are real.

## Teardown

- Delete every run-created fixture. Verify each deletion **by
  observation** — re-read or enumerate the object and confirm it is gone
  or cancelled — never by trusting the delete's status code. Where the API
  soft-deletes, query with include-inactive flags to see the truth.
- Restore user-designated mutables to their interviewed state if the user
  asked for restoration.
- Re-read a sample of no-touch objects (from no-touch.md, including
  collection-level counts) and confirm they are untouched.
- Enumerate every unavoidable leftover into the report's residual-state
  section — exactly, with ids and final positions.

## Durable learnings (optional, per doctrine)

- **Local memory write:** if the run produced durable learnings (a fixture
  recipe, a platform quirk), offer to save them to the user's LOCAL
  per-user memory with provenance (date, run context). Scrub personally
  identifying fixture fields first, using the same rule phase 6 applies to
  the report. Never write run state to any repo.
- **Skill-text PR proposal:** if the run discovered a durable METHOD
  improvement (a better derivation technique, a new invariant category, a
  failure-triage pattern), draft the skill-text diff and present it to the
  user for approval. The skill never self-writes its own text.

## Gate

Cleanup verified by observation; report delivered (phase 6); any
method-improvement proposal presented. The run is complete only when all
three hold.
````

- [ ] **Step 2: Validate**

Run: `python scripts/validate.py`
Expected: exit 0, `OK`

- [ ] **Step 3: Commit**

```bash
git add skills/api-tooling/api-e2e/steps/07-cleanup.md
git commit -m "feat(api-e2e): phase-7 cleanup and close-out step"
```

---

## Phase B — Orchestrator + registration

### Task 9: Create `SKILL.md`

**Files:**
- Create: `skills/api-tooling/api-e2e/SKILL.md`

**Interfaces:**
- Consumes: all eight step files by relative reference (`steps/00-…` … `steps/07-…`) — the validator proves each reference resolves.
- Produces: the installable skill entry point (frontmatter `name: api-e2e` is what `/api-e2e` resolves to).

- [ ] **Step 1: Write the file**

````markdown
---
name: api-e2e
description: >
  Interview-driven, fresh-context staging E2E validation of a backend API —
  either an open PR (deploy + fingerprint + test) or an already-deployed
  endpoint. Derives an exhaustive wire-expectation map from the deployed
  repo head, gates on a build fingerprint, executes a risk-tiered test
  matrix with rollback verification and attribution proofs, triages every
  failure, and delivers a redacted report to a durable destination. Use
  when the user says "run e2e against PR #N", "e2e-validate this
  endpoint", "/api-e2e", or similar.
argument-hint: "[PR number / PR URL / endpoint description]"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent, AskUserQuestion, WebFetch, ToolSearch, TaskCreate, TaskUpdate
---

# api-e2e

Orchestrator. Read each step file when its phase begins — do not preload
them all. Run artifacts live under `{scratchpad}/api-e2e/`; create a task
per phase for progress tracking.

## Doctrine (non-negotiable, applies to every phase)

1. **Three information sources.** A run derives everything from exactly:
   (a) the deployed repository head, (b) live probing of the environment,
   (c) the user interview. Nothing else is authoritative.
2. **Memory policy.** Read local memories as HYPOTHESES only — every fact
   from memory is untrusted until re-verified live; memory never
   substitutes for repo-head derivation or pre-write probing. Write
   durable learnings to local per-user memory only, PII-scrubbed, with
   provenance. The repo and this skill's text carry zero run state, ever:
   no fixture inventories, testbed files, or environment profiles are
   committed anywhere. Reports go to a durable user-approved destination
   as OUTPUTS only — no future run reads a past report as authority.
   Method improvements become proposed skill-text PRs (phase 7), never
   self-written. Rationale: blast-radius containment first (a wrong shared
   fact would poison every teammate's runs; a wrong local memory is
   contained and verify-live corrects it), ensemble diversity second
   (independent fresh runs are nondeterministic in different ways — many
   runs out-cover any curated matrix).
3. **Method, zero environment facts.** This skill contains no service
   names, URLs, tenant numbers, IDs, or quirks — the interview and the
   repo head supply those per run.
4. **Never presume — interview.** Any missing capability, credential,
   permission, or fixture becomes a question to the user, including asking
   the user to create fixtures in domains not exposed to the run.
5. **Hard gates.** No test execution before the build fingerprint passes.
   No writes before the no-touch inventory exists and the fixture plan is
   user-approved. No run is complete without cleanup verification and the
   delivered report.
6. **Secrets are session-scoped.** Token-mint curls and credentials live
   in `{scratchpad}/api-e2e/secrets/` only — never in committed,
   persistent, or memory files, and never in the report.

## Phase sequence

| # | Phase | File | Exit gate |
|---|---|---|---|
| 0 | Preflight | [steps/00-preflight.md](steps/00-preflight.md) | Capability table complete (tool or user-mediated fallback per need) |
| 1 | Interview | [steps/01-interview.md](steps/01-interview.md) | Verified token per known domain; mode/target/permissions explicit |
| 2 | Ground truth | [steps/02-ground-truth.md](steps/02-ground-truth.md) | Delta map, no-touch inventory, deploy model, fingerprint — all repo-head-traceable |
| 3 | Environment gate | [steps/03-environment-gate.md](steps/03-environment-gate.md) | 3 consecutive fingerprint passes (rung-3: user-confirmed evidence, recorded) |
| 4 | Matrix & scripting | [steps/04-matrix.md](steps/04-matrix.md) | Executed tier approved (all modes); fixture plan approved (when writes exist) |
| 5 | Execution & triage | [steps/05-execute.md](steps/05-execute.md) | Zero undispositioned FAILs |
| 6 | Report | [steps/06-report.md](steps/06-report.md) | Redacted report user-approved and delivered to the durable destination |
| 7 | Cleanup | [steps/07-cleanup.md](steps/07-cleanup.md) | Cleanup verified by observation; method-improvement proposal presented if any |

Phases run in order. Two sanctioned loop-backs: any phase may re-enter
phase 1 for a newly discovered domain (token + permissions only), and
phase 5 re-enters phase 3 on a fingerprint flip. Phase 7 executes before
phase 6's final delivery so residual-state and cleanup-verification
sections are real; the gates still both apply.

## Modes

- **PR mode:** validate an open PR. Phase 3 includes deploy orchestration
  (prefer user-run deploys; confirm pipeline identity before triggering).
- **Deployed mode:** validate what is already live against the deployed
  ref the interview collects. Phase 3 verifies identity only.
- **Read-only degradation:** when data-permission answers are missing, the
  run proceeds with safe verbs only (expected-rejection probes count as
  writes) and records all write coverage as gaps — with an explicit
  proceed-or-defer checkpoint when the delta is predominantly
  write-dependent.

## Fan-out threshold

When the phase-2 delta map contains 10 or more wire-observable deltas
(default; interview may override either way), fan out per-category
derivation subagents in phases 2a/4 and reconcile. Below the threshold,
derive inline.

## Failure posture

A FAIL is never reported as a build defect until the fixture assumption
has been verified live (phase 5's four-way disposition). Two "failures"
that turn out to be the build being right are positive evidence — report
them as such.
````

- [ ] **Step 2: Validate (proves all eight step references resolve)**

Run: `python scripts/validate.py`
Expected: exit 0, `OK`

- [ ] **Step 3: Commit**

```bash
git add skills/api-tooling/api-e2e/SKILL.md
git commit -m "feat(api-e2e): orchestrator SKILL.md"
```

### Task 10: Register the skill + record the resolved open question

**Files:**
- Modify: `README.md` (Skills table + Installation block)
- Modify: `docs/superpowers/specs/2026-07-10-api-e2e-skill-design.md` (Deferred / Open Questions section)

- [ ] **Step 1: Add the README Skills-table row**

In `README.md`, after the `design-coverage-scout` row of the Skills table, add:

```markdown
| [`api-e2e`](./skills/api-tooling/api-e2e/SKILL.md) | Interview-driven, fresh-context staging E2E validation of a backend API PR or deployed endpoint: repo-head-derived expectations, build fingerprinting, risk-tiered matrix, four-way failure triage, redacted durable report. |
```

- [ ] **Step 2: Add the installation symlink lines**

In `README.md`, append to the symlink block:

```bash
ln -s "$PWD/skills/api-tooling/api-e2e"                  "$HOME/.claude/skills/api-e2e"
```

and to the Windows copy block:

```bash
cp -r skills/api-tooling/api-e2e                  "$HOME/.claude/skills/api-e2e"
```

- [ ] **Step 3: Record the fan-out resolution in the spec**

In `docs/superpowers/specs/2026-07-10-api-e2e-skill-design.md`, append to the
"Subagent fan-out threshold" bullet under `### From 2026-07-10 review`:

```markdown
  **Resolved (implementation plan, 2026-07-10):** fixed default in the
  skill text — fan out when the phase-2 delta map contains ≥ 10
  wire-observable deltas; the interview may override in either direction.
```

- [ ] **Step 4: Full validation**

Run: `python scripts/validate.py`
Expected: exit 0, `OK`

- [ ] **Step 5: Commit**

```bash
git add README.md docs/superpowers/specs/2026-07-10-api-e2e-skill-design.md
git commit -m "feat(api-e2e): register skill in README; resolve fan-out threshold open question"
```

---

## Post-plan (not tasks — noted for the humans)

- Symlink/copy the skill into `~/.claude/skills/` and restart the session to expose `/api-e2e`.
- Spec acceptance criterion 1 (replay with induced fingerprint refusal + seeded harness bug) and criterion 2 (transfer run by a method-naive teammate) are manual exercises after merge.
- Per the repo's workflow memory: run `/simplify` before raising the PR, then pr-autopilot for the PR loop.
