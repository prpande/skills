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

If this invocation is `--dry-run` and `<STATE_DIR>/watch.json` exists
with `dry_run` other than `true`: stop and tell the user a real watch
exists here; a dry run needs it stopped (`/pr-watch stop`) and its state
files (`watch.json`, `watch-poller.json`, `watch-seen.json`) moved aside
first. Write nothing.

The heartbeat check, used twice below: run
`python -c "import sys, time; print(int(time.time()) - int(open(sys.argv[1]).read()))" "<STATE_DIR>/watch-heartbeat"`.
The heartbeat is fresh when it prints a number below 300. A larger
number, or a non-zero exit (no heartbeat file), is not fresh.

If `<STATE_DIR>/watch.json` exists and its `dry_run` is `true` and this
invocation is not `--dry-run`: a dry run is never resumed by a real one.
If this session has no running monitor for that watch and the heartbeat
is fresh, stop and tell the user a dry-run watch is still running here
and must be stopped (`/pr-watch stop` in its session) first; delete
nothing. Otherwise delete `watch.json`, `watch-poller.json`, and
`watch-seen.json`, and start from an empty set exactly as a first run
(its baseline applies to every PR added below).

Otherwise, if `<STATE_DIR>/watch.json` exists, read it. Its PRs are the
starting set, their id lists are kept, and discovery below only adds to
it. Then:

- This session already has a running monitor for this watch: keep the
  existing `session_id`.
- This session has no running monitor for this watch and the heartbeat
  is fresh: stop and tell the user a watch was active in this repo in
  the last five minutes; if it runs in another session, run
  `/pr-watch stop` there; either way, wait five minutes and retry.
- Otherwise set `session_id` to a fresh UUID
  (`python -c "import uuid; print(uuid.uuid4())"`); the library lock
  protocol reclaims stale locks from the old session.

Otherwise start from an empty set with a fresh `session_id`.

## 3. Discover

Authored PRs with a worktree:

- `gh pr list --repo <SLUG> --author '@me' --state open --limit 100 --json number,title,url,headRefName`.
  The quotes around `@me` are load-bearing in PowerShell: bare, the shell
  eats the next flag and `gh` fails with `unknown argument "open"`.
- `git -C <MAIN> worktree list --porcelain` → map each `branch refs/heads/<name>`
  line to the `worktree` path above it.
- A PR whose `headRefName` has a worktree joins the set as `authored` with
  that path. A PR without one is listed as excluded in the confirmation.

Reviewed PRs:

- `gh api -i -X GET search/issues -f q="repo:<SLUG> is:pr is:open reviewed-by:<SELF> -author:<SELF>" -f per_page=100`.
  If the response headers contain `X-GitHub-SSO: partial-results`, stop:
  the token is not SSO-authorised for this org and results are silently
  incomplete. Tell the user to authorise it.
- Each result joins the set as `reviewed`. A result already in the
  starting set from a resume is never removed by this bullet; only a
  newly discovered one is checked. For a newly discovered one, after
  step 5 writes `watch.json`, run `POLL --findings <N> --state-dir
  <STATE_DIR>`. Remove it from `watch.json` when every thread is
  `is_resolved: true` and every comment after the user's last comment on
  it (the entries after the last `me` in `kinds`) has its id in
  `escalated_ids` (empty for a new PR, so any such comment keeps it) —
  03 D step 1's settle condition, meaning nothing is left to watch. When
  that command exits non-zero, remove the PR from `watch.json` too and
  list it among the excluded PRs in step 6 with the command's stderr
  line.

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
(kept as is on resume), and `ado_orgs` `["mindbody"]`. On resume,
`ado_orgs` is written as `["mindbody"]` only when the key is missing; any
other existing value is kept as is.

Each new PR starts with `posted_reply_ids`, `settled_ids`, and
`escalated_ids` as `[]`, `handled_top_level_ids` as `{}`, and `slack_ts`
as `null`. A new `authored` PR also starts with:

- `ci_reruns`, `ci_rerun_queued`, `ci_handled`, and `ci_log_retries` as `[]`;
- `ci_fix_pushes` and `review_fix_pushes` as `0`;
- `last_pushed_head`, `queued_head`, `queued_at`, `wait_notice_at`,
  `retry_after`, and `skip_reason` as `null`.

A new `reviewed` PR also starts with `finding_verdicts` as `{}`, and
`rereviewed_head` and `retry_after` as `null`. On resume, a PR entry missing any key this
section lists for its role gets it with that starting value; every key
it already has is kept.

## 5. Baseline new authored PRs

For every `authored` PR added in this run (not resumed ones):
`POLL --baseline <N> --state-dir <STATE_DIR>`. Merge its `settled_ids` and
`handled_top_level_ids` into the PR's entry and rewrite `watch.json`.
When it exits non-zero, remove the PR from `watch.json`, list it among
the excluded PRs in step 6 with the command's stderr line, and go on
with the other PRs. A PR left in without its baseline would be resumed
next run with every old thread pending.

The baseline holds back one kind of existing item: a bot review submitted
against the PR's current head. That is feedback on the code as it stands,
and a review body can carry findings of its own
(`pr-watch/references/known-bots-overlay.md`), so it arrives as the first
`pending` event instead of being treated as history. A bot review on an
older head, a bot issue comment, and anything the user already answered
are baselined as before.

## 6. Confirm

For each PR run `POLL --tails <N>` (authored) or `POLL --findings <N>`
(reviewed), both with `--state-dir <STATE_DIR>`. Show one table:

| PR | Role | Title | Worktree | What the first event will act on |
|---|---|---|---|---|

For authored PRs the last column is the pending thread and top-level
counts. For reviewed PRs it is "head moved past your review" or "waiting
for a push". When the command exits non-zero, the last column is its
stderr line and the PR stays in the set; the first event refetches it.
Under the table list the excluded PRs and why: authored PRs with no
worktree, and PRs removed in steps 3 and 5 with their stderr line.

Ask with `AskUserQuestion`: "Watch these PRs?" with options "Watch them"
and "Change the set". On "Change the set", take the changes in plain
text. Run each PR added through §3's explicit-number handling (the live
role read and, for an authored PR with no worktree, creating one), §4's
starting keys, and §5's baseline, removing it again and listing it among
the excluded PRs with the command's stderr line when the baseline fails.
Apply the changes to `watch.json` and ask again.

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

These files sit in other worktrees, which the Write tool refuses the
same way as `STATE_DIR`. Write the object to the scratchpad and place it
with the script from `pr-watch/references/watch-state-schema.md`
"Writing", naming this file on both sides:

```
python "<SKILL_DIR>/scripts/state_put.py" "<scratchpad>/pr-<N>.json.new" "<worktree>/.pr-autopilot/pr-<N>.json"
```

Creating the file is all this step does; no lock exists yet, and the
library's own write protocol (lock refresh, schema validation, the
`state_write` log line) governs every update after step 04 acquires one.
An existing file (from a `pr-autopilot`
run) is left as it is; the lock protocol updates its `session_id` when it
reclaims.

Then go to `pr-watch/steps/02-arm-monitor.md`.
