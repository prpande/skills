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

## Collect (in order; append each answer to `{scratchpad}/api-e2e/run-context.md`)

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
