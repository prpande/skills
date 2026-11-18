# Loop step 09 — CI gate

Wait for CI to finish, report status. Only entered when step 08 exits
quiescent (not on cap/runaway).

## Stacked base

Runs at step entry, before the platform collection below. The default branch is read as in pr-autopilot step 04.

### Live base

`gh pr view <N> --json baseRefName --jq .baseRefName` (AzDO: `az repos pr show --id <N> --query targetRefName -o tsv`, strip `refs/heads/`). When it differs from `context.base`: log `base_changed {from, to}`, set `context.base`, recompute `context.base_sha` as step 01 does (`git fetch origin <base>`, then `git merge-base origin/<base> HEAD`), and remember that the base changed in this run. When the running skill is pr-followup and the base changed, run "Merged base" below. pr-autopilot never runs "Merged base"; it follows the changed base and its report says to run pr-followup.

### Required checks

Runs when `context.base` is not the default branch, or when the base changed in this run (GitHub retargets a rung to the default branch when the lower rung's branch is deleted on merge, and that does not start a `pull_request` run). Otherwise skip this section.

The required check names are the default branch's, not the live base's.

- GitHub: the union of the ruleset names and the classic protection names. A 404 from either source means no names from it.

  ```bash
  gh api repos/<owner>/<repo>/rules/branches/<default> --paginate \
    --jq '.[] | select(.type == "required_status_checks") | .parameters.required_status_checks[].context'
  gh api repos/<owner>/<repo>/branches/<default>/protection/required_status_checks --jq '.contexts[]'
  ```

  Names match check-run names.
- Azure DevOps: no dispatch. `az repos policy list --branch <default>`; each enabled Build policy needs a completed run of its pipeline for the PR's source commit. Each without one is missing.

After the collection below, every required name with no check on the head is appended to `context.ci_results` as `{name, state: "missing", link: null, raw_state: null, extra: {}}`. No required names: nothing is appended.

### Gated workflows

Runs only on GitHub, and only when a required check is missing. Gated workflows are the `.github/workflows/*.yml` and `*.yaml` files at `context.head_sha` where all of these hold:

- `on.pull_request` (or `pull_request_target`) has a `branches` filter that does not match `context.base`, or a `branches-ignore` filter that does.
- The file declares `workflow_dispatch`, and every input with `required: true` has a `default`.

For each such file whose `<head_sha>|<file>` is not in `context.ci_dispatched`:

1. Append `<head_sha>|<file>` to `context.ci_dispatched` and write state.
2. `gh workflow run <file> --ref <context.branch>`. Under `--dry-run`, print the command instead.

Then find each run: `gh run list --workflow <file> --commit <head_sha> --event workflow_dispatch --json databaseId,status --limit 1`, polling every 15 seconds for up to 2 minutes. Wait with `gh run watch <id> --exit-status >/dev/null 2>&1 || true`, inside the step's 30-minute budget. Then re-collect the checks and recompute `missing` once.

A dispatch recorded for this head is never repeated. When nothing is selectable or the run never appears, the `missing` entries stay.

### Merged base (pr-followup only)

Runs when `context.base` is not the default branch and `gh pr list --head <base> --state merged --json number --jq '.[0].number'` prints a number, or when the base changed in this run to the default branch.

1. When the PR still targets the merged base, retarget it: `gh pr edit <N> --base <default>` (AzDO: `az repos pr update --id <N> --target-branch <default>`) and log `retargeted`.
2. `git fetch origin <default>`. When `origin/<default>` is not an ancestor of HEAD, `git merge --no-edit origin/<default>`. Never rebase, never force-push.
3. On a conflict, `git merge --abort` and end with `context.termination_reason = "user-intervention-needed"` naming the conflicting paths.
4. Otherwise run the build and test commands of `pr-loop-lib/steps/04.5-local-verify.md`. On failure, `git reset --keep ORIG_HEAD` to drop the unpushed merge commit and end with `user-intervention-needed`.
5. On pass, plain `git push`; update `base`, `base_sha`, `head_sha`, `last_push_sha` and `last_push_timestamp`; restart step 09 from the top. The push starts the PR's own CI.

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
  state: green | red | pending-timeout | missing,
  link: <URL>,
  raw_state: <platform-specific terminal value>,
  extra: {...}  // e.g., pipeline_id for AzDO, bucket for GitHub
}
```

The four state values have distinct meanings:
- `green` — check reported success.
- `red` — check reported failure (any non-success terminal state on the
  platform).
- `pending-timeout` — check never reached a terminal state within the
  skill's timeout window. Step 10 does NOT classify these; step 11
  reports them alongside the per-check breakdown so the user knows the
  gate was abandoned, not failed.
- `missing` — a check the default branch requires has no run on the
  head (see "Stacked base"). Step 10 skips these.

## Routing

- `context.ci_results` is **empty** after detection (GitHub: `gh pr
  checks` returned no checks; AzDO: no pipeline runs associated with
  this PR within the lookback window) → no CI is configured for this
  repo. Proceed to step 11 with
  `context.termination_reason = "ci-skipped"`. Do NOT treat as
  vacuously-green — that misleads the operator.
- Any `missing` and no red → proceed to step 11 with
  `context.termination_reason = "ci-unchecked"`. A red check still goes to
  step 10 first.
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
