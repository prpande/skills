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
