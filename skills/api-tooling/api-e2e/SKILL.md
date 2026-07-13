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
them all. Run artifacts live under `{scratchpad}/api-e2e/`. `{scratchpad}`
is this session's private scratchpad/temp directory — never a repo path,
never a shared temp dir. Resolve it to an absolute path once in phase 0 and
substitute it in every command that mentions it. Create a task per phase for
progress tracking.

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
3. **Method, zero environment facts.** This skill contains no
   target-environment service names, URLs, tenant numbers, IDs, or quirks —
   the interview and the repo head supply those per run; generic vendor-tool
   examples (`gh`, `az`, an MCP server name) that illustrate probing are
   fine.
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
| 0 | Preflight | [`steps/00-preflight.md`](steps/00-preflight.md) | Capability table complete (tool or user-mediated fallback per need) |
| 1 | Interview | [`steps/01-interview.md`](steps/01-interview.md) | Verified token per known domain; mode/target/permissions explicit |
| 2 | Ground truth | [`steps/02-ground-truth.md`](steps/02-ground-truth.md) | Delta map, no-touch inventory, deploy model, fingerprint — all repo-head-traceable |
| 3 | Environment gate | [`steps/03-environment-gate.md`](steps/03-environment-gate.md) | 3 consecutive fingerprint passes (rung-3: user-confirmed evidence, recorded) |
| 4 | Matrix & scripting | [`steps/04-matrix.md`](steps/04-matrix.md) | Executed tier approved (all modes); fixture plan approved (when writes exist) |
| 5 | Execution & triage | [`steps/05-execute.md`](steps/05-execute.md) | Zero undispositioned FAILs |
| 6 | Report | [`steps/06-report.md`](steps/06-report.md) | Redacted report user-approved and delivered to the durable destination |
| 7 | Cleanup | [`steps/07-cleanup.md`](steps/07-cleanup.md) | Cleanup verified by observation; sections handed to phase 6; method-improvement proposal presented if any |

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

At 10 or more wire-observable deltas (default; interview may override
either way), fan out derivation subagents and reconcile — per effect class
in phase 2a (once the running delta count reaches the threshold) and per
invariant category in phase 4. Below the threshold, derive inline.

## Failure posture

A FAIL is never reported as a build defect until the fixture assumption
has been verified live (phase 5's four-way disposition). Two "failures"
that turn out to be the build being right are positive evidence — report
them as such.
