# Loop step 09 — CI gate

Wait for CI to finish, report status. Only entered when step 08 exits
quiescent (not on cap/runaway).

## GitHub

```bash
# The --watch form exits non-zero if ANY check finishes red. We need the
# skill to continue into step 10 (classify) in that case, so capture the
# exit status instead of letting it propagate as a hard failure:
gh pr checks "$PR" --watch --fail-fast=false >/dev/null 2>&1 || true

# Then collect the final per-check status unconditionally:
gh pr checks "$PR" --json name,state,link,bucket,completedAt \
  --jq '[.[] | {name, state, link, bucket, completedAt}]'
```

The `|| true` is intentional — a non-zero from `--watch` means "some check
ended red", which is exactly the branch step 10 handles. Letting the exit
code abort the orchestrator would skip classification entirely. The
`--json` follow-up query is the authoritative source for
`context.ci_results`; the `--watch` call is used only for its blocking
behavior.

## Azure DevOps

Poll `az pipelines runs list` until the latest run per pipeline is in a
terminal state (`completed`). Terminal status comes from the `result` field:

- `succeeded` — green
- `failed` | `canceled` | `partiallySucceeded` — red

Collect one record per pipeline: `{name, result, link, pipeline_id}`.

## Output

Populate `context.ci_results` as a list of:
```
{ name: <check/pipeline name>,
  state: green | red | pending-timeout,
  link: <URL>,
  raw_state: <platform-specific terminal value>,
  extra: {...}  // e.g., pipeline_id for AzDO, bucket for GitHub
}
```

The three state values have distinct meanings:
- `green` — check reported success.
- `red` — check reported failure (any non-success terminal state on the
  platform).
- `pending-timeout` — check never reached a terminal state within the
  skill's timeout window. Step 10 does NOT classify these; step 11
  reports them alongside the per-check breakdown so the user knows the
  gate was abandoned, not failed.

## Routing

- All green → proceed to step 11 (final report) with
  `context.termination_reason = "ci-green"`.
- Any red → proceed to step 10 (classify + possibly re-enter the loop).
- Any `pending-timeout` (with no red checks) → proceed to step 11 with
  `context.termination_reason = "ci-timeout"`.

## Timeout

If the CI gate takes longer than 30 minutes (total wall-clock), stop
watching, record the still-pending checks as
`state: "pending-timeout"` in `context.ci_results`, and proceed to step 11
with `context.termination_reason = "ci-timeout"`. Do not re-enter.
