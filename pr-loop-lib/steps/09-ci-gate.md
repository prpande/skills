# Loop step 09 — CI gate

Wait for CI to finish, report status. Only entered when step 08 exits
quiescent (not on cap/runaway).

## GitHub

```bash
gh pr checks "$PR" --watch --fail-fast=false
```

Blocks until every reported check has a terminal status. Then collect:

```bash
gh pr checks "$PR" --json name,state,link,bucket,completedAt \
  --jq '[.[] | {name, state, link, bucket, completedAt}]'
```

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
  state: green|red,
  link: <URL>,
  raw_state: <platform-specific terminal value>,
  extra: {...}  // e.g., pipeline_id for AzDO, bucket for GitHub
}
```

## Routing

- All green → proceed to step 11 (final report) with
  `context.termination_reason = "ci-green"`.
- Any red → proceed to step 10 (classify + possibly re-enter the loop).

## Timeout

If the CI gate takes longer than 30 minutes (total wall-clock), stop
watching, record the still-pending checks as
`state: "pending-timeout"` in `context.ci_results`, and proceed to step 11
with `context.termination_reason = "ci-timeout"`. Do not re-enter.
