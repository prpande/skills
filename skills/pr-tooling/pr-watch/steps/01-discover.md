# Step 01 — Discover, baseline, confirm, initialise

Runs on `/pr-watch [pr-number ...]`. Writes `watch.json` and one library
state file per authored PR. Posts nothing anywhere.

## 1. Record the fixed values

Run each command on its own and keep its output:

- `git worktree list --porcelain` → `MAIN` is the path on the first
  `worktree` line; `STATE_DIR` is `<MAIN>/.pr-autopilot`.
- `git rev-parse --show-toplevel` → `ORIGIN`, the worktree the session is
  in now.
- `gh repo view --json nameWithOwner --jq .nameWithOwner` → `SLUG`.
- `gh api user --jq .login` → `SELF`. A failure here means `gh` is not
  authenticated: stop and tell the user to run `gh auth login`.

Make sure `.pr-autopilot/` is ignored: run
`git -C <MAIN> check-ignore -q .pr-autopilot/probe`. On a non-zero exit,
append the line `.pr-autopilot/` to `<git -C <MAIN> rev-parse --git-common-dir>/info/exclude`.
Never edit `.gitignore`.

## 2. Resume or start

If `<STATE_DIR>/watch.json` exists and its `dry_run` is `true` and this
invocation is not `--dry-run`: a dry run is never resumed by a real one.
Delete `watch.json`, `watch-poller.json`, and `watch-seen.json`, and
start from an empty set exactly as a first run (its baseline applies to
every PR added below).

Otherwise, if `<STATE_DIR>/watch.json` exists, read it. Its PRs are the
starting set, their id lists are kept, and discovery below only adds to
it. Set `session_id` to a fresh UUID
(`python -c "import uuid; print(uuid.uuid4())"`); the library lock
protocol reclaims stale locks from the old session.

Otherwise start from an empty set with a fresh `session_id`.

## 3. Discover

Authored PRs with a worktree:

- `gh pr list --repo <SLUG> --author @me --state open --limit 100 --json number,title,url,headRefName`
- `git -C <MAIN> worktree list --porcelain` → map each `branch refs/heads/<name>`
  line to the `worktree` path above it.
- A PR whose `headRefName` has a worktree joins the set as `authored` with
  that path. A PR without one is listed as excluded in the confirmation.

Reviewed PRs:

- `gh api -i -X GET search/issues -f q="repo:<SLUG> is:pr is:open reviewed-by:<SELF> -author:<SELF>" -f per_page=100`.
  If the response headers contain `X-GitHub-SSO: partial-results`, stop:
  the token is not SSO-authorised for this org and results are silently
  incomplete. Tell the user to authorise it.
- Each result joins the set as `reviewed` if, after step 5 writes
  `watch.json`, `POLL --findings <N> --state-dir <STATE_DIR>` shows at
  least one thread. Otherwise drop it.

Explicit numbers from the invocation join the set. For each, read the
live author with `gh pr view <N> --repo <SLUG> --json author,title,url,headRefName`;
the role is `authored` when the author is `SELF`, else `reviewed`. An
explicit authored PR with no worktree gets one:

```
git -C <MAIN> fetch origin <headRefName>
git -C <MAIN> worktree add <MAIN>/.claude/worktrees/<headRefName> <headRefName>
```

If the local branch does not exist, the second command is
`git -C <MAIN> worktree add -b <headRefName> <MAIN>/.claude/worktrees/<headRefName> origin/<headRefName>`.

A PR number the user only mentioned in conversation is never added.

## 4. Write `watch.json`

Write it per `pr-watch/references/watch-state-schema.md` "Writing", with
`channel_id` from `--channel` or `C0C15VC8Y0Z`, `serialize_pushes`
`false` only under `--parallel-pushes`, `dry_run` from `--dry-run`,
`origin_worktree` = `ORIGIN`, `bot_allowlist`
`["sonarqube-mbodevme", "mindbody-ado-pipelines", "mergewatch-playlist"]`
(kept as is on resume), and each new PR with empty id lists and objects
(including `ci_reruns`, `ci_rerun_queued`, `ci_handled`, and
`finding_verdicts`) and `slack_ts: null`.

## 5. Baseline new authored PRs

For every `authored` PR added in this run (not resumed ones):
`POLL --baseline <N> --state-dir <STATE_DIR>`. Merge its `settled_ids` and
`handled_top_level_ids` into the PR's entry and rewrite `watch.json`.

## 6. Confirm

For each PR run `POLL --tails <N>` (authored) or `POLL --findings <N>`
(reviewed), both with `--state-dir <STATE_DIR>`. Show one table:

| PR | Role | Title | Worktree | What the first event will act on |
|---|---|---|---|---|

For authored PRs the last column is the pending thread and top-level
counts. For reviewed PRs it is "head moved past your review" or "waiting
for a push". Under the table list the excluded authored PRs and why.

Ask with `AskUserQuestion`: "Watch these PRs?" with options "Watch them"
and "Change the set". On "Change the set", take the changes in plain text,
apply them to `watch.json`, and ask again.

## 7. Initialise the library state for authored PRs

For each `authored` PR whose `<worktree>/.pr-autopilot/pr-<N>.json` does
not exist, create it with exactly these keys (the library schema forbids
others):

```json
{
  "session_id": "<watch.json session_id>",
  "host_platform": "claude-code",
  "platform": "github",
  "repo_root": "<worktree>",
  "base": "<baseRefName>",
  "branch": "<headRefName>",
  "head_sha": "<headRefOid>",
  "base_sha": "<git -C <worktree> merge-base origin/<baseRefName> HEAD>",
  "pr_number": <N>,
  "pr_url": "<url>",
  "self_login": "<SELF>"
}
```

Use the tmp-then-rename write. An existing file (from a `pr-autopilot`
run) is left as it is; the lock protocol updates its `session_id` when it
reclaims.

Then go to `pr-watch/steps/02-arm-monitor.md`.
