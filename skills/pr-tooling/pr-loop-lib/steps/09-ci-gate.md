# Loop step 09 — CI gate

Wait for CI to finish, report status. Only entered when step 08 exits
quiescent (not on cap/runaway).

## Stacked base

Runs at step entry, before the platform collection below. The default branch is read as in pr-autopilot step 04. The subsections run in this order:

1. Live base.
2. Merged base (pr-followup only). When it pushes, it ends this pass of step 09: see its step 5.
3. The platform collection below (GitHub, Azure DevOps).
4. Required checks: append the `missing` entries.
5. Gated workflows: dispatch, then re-collect the checks.
6. Routing.

### Head check

Merged base and Gated workflows act on the checkout's HEAD, so each first runs this check. Read the PR's head: `gh pr view <N> --json headRefName,headRefOid` (AzDO: `az repos pr show --id <N> --query "{ref: sourceRefName, sha: lastMergeSourceCommit.commitId}"`, strip `refs/heads/` from the ref). The check passes when `git rev-parse --abbrev-ref HEAD` equals the head branch name and `git rev-parse HEAD` equals the head commit.

On a mismatch, the section does nothing else: add a `needs_human_items` entry `{feedback_id: "stacked-base", reason}` naming the checkout's branch and commit and the PR's head branch and commit, and keep the `missing` entries. Add that entry once per pass of step 09, even when both sections run the check.

### Live base

`gh pr view <N> --json baseRefName --jq .baseRefName` (AzDO: `az repos pr show --id <N> --query targetRefName -o tsv`, strip `refs/heads/`). When it differs from `context.base`: log `base_changed {from, to}`, set `context.base`, recompute `context.base_sha` as step 01 does (`git fetch origin <base>`, then `git merge-base origin/<base> HEAD`), set `context.base_changed_in_run = true` and write state. When the running skill is pr-followup and the base changed, run "Merged base" below. pr-autopilot never runs "Merged base"; it follows the changed base and its report says to run pr-followup.

### Merged base (pr-followup only)

Runs when `context.merged_base_done` is false and one of these holds:

1. `context.base` is not the default branch and the base is merged. The base is merged when, after `git fetch origin <base>`, `gh pr list --head <base> --state merged --json number,headRefOid,baseRefName --jq '[.[] | select(.baseRefName == "<default>")] | .[0]'` prints a PR whose `headRefOid` equals `git rev-parse origin/<base>`. A PR merged into any other branch does not count.
2. `context.base_changed_in_run` is true and `context.base` is the default branch.
3. `context.base` is the default branch and the first line of the PR body starts with "Stacked on " (`gh pr view <N> --json body --jq .body`; AzDO: `az repos pr show --id <N> --query description -o tsv`). That line is the marker that Merged base has not run; removing it in step 1 is the done mark across runs.

Run "Head check" first. On a pass, set `context.merged_base_done = true` and write state; this holds whatever the outcome, so a later pass of step 09 skips Merged base.

Under `--dry-run`, print the retarget, body edit, merge and push commands below, perform none of them, and continue with the gate.

1. When the PR still targets the merged base, retarget it: `gh pr edit <N> --base <default>` (AzDO: `az repos pr update --id <N> --target-branch <default>`), log `retargeted`, set `context.base_changed_in_run = true` and write state. When the command exits non-zero, stop Merged base before the body edit: add a `needs_human_items` entry `{feedback_id: "stacked-base", reason}` with the first stderr line, and end with `context.termination_reason = "user-intervention-needed"`.

   Whenever Merged base runs, retargeted by this step or by the platform, remove the PR body's first line when it starts with "Stacked on ": `gh pr view <N> --json body --jq .body`, write the rest to a temp file, `gh pr edit <N> --body-file <file>` (AzDO: read with `az repos pr show --id <N> --query description -o tsv`, write with `az repos pr update --id <N> --description`).
2. `git fetch origin <default>`. When `origin/<default>` is an ancestor of HEAD, no merge commit is made: update `base` and `base_sha` and continue with the gate; steps 3 to 5 do not apply. Otherwise `git status --porcelain` must print nothing; when it prints a path, add a `needs_human_items` entry naming the dirty paths and end with `user-intervention-needed`. Then `git merge --no-edit origin/<default>`. Never rebase, never force-push.
3. A `git merge` that exits non-zero with no `MERGE_HEAD` (no conflict) adds a `needs_human_items` entry with its first stderr line and ends with `user-intervention-needed`. On a conflict (`MERGE_HEAD` exists), run `git merge --abort`, add a `needs_human_items` entry naming the conflicting paths and saying the PR is already retargeted, and end with `user-intervention-needed`.
4. Otherwise run the build and test commands detected by "Command detection" in `pr-loop-lib/steps/04.5-local-verify.md`, under its "Execution rules" and "Local suites". Do not invoke 04.5 as a step: its skip condition does not apply here. On failure, `git reset --keep ORIG_HEAD` to drop the unpushed merge commit from step 2, add a `needs_human_items` entry with the failing command and its first error line, saying the PR is already retargeted, and end with `user-intervention-needed`.
5. On pass, `git push origin HEAD`. When the push fails, add a `needs_human_items` entry with the first stderr line and end with `user-intervention-needed`. Otherwise update `base`, `base_sha`, `head_sha` and `last_push_sha`, set `last_push_timestamp` to the epoch from `git log -1 --format=%ct`, write state and go to loop step 01 (wait cycle), as step 06 does after its push. Do not continue this pass of step 09.

Every `needs_human_items` entry from steps 2 to 5 also says to merge `origin/<default>` into the branch by hand and push: the "Stacked on " line is already removed, so a later run does not retry Merged base.

### Required checks

Runs when `context.base` is not the default branch, when `context.base_changed_in_run` is true, or when the PR's timeline has a retarget event (GitHub only): `gh api repos/<owner>/<repo>/issues/<N>/timeline --paginate --jq '.[] | select(.event == "base_ref_changed" or .event == "automatic_base_change_succeeded") | .event'` prints any line. GitHub retargets a rung to the default branch when the lower rung's branch is deleted on merge, and that does not start a `pull_request` run. Otherwise skip this section.

The required check names are the default branch's, not the live base's. `<default>` in the API paths is URL-encoded (`release/1` is `release%2F1`).

- GitHub: the union of the ruleset names and the classic protection names. A 404 from the rules call means no names from it; a 403 or 404 ("Must have admin rights") from the classic protection call means no names from it. Any other error ends the gate with `context.termination_reason = "user-intervention-needed"` and a `needs_human_items` entry `{feedback_id: "stacked-base", reason}` carrying the failing call and its first error line; it never routes to `ci-green`.

  ```bash
  gh api repos/<owner>/<repo>/rules/branches/<default> --paginate \
    --jq '.[] | select(.type == "required_status_checks") | .parameters.required_status_checks[].context'
  gh api repos/<owner>/<repo>/branches/<default>/protection/required_status_checks --jq '.contexts[]'
  ```

  Names match check-run names.
- Azure DevOps: no dispatch. Get the repository id with `az repos show --repository <repo> --query id -o tsv`, then `az repos policy list --repository-id <repo id> --branch <default>`. Each enabled Build policy needs a completed run of its pipeline for the PR: `az pipelines runs list --branch refs/pull/<N>/merge --pipeline-ids <id>` lists one with status `completed` that started after the head commit's push. Each without one is missing. An error from these calls ends the gate as in the GitHub bullet.

After the collection below and before Routing, every required name with no check on the head is appended to `context.ci_results` as `{name, state: "missing", link: null, raw_state: null, extra: {}}`. No required names: nothing is appended. Routing sees the appended entries, so required names plus an empty collection route to `ci-unchecked`, not `ci-skipped`.

### Gated workflows

Runs only on GitHub, and only when a required check is missing. Run "Head check" first; on a mismatch, dispatch nothing. Gated workflows are the `.github/workflows/*.yml` and `*.yaml` files at `context.head_sha` where all of these hold:

- `on.pull_request` (or `pull_request_target`) runs for PRs into the default branch: its `branches` filter matches the default branch, or it has no `branches` filter and its `branches-ignore` does not match it.
- The file declares `workflow_dispatch`, and every input with `required: true` has a `default`.
- The head commit has no run of it: `gh run list --workflow <file> --commit <head_sha> --json databaseId --limit 1` prints `[]`.

For each such file whose `<head_sha>|<file>` is not in `context.ci_dispatched`:

1. Append `<head_sha>|<file>` to `context.ci_dispatched` and write state.
2. `gh workflow run <file> --ref <headRefName>`, the PR's head branch from "Head check". When it exits non-zero, remove that `<head_sha>|<file>` key from `context.ci_dispatched`, write state, and add a `needs_human_items` entry `{feedback_id: "stacked-base", reason}` with its first stderr line, for step 11.

Under `--dry-run`, print the `gh workflow run` command for each file and do neither step, so a later real run still dispatches.

Then find each run: `gh run list --workflow <file> --commit <head_sha> --event workflow_dispatch --json databaseId,status --limit 1`, polling every 15 seconds for up to 2 minutes. Wait with `gh run watch <id> --interval 15 --exit-status >/dev/null 2>&1 || true`, inside the step's 30-minute budget. Then re-collect the checks and recompute `missing` once. Under `--dry-run` nothing is dispatched, so skip this lookup and keep the `missing` entries.

A dispatch recorded for this head is never repeated. When nothing is selectable or the run never appears, the `missing` entries stay.

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
  `context.termination_reason = "ci-unchecked"`, also when a `pending-timeout`
  entry is present; step 11's per-check breakdown lists those checks too. A
  red check still goes to step 10 first.
- All green → proceed to step 11 (final report) with
  `context.termination_reason = "ci-green"`.
- Any red → proceed to step 10 (classify + possibly re-enter the loop).
- Any `pending-timeout` (with no red and no `missing` checks) → proceed to step 11 with
  `context.termination_reason = "ci-timeout"`.

## Timeout

If the CI gate takes longer than 30 minutes (total wall-clock), stop
watching, record the still-pending checks as
`state: "pending-timeout"` in `context.ci_results`, and proceed to step 11
with `context.termination_reason = "ci-timeout"`, or `"ci-unchecked"` when a `missing` entry exists and no check is red (see Routing). A red check still goes to step 10 first. Do not re-enter.
