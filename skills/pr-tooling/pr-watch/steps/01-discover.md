# Step 01 — Discover, claim, baseline, confirm, initialise

Runs on `/pr-watch [owner/repo#N | N ...]`. Writes `watch.json`, one
progress file per PR, one lease per PR, and one library state file per
authored PR. Posts nothing anywhere.

## 1. Record the fixed values

Run each command on its own and keep its output:

- `python -c "import os; print(os.environ['CLAUDE_CODE_SESSION_ID'])"` →
  `SESSION_ID`. `SESSION_DIR` is `<PW_HOME>/sessions/<SESSION_ID>`.
- `python -c "import os; print(os.environ['CLAUDE_PID'])"` → `CLAUDE_PID`.
- `git rev-parse --show-toplevel` → `ORIGIN`, the worktree the session is
  in now.
- `gh api user --jq .login` → `SELF`. A failure here means `gh` is not
  authenticated: stop and tell the user to run `gh auth login`.

Then run `POLL --check-identity`. A non-zero exit means this process is
not running under the claude process in `CLAUDE_PID`, so a lease written
now would name the wrong holder. Stop the whole arm, print the command's
stderr line, and write nothing.

## 2. Resume or start

If this invocation is `--dry-run` and `<SESSION_DIR>/watch.json` exists
with `dry_run` other than `true`: stop and tell the user a real watch
exists for this session; a dry run needs it stopped (`/pr-watch stop`)
and its state files (`watch.json`, `watch-poller.json`, `watch-seen.json`)
moved aside first. Write nothing.

If `<SESSION_DIR>/watch.json` exists and its `dry_run` is `true` and this
invocation is not `--dry-run`: a dry run is never resumed by a real one.
If `POLL --monitor-alive --session-dir <SESSION_DIR>` prints `alive`, stop
and tell the user a dry-run watch is still running in this session and
must be stopped (`/pr-watch stop`) first; delete nothing. Otherwise delete
`watch.json`, `watch-poller.json`, `watch-seen.json`, and the `progress`
directory in `<SESSION_DIR>`, and start from an empty set exactly as a
first run.

Otherwise, if `<SESSION_DIR>/watch.json` exists, read it. This is a
resume:

- Its `prs` are the starting set, with their `role`, `worktree`,
  `branch`, `title`, and `url` kept. An entry whose `status` is
  `released` or `closed` is dropped. An entry whose `status` is `armed`,
  `stopped`, or `lost` stays, and §5 claims it again.
- `push_queue`, `channel_id`, `serialize_pushes`, and `bot_allowlist`
  are kept. `session_id` stays `SESSION_ID`.
- Run `POLL --end-leftover-monitors --session-dir <SESSION_DIR>`. It ends
  every monitor of this session left by an earlier claude process and
  prints their pids, so one session never has two pollers. It prints
  `[]` when there is none.

Otherwise start from an empty set.

## 3. Discover

Build the candidate set in the conversation. Nothing is written until §5.

**Bare `/pr-watch`.** Run `POLL --discover --session-id <SESSION_ID>`. It
prints a JSON list of `{ref, url, branch, evidence}` for the open PRs
this session wrote to and authored. Each joins the set as `authored`.
`[]` means the session has not written to any PR; tell the user so and
that `/pr-watch owner/repo#N` names one. A bare `/pr-watch` never adds a
reviewed PR, and a PR the user only mentioned in conversation is never
added.

**Explicit refs.** Each argument is `owner/repo#N`, a PR URL, or a bare
number. A bare number belongs to the repo of the current directory: run
`gh repo view --json nameWithOwner --jq .nameWithOwner` and use it as
the repo. Lowercase the owner and repo; the key is `owner/repo#N`. Read
the live author:
`gh pr view <N> --repo <owner/repo> --json author,state,title,url,headRefName`.
The PR joins the set as `authored` when the author is `SELF`, else
`reviewed`. A PR that is not open is excluded with its state. Explicit
PRs are claimed with `--explicit` in §5.

**Clone and worktree.** An `authored` PR needs the path of a worktree of
its head branch. Resolve the clone first:

- The current directory's repo, when
  `git remote get-url origin` names `<owner>/<repo>` (compare without
  case). `CLONE` is `ORIGIN`.
- Otherwise run `POLL --find-clone <owner/repo#N> --session-id <SESSION_ID>`.
  It prints the top level of a clone this session worked in. `CLONE` is
  that path.
- A non-zero exit excludes the PR with the command's stderr line. Search
  nowhere else.

Then `git -C <CLONE> worktree list --porcelain`. When a
`branch refs/heads/<headRefName>` line has a `worktree` path above it,
that path is the PR's `worktree`. When none does, create one:

```
git -C <CLONE> fetch origin <headRefName>
git -C <CLONE> worktree add <MAIN>/.claude/worktrees/<headRefName> <headRefName>
```

`MAIN` is the path on the first `worktree` line of that same listing. If
the local branch does not exist, the second command is
`git -C <CLONE> worktree add -b <headRefName> <MAIN>/.claude/worktrees/<headRefName> origin/<headRefName>`.

Other repos' worktrees are edited with absolute paths and `git -C`; this
step records the path and never moves the session.

A `reviewed` PR needs no worktree and no clone.

## 4. Old-format watches

Skip this section under `--dry-run`: a dry run migrates nothing.

For every repo in the candidate set that has a `CLONE`, run
`POLL --migrate-scan <MAIN> --session-dir <SESSION_DIR>`. It prints
`{state, monitor_pid, owner_pid, heartbeat_age, prs}`; `prs` lists the
keys in the old `<MAIN>/.pr-autopilot/watch.json`. Act on `state`:

- `none`: nothing to migrate.
- `stale`: no old poller runs and its heartbeat is over 300 s old. Import.
- `owned`: the old poller runs under this session's claude process. End
  it, then import. `TaskStop` the monitor when its task id is still in
  the conversation. Otherwise run `taskkill /T /F /PID <monitor_pid>`;
  `--end-leftover-monitors` does not cover it, because the old poller
  was started with `--state-dir`.
- `foreign`: another session owns it. Exclude every candidate PR whose
  key is in `prs` with "old-format watch in <owner/repo> held by the
  session running claude pid <owner_pid>, heartbeat <heartbeat_age>s ago;
  re-arm /pr-watch in that session".
- `live-unknown`: no old poller process, and the heartbeat is
  <heartbeat_age>s old. Exclude the same PRs with "old-format watch in
  <owner/repo> ticked <heartbeat_age>s ago; retry after it goes stale".

To import, run `POLL --migrate-import <MAIN> --session-dir <SESSION_DIR>`.
It copies each old PR's progress into its `<N>.progress.json`, keeps a
progress file that already exists, renames the old `watch.json` to
`watch.json.migrated`, and deletes the old heartbeat and poller files.
Its output is not the PR list: a re-run after a crash prints `[]`. Take
the PR set from the scan's `prs`. Add each key in `prs` that is not
already a candidate and that is still open (resolve it as in §3, with its
role from the live author), so no PR of the old watch is left unwatched.

## 5. Write `watch.json` and claim

Write `watch.json` per `pr-watch/references/watch-state-schema.md`
"Writing", with:

- `session_id` `SESSION_ID`, `claude_pid` `CLAUDE_PID`, `self_login`
  `SELF`, and `origin_worktree` `ORIGIN`;
- `channel_id` from `--channel` or `C0C15VC8Y0Z`, `serialize_pushes`
  `false` only under `--parallel-pushes`, and `dry_run` from `--dry-run`;
- `stopped_at` `null`: any arm clears it. An entry kept from a resume
  with `status` `stopped` becomes `armed`;
- `push_queue` kept from a resume, else `[]`;
- `bot_allowlist` `["sonarqube-mbodevme", "mindbody-ado-pipelines", "mergewatch-playlist"]`
  (kept as is on resume);
- `ado_orgs` `["mindbody"]`; on resume it is written that way only when
  the key is missing, and any other existing value is kept;
- `prs`: one entry per candidate, keyed `owner/repo#N`, with `role`,
  `worktree` (authored only), `branch`, `title`, `url`, and `status`
  `armed`.

The lease needs `session_id` and `claude_pid` from this file, so write it
before the first claim.

Under `--dry-run` take no lease and go to §6.

Otherwise claim each PR in the set, one command each:
`POLL --claim <owner/repo#N> --role <role> --session-dir <SESSION_DIR>`,
adding `--explicit` for a PR the user named in this invocation. It prints:

- `claimed`: the lease was free or released.
- `reclaimed`: the lease was already this session's.
- `taken-over`: the lease came from a dead session. Read the PR's
  `<N>.progress.json`. When `queued_head` is set or `ci_rerun_queued` is
  non-empty, add the PR's key to `push_queue` in `watch.json`, so the
  next drain handles a fix the dead session committed but did not push.

A non-zero exit refuses the claim. When its stderr line says "lease
unreadable", run the same claim once more. Any other refusal, and a second
"lease unreadable", removes the PR from `watch.json` and lists it among
the excluded PRs in §7 with the command's stderr line.

Rewrite `watch.json` once after the last claim so it holds exactly the
claimed PRs and the final `push_queue`.

## 6. Baseline

Progress files live at `<PW_HOME>/prs/<owner>/<repo>/<N>.progress.json`,
or under `--dry-run` at
`<SESSION_DIR>/progress/<owner>/<repo>/<N>.progress.json`. They are
written with `state_put.py` as `watch-state-schema.md` "Writing" shows.

For every PR in `watch.json` whose progress file does not exist, write
one with the starting keys for its role:

- all PRs: `posted_reply_ids`, `settled_ids`, and `escalated_ids` as
  `[]`, `handled_top_level_ids` as `{}`, `slack_ts` as `null`;
- `authored` adds `ci_reruns`, `ci_rerun_queued`, `ci_handled`, and
  `ci_log_retries` as `[]`; `ci_log_occurrence` and `cap_notified_head`
  as `null`; `ci_fix_pushes` and `review_fix_pushes` as `0`;
  `last_pushed_head`, `queued_head`, `queued_at`, `wait_notice_at`,
  `retry_after`, and `skip_reason` as `null`;
- `reviewed` adds `finding_verdicts` as `{}`, and `rereviewed_head` and
  `retry_after` as `null`.

A progress file that exists (a resume, a takeover, an import) is never
re-baselined. A key it lacks for its role gets the starting value; every
key it has is kept.

For every `authored` PR that got a new progress file in this run, run
`POLL --baseline <owner/repo#N> --session-dir <SESSION_DIR>`. Merge its
`settled_ids` and `handled_top_level_ids` into the PR's progress file.
When it exits non-zero, remove the PR from `watch.json`, release its lease
with `POLL --lease-status <owner/repo#N> --status released --session-dir
<SESSION_DIR>` (skipped under `--dry-run`), delete the progress file just
written, and list the PR among the excluded PRs in §7 with the command's
stderr line. A PR left in without its baseline would be resumed next run
with every old thread pending.

The baseline holds back one kind of existing item: a bot review submitted
against the PR's current head. That is feedback on the code as it stands,
and a review body can carry findings of its own
(`pr-watch/references/known-bots-overlay.md`), so it arrives as the first
`pending` event instead of being treated as history. A bot review on an
older head, a bot issue comment, and anything the user already answered
are baselined as before.

A `reviewed` PR new to this watch is checked with
`POLL --findings <owner/repo#N> --session-dir <SESSION_DIR>`. Remove it
from `watch.json` and release its lease when every thread is
`is_resolved: true` and every comment after the user's last comment on it
(the entries after the last `me` in `kinds`) has its id in `escalated_ids`
(empty for a new PR, so any such comment keeps it): 03 D step 1's settle
condition, meaning nothing is left to watch. When the command exits
non-zero, remove the PR and release its lease too, and list it among the
excluded PRs in §7 with the command's stderr line.

## 7. Confirm

For each PR run `POLL --tails <owner/repo#N>` (authored) or
`POLL --findings <owner/repo#N>` (reviewed), both with
`--session-dir <SESSION_DIR>`. Show one table:

| PR | Role | Title | Worktree | What the first event will act on |
|---|---|---|---|---|

For authored PRs the last column is the pending thread and top-level
counts. For reviewed PRs it is "head moved past your review" or "waiting
for a push". When the command exits non-zero, the last column is its
stderr line and the PR stays in the set; the first event refetches it.
Under the table list the excluded PRs and why: PRs with no local clone,
refused claims, old-format watches held elsewhere, and PRs removed in §6
with their stderr line.

With `--yes`, skip the question and go to §8. Otherwise ask with
`AskUserQuestion`: "Watch these PRs?" with options "Watch them" and
"Change the set". On "Change the set", take the changes in plain text.
Remove a PR from `watch.json` and release its lease with
`POLL --lease-status <owner/repo#N> --status released --session-dir
<SESSION_DIR>` (skipped under `--dry-run`). Run each PR added through §3,
§5's claim, and §6, removing it again and listing it among the excluded
PRs with the command's stderr line when its baseline fails. Apply the
changes to `watch.json` and ask again.

## 8. Initialise the library state for authored PRs

For each `authored` PR whose `<worktree>/.pr-autopilot/pr-<N>.json` does
not exist, read `gh pr view <N> --repo <owner/repo> --json baseRefName,headRefOid`
and create the file with exactly these keys (the library schema forbids
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
same way as `SESSION_DIR`. Write the object to the scratchpad and place it
with the script from `pr-watch/references/watch-state-schema.md`
"Writing", naming this file on both sides:

```
python "<SKILL_DIR>/scripts/state_put.py" "<scratchpad>/pr-<N>.json.new" "<worktree>/.pr-autopilot/pr-<N>.json"
```

Make sure the worktree ignores `.pr-autopilot/`: run
`git -C <worktree> check-ignore -q .pr-autopilot/probe`. On a non-zero
exit, append the line `.pr-autopilot/` to
`<git -C <worktree> rev-parse --git-common-dir>/info/exclude`. Never edit
`.gitignore`.

Creating the file is all this step does; no lock exists yet, and the
library's own write protocol (lock refresh, schema validation, the
`state_write` log line) governs every update after step 04 acquires one.
An existing file (from a `pr-autopilot` run) is left as it is; the lock
protocol updates its `session_id` when it reclaims.

## 9. Arm or join

When no PR in `watch.json` is `armed`, there is nothing to watch: tell the
user which PRs were excluded and stop.

Otherwise run `POLL --monitor-alive --session-dir <SESSION_DIR>`. Run it
after the entries above are written, never on a remembered task id:

- `alive`: a monitor of this session is already running. Arm nothing; its
  next tick picks up the new entries. Post nothing here; step 06 posts
  the join line.
- `down`: go to `pr-watch/steps/02-arm-monitor.md`. This also covers a
  monitor that went `idle` while the entries were being written, and a
  task id lost to compaction.
