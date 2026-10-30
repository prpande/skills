# Step 01 — Discover, claim, baseline, confirm, initialise

Runs on `/pr-watch [owner/repo#N | N ...]`. Writes `watch.json`, one
progress file per PR, one lease per PR, and one library state file per
authored PR. Posts nothing anywhere.

## 1. Record the fixed values

Run each command on its own and keep its output:

- `python -c "import os; print(os.environ['CLAUDE_CODE_SESSION_ID'])"` →
  `SESSION_ID`.
- `python -c "import sys; sys.path.insert(0, r'<SKILL_DIR>/scripts'); import pw_paths; print(pw_paths.home())"`
  → `PW_HOME`, an absolute path that honours `PR_WATCH_HOME`.
- `python -c "import os, sys; sys.path.insert(0, r'<SKILL_DIR>/scripts'); import pw_paths; print(pw_paths.session_dir(os.environ['CLAUDE_CODE_SESSION_ID']))"`
  → `SESSION_DIR`, the absolute path every `--session-dir` below takes.
- `python -c "import os; print(os.environ['CLAUDE_PID'])"` → `CLAUDE_PID`.
- `git rev-parse --show-toplevel` → `ORIGIN`, the worktree the session is
  in now.
- `gh api user --jq .login` → `SELF`. A failure here means `gh` is not
  authenticated: stop and tell the user to run `gh auth login`.

Then run `POLL --check-identity`. A non-zero exit means this process is
not running under the claude process in `CLAUDE_PID`, so a lease written
now would name the wrong holder. Stop the whole arm, print the command's
stderr line, and write nothing.

Under `--dry-run` no lease exists, so every `--claim` and `--lease-status`
in this step is skipped.

A `POLL` command in this step with no branch of its own below
(`--discover`, `--end-leftover-monitors`, `--monitor-alive`) stops the
whole arm on a non-zero exit: print its stderr line and write nothing
further.

## 2. Resume or start

Run `POLL --end-leftover-monitors --session-dir <SESSION_DIR>` first, on
every arm. It ends every monitor of this session left by an earlier
claude process and prints their pids, so one session never has two
pollers. It prints `[]` when there is none.

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
  `released` or `closed` is dropped. An entry whose `status` is `armed`
  or `lost` stays, and §5 claims it again. An entry whose `status` is
  `stopped` stays `stopped`, with its lease untouched, unless this is a
  bare `/pr-watch` or the invocation names it; then §5 claims it and §7
  sets it `armed` once the claim succeeds.
- `push_queue`, `serialize_pushes`, and `bot_allowlist` are kept.
  `channel_id` is kept when it is `C0C15VC8Y0Z`; any other value is set
  to `C0C15VC8Y0Z`, and `slack_ts` is set to `null` in the progress file
  of every PR in the watch, since those values belong to another channel. `session_id` stays `SESSION_ID`.
- `watcher` is kept. A watch whose `watch.json` has `"watcher": "central"`
  stays central, whether or not `--central` was passed: this invocation
  is treated as `--central` in §5 and §9 and arms no Monitor.

Otherwise start from an empty set.

## 3. Discover

Build the candidate set in the conversation. Nothing is written until §5.

**Bare `/pr-watch`.** Run `POLL --discover --session-id <SESSION_ID>`. It
prints a JSON list of `{ref, url, branch, evidence}` for the open PRs
this session wrote to and authored. Each joins the set as `authored`.
The list carries no title; read each with
`gh pr view <url> --json title --jq .title`.
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
PRs are claimed with `--explicit` in §5, and a saved `stopped` entry
among them is re-armed (§2).

**Clone and worktree.** An `authored` PR needs the path of a worktree of
its head branch. Resolve the clone first:

- The current directory's repo, when
  `git remote get-url origin` names `<owner>/<repo>` (compare without
  case). `CLONE` is `ORIGIN`.
- Otherwise run `POLL --find-clone <owner/repo#N> --session-id <SESSION_ID>`.
  It prints the top level of a clone this session worked in, else the
  worktree the PR's lease holder recorded. `CLONE` is that path.
- A non-zero exit excludes the PR with the command's stderr line. Search
  nowhere else.

Then `git -C <CLONE> worktree list --porcelain`. `MAIN` is the path on
the first `worktree` line of that listing. When a
`branch refs/heads/<headRefName>` line has a `worktree` path above it,
that path is the PR's `worktree`. When none does, create one:

```
git -C <CLONE> fetch origin <headRefName>
git -C <CLONE> worktree add <MAIN>/.claude/worktrees/<headRefName> <headRefName>
```

If the local branch does not exist, the second command is
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

- `none`: nothing to migrate. When an earlier import renamed the old
  watch but no session claimed some of its PRs (the session ended before
  §5), `prs` lists those PRs, for 7 days after that import and until
  §7 runs `--migrate-done`; add them as the import paragraph below says.
- `stale`: no old poller runs and its heartbeat is over 300 s old. Import.
- `owned`: the old poller runs under this session's claude process. End
  it, then import. `TaskStop` the monitor when its task id is still in
  the conversation. Otherwise run `taskkill /T /F /PID <monitor_pid>`;
  `--end-leftover-monitors` does not cover it, because the old poller
  was started with `--state-dir`.
- `foreign`: another session owns it. Run `claude agents --json` and find
  the entry whose `pid` is `owner_pid`; its `name` is the `[Tag]Name` label. When the
  command fails, lists no match, or `owner_pid` is null, the label is "the
  session running claude pid <owner_pid>" ("an unidentified session" for
  null). Exclude every candidate PR whose key is in `prs` with
  "old-format watch in <owner/repo> held by <label>, heartbeat
  <heartbeat_age>s ago; re-arm /pr-watch in that session".
- `live-unknown`: no old poller process, and the heartbeat is
  <heartbeat_age>s old. Exclude the same PRs with "old-format watch in
  <owner/repo> ticked <heartbeat_age>s ago; retry after it goes stale".

A non-zero exit from `--migrate-scan` or `--migrate-import` excludes
every candidate PR of that repo with the command's stderr line and leaves
the old watch as it is.

To import, run `POLL --migrate-import <MAIN> --session-dir <SESSION_DIR>`.
It copies each old PR's progress into its `<N>.progress.json`, keeps a
progress file that already exists, renames the old `watch.json` to
`watch.json.migrated`, and deletes the old heartbeat and poller files.
Its output is not the PR list: a re-run after a crash prints `[]`. Take
the PR set from the scan's `prs`, for an import and for a `none` scan
alike. Add each key in `prs` that is not
already a candidate and that is still open (resolve it as in §3, with its
role from the live author), so no PR of the old watch is left unwatched.

## 5. Write `watch.json` and claim

When §2 kept no entry and §3 and §4 found no candidate, tell the user
that no PR was resumed, discovered, or named, and stop. Write nothing.

Write `watch.json` per `pr-watch/references/watch-state-schema.md`
"Writing", with:

- `session_id` `SESSION_ID`, `claude_pid` `CLAUDE_PID`, `self_login`
  `SELF`, and `origin_worktree` `ORIGIN`;
- `channel_id` `C0C15VC8Y0Z`, `serialize_pushes`
  `false` only under `--parallel-pushes`, and `dry_run` from `--dry-run`;
- `stopped_at` kept as it is; §7 clears it;
- `push_queue` kept from a resume, else `[]`;
- `bot_allowlist` `["sonarqube-mbodevme", "mindbody-ado-pipelines", "mergewatch-playlist"]`
  (kept as is on resume);
- `ado_orgs` `["mindbody"]`; on resume it is written that way only when
  the key is missing, and any other existing value is kept;
- `prs`: only the entries §2 kept, each with its current `status`
  unchanged. A candidate PR is added to `prs` in §7, after its claim and
  baseline, never before, and a kept entry changes to `armed` only there,
  after its claim: a running monitor reloads `watch.json` every tick and
  would otherwise act on a PR this session does not hold yet.

A central watch (`watcher` kept from a resume, or `--central`) keeps
`"watcher": "central"` in `watch.json`, and so does every later write of
this file in this step and in the steps that follow. The field is already
in `watch.json` only on a resume; on a fresh `--central` run it is written
by section 9 step 4 alone, after the down check, and "keeps" applies only
where `watch.json` already has it.

The lease needs `session_id` and `claude_pid` from this file, so write it
before the first claim.

Under `--dry-run` take no lease and go to §6.

Otherwise claim each kept entry whose `status` is `armed` or `lost`, each
kept `stopped` entry §2 marked for re-arming, and each candidate, one command each:
`POLL --claim <owner/repo#N> --role <role> --session-dir <SESSION_DIR>`,
adding `--explicit` for a PR the user named in this invocation, and
`--central` when the watch is central (the flag was passed, or `watch.json`
already has `"watcher": "central"`, which covers a bare `/pr-watch` and
new refs joining a central watch). It prints:

- `claimed`: the lease was free or released.
- `reclaimed`: the lease was already this session's.
- `taken-over`: the lease came from a dead session. Read the PR's
  `<N>.progress.json`. When `queued_head` is set or `ci_rerun_queued` is
  non-empty, add the PR's key to `push_queue` in `watch.json`, so the
  next drain handles a fix the dead session committed but did not push.
  That commit exists only in the dead session's clone; when §3 resolved
  another clone, the drain escalates it instead of pushing.

A non-zero exit refuses the claim. When its stderr line says "lease
unreadable", run the same claim once more. Any other refusal, and a second
"lease unreadable", drops a candidate or refuses a kept entry, and lists
the PR among the excluded PRs in §7 with the command's stderr line. A
refused kept entry becomes `lost` when the stderr line names another
holder, and otherwise keeps its old `status`.

Wherever this step drops a candidate, refuses a kept entry, or removes an
entry from `watch.json`, it also removes the PR's key from `push_queue`.

## 6. Baseline

Progress files live at `<PW_HOME>/prs/<owner>/<repo>/<N>.progress.json`,
or under `--dry-run` at
`<SESSION_DIR>/progress/<owner>/<repo>/<N>.progress.json`. They are
written with `state_put.py` as `watch-state-schema.md` "Writing" shows.

For every claimed PR (kept entry or candidate) whose progress file does
not exist, write one with the starting keys for its role, in a single
write that already holds an `authored` PR's baseline (below):

- all PRs: `posted_reply_ids`, `settled_ids`, and `escalated_ids` as
  `[]`, `handled_top_level_ids` as `{}`, `slack_ts` as `null`;
- `authored` adds `slack_root_checked` as `false`, `ci_reruns`, `ci_rerun_queued`, `ci_handled`, and
  `ci_log_retries` as `[]`; `ci_log_occurrence` and `cap_notified_head`
  as `null`; `ci_fix_pushes` and `review_fix_pushes` as `0`;
  `last_pushed_head`, `queued_head`, `queued_at`, `wait_notice_at`,
  `retry_after`, and `skip_reason` as `null`;
- `reviewed` adds `finding_verdicts` as `{}`, and `rereviewed_head` and
  `retry_after` as `null`.

A progress file that exists (a resume, a takeover, an import) is never
re-baselined. A key it lacks for its role gets the starting value; every
key it has is kept.

For every `authored` PR without a progress file, run
`POLL --baseline <owner/repo#N> --session-dir <SESSION_DIR>` before
writing it, and put its `settled_ids` and `handled_top_level_ids` into
that one write. When it exits non-zero, write no progress file, drop the
PR (remove a kept entry from `watch.json`), release its lease with
`POLL --lease-status <owner/repo#N> --status released --session-dir
<SESSION_DIR>`, and list the PR among the excluded PRs in §7 with the
command's stderr line. A progress file is shared by every later holder
and never re-baselined, so one written without its baseline would replay
every old thread.

The baseline holds back one kind of existing item: a bot review submitted
against the PR's current head. That is feedback on the code as it stands,
and a review body can carry findings of its own
(`pr-watch/references/known-bots-overlay.md`), so it arrives as the first
`pending` event instead of being treated as history. A bot review on an
older head, a bot issue comment, and anything the user already answered
are baselined as before.

A `reviewed` candidate is checked with
`POLL --findings <owner/repo#N> --session-dir <SESSION_DIR>`. Drop it and
release its lease (skipped under `--dry-run`) when every thread is
`is_resolved: true` and every comment after the user's last comment on it
(the entries after the last `me` in `kinds`) has its id in `escalated_ids`
(empty for a new PR, so any such comment keeps it): 03 D step 1's settle
condition, meaning nothing is left to watch. When the command exits
non-zero, drop it and release its lease (skipped under `--dry-run`) too,
and list it among the excluded PRs in §7 with the command's stderr line.

## 7. Confirm

For each PR still in play (kept entries being armed, and candidates) run
`POLL --tails <owner/repo#N>` (authored) or
`POLL --findings <owner/repo#N>` (reviewed), both with
`--session-dir <SESSION_DIR>`. Show one table:

| PR | Role | Title | Worktree | What the first event will act on |
|---|---|---|---|---|

For authored PRs the last column is the pending thread and top-level
counts. For reviewed PRs it is "head moved past your review" or "waiting
for a push". When the command exits non-zero, the last column is its
stderr line and the PR stays in the set; the first event refetches it.
Under the table list the excluded PRs and why: PRs with no local clone,
refused claims, old-format watches held elsewhere, and PRs dropped in §6
with their stderr line.

With `--yes`, skip the question. Otherwise ask with `AskUserQuestion`:
"Watch these PRs?" with options "Watch them" and "Change the set". On
"Change the set", take the changes in plain text. Drop a candidate, or
remove a kept entry from `watch.json`, and release its lease with
`POLL --lease-status <owner/repo#N> --status released --session-dir
<SESSION_DIR>` (skipped under `--dry-run`). Run each PR added through §3,
§5's claim, and §6, dropping it again and listing it among the excluded
PRs with the command's stderr line when its baseline fails. Ask again.

Once the set is accepted, set `status` `armed` on each kept entry whose
claim succeeded (under `--dry-run`, every one §5 would have claimed), add each remaining
candidate to `prs` in `watch.json` with `role`, `worktree` (authored
only), `branch`, `title`, `url`, and `status` `armed`, and rewrite the
file. For each `MAIN` whose old watch §4 imported or recovered, run
`POLL --migrate-done <MAIN> --session-dir <SESSION_DIR>`, so a later
scan does not offer the PRs left out here again. When at least one entry of `prs` is `armed`, also set `stopped_at`
to `null`; otherwise the watch stays as it was, so auto-join stays off.
When no entry of `prs` is `armed`, there is nothing to watch: tell the user
which PRs were excluded, delete `watch.json` if this run created it, and
stop.

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
`<git -C <worktree> rev-parse --path-format=absolute --git-common-dir>/info/exclude`. Never edit
`.gitignore`.

Creating the file is all this step does; no lock exists yet, and the
library's own write protocol (lock refresh, schema validation, the
`state_write` log line) governs every update after step 04 acquires one.
An existing file (from a `pr-autopilot` run) is left as it is; the lock
protocol updates its `session_id` when it reclaims.

## 9. Arm or join

When the watch is central (`--central` passed, or `watch.json` already has
`"watcher": "central"`), arm no Monitor and do not go to step 02:

1. `TaskStop` the remembered Monitor task, if there is one.
2. Run `POLL --end-session-monitors --session-dir <SESSION_DIR>`. It ends
   every `--monitor` poller for this session directory, whatever its
   claude ancestor, and prints the pids it ended as a JSON list.
3. Run `POLL --monitor-alive --session-dir <SESSION_DIR>`. When it does not
   print `down`, do not write `"watcher": "central"`. The leases are
   already claimed as central with nothing ticking them, so release each
   one claimed in this run with `POLL --lease-status <owner/repo#N>
   --status released --session-dir <SESSION_DIR>`, then tell the user the
   monitor could not be ended and stop.
4. Write `"watcher": "central"` into `watch.json` (already there on a
   resume) and stop. From here the
   orchestrator ticks the watch and delivers events as `/pr-watch event`
   messages (`pr-watch/steps/03-route-event.md`).

Otherwise (a Monitor watch) run `POLL --monitor-alive --session-dir <SESSION_DIR>`. Run it
after the entries above are written, never on a remembered task id:

- `alive`: a monitor of this session is already running. Arm nothing; its
  next tick picks up the new entries. Post nothing here; step 06 posts
  the join line.
- `down`: go to `pr-watch/steps/02-arm-monitor.md`. This also covers a
  monitor that went `idle` while the entries were being written, and a
  task id lost to compaction.
