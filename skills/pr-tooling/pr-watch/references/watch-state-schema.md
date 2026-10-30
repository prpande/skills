# Watch state schema

pr-watch keeps its state under `PW_HOME` (`~/.claude/pr-watch/`). Nothing
lives in a repo's main checkout. Each file has exactly one writer.

```
PW_HOME/
  sessions/<session-id>/        SESSION_DIR
    watch.json                  session; written only by the session
    watch-poller.json           written only by POLL --monitor and --tick-all
    watch-poller.dry-run.json   written only by POLL --tick-all --dry-run
    events.jsonl                spool of central events; appended only by POLL --tick-all
    slack-<reply_ts>.json       Slack thread replies for one slack-reply event; written and deleted only by the session
    events.dry-run.jsonl        the same for --tick-all --dry-run
    watch-heartbeat             written only by POLL --monitor
    watch-seen.json             written only by POLL --report and --reseed
    progress/<owner>/<repo>/<N>.progress.json   dry-run watches only
  prs/<owner>/<repo>/
    <N>.json                    the lease; written only by poll.py
    <N>.progress.json           the PR's progress; written only by the lease holder's session
    <N>.claim.lock              transient lock around every lease write
    push.lock                   transient lock around a push
```

`<session-id>` is `CLAUDE_CODE_SESSION_ID`; `--resume` keeps it. `owner`
and `repo` are lowercase wherever they form a path or a key, and a PR key
is `owner/repo#N` (`mindbody/mindbody.clients#14`).

`<N>.json` is the lease. Its fields and rules are in
`pr-watch/references/lease-contract.md`, which outside readers cite.

`push.lock` is exclusive-create. A session takes it before the scan for
other PRs' running checks and releases it once the pushed head has a
check run registered, or 120 seconds after the push. It takes it again
right before the push, which refreshes the lock it holds. A lock older
than 300 seconds is stale. A session that finds it held treats the repo as
busy and queues. `POLL --push-lock take|release <owner/repo#N>` takes and
releases it.

## Writing

The session writes the whole new object every time and never edits a
file in place. Re-read it before every write; events are handled one at a
time, so no two session writes race. The poller files and the lease are
never written by the session directly. The write itself is atomic,
through the two steps below.

`SESSION_DIR` and `PW_HOME/prs/` are outside the worktree, and a session
in a worktree cannot write there with the Write tool: it refuses every
path outside the worktree the session is in. This is the normal case, not
an edge one, and it applies to the library files in the other PR
worktrees too. Write the new object to the scratchpad with the Write
tool, then hand it to the script that does the placing:

```
python "<SKILL_DIR>/scripts/state_put.py" "<scratchpad>/watch.json.new" "<SESSION_DIR>/watch.json"
```

It takes any source and any destination, so it places a
`<N>.progress.json` and the library's `pr-<N>.json` the same way. It
reads the staged file as JSON (a half-written one fails there, before
anything is replaced), creates the destination's directory if it is
missing, and writes through the poller's own `write_json_atomic`: the
temp file is made next to the destination, so the rename stays on one
filesystem, and a replace that Windows refuses because a reader holds the
file open is retried before it gives up. A hand-rolled copy and rename
has neither the retry nor the cleanup.

## `watch.json`: written only by the session

| Field | Type | Meaning |
|---|---|---|
| `session_id` | string (UUID) | The session that armed the watch; also the `session_id` in every library lock this watch takes |
| `claude_pid` | integer | `CLAUDE_PID` of the session's claude process; the monitor exits when that process is gone |
| `self_login` | string | `gh api user --jq .login` at arm |
| `channel_id` | string | Slack channel for notifications; always `C0C15VC8Y0Z` |
| `origin_worktree` | string (absolute path) | Where the session returns after every fix |
| `serialize_pushes` | boolean | `false` only with `--parallel-pushes` |
| `bot_allowlist` | array of logins | Logins always classified as bots, whatever type GitHub reports |
| `ado_orgs` | array of strings | Azure DevOps organisations `POLL --ci-log` and `--ci-rerun` may send the PAT to, matched without case; a link to any other organisation, a missing key, or a value that is not a list of strings, fails without a request. The link's org must also match `^[A-Za-z0-9._-]+$` and its project `^[A-Za-z0-9._ %!&()@~-]+$`. Written by `pr-watch/steps/01-discover.md` section 5: `["mindbody"]` for a new watch, and on resume only when the key is missing |
| `watcher` | string or absent | `central` when the orchestrator's `POLL --tick-all` ticks this watch and the session arms no Monitor; written by `pr-watch/steps/01-discover.md` section 9 only after `POLL --monitor-alive` prints `down`. Absent for a Monitor watch. `--tick-all` ticks only watches that carry it |
| `dry_run` | boolean | `true` for a `--dry-run` watch. A dry run takes no leases and keeps each PR's progress under `SESSION_DIR/progress/`, so a rehearsal never touches the shared files. A saved watch with `dry_run: true` is never resumed by a non-dry-run invocation |
| `stopped_at` | integer or null | Epoch seconds `/pr-watch stop` ran; cleared by any arm. Auto-join from `pr-autopilot` and `pr-followup` does nothing while it is set |
| `push_queue` | array of PR keys | `owner/repo#N` of authored PRs with a local fix commit or a CI rerun waiting for other PRs' checks |
| `prs` | object keyed by PR key | See below |

Per PR in `prs`:

| Field | Type | Meaning |
|---|---|---|
| `role` | `authored` \| `reviewed` | From the PR's live author at discovery |
| `worktree` | string or absent | Absolute path; `authored` only |
| `branch` | string | Head branch name |
| `title`, `url` | string | For the Slack root of a `reviewed` PR |
| `status` | string | `armed`, `stopped`, `released`, `closed` or `lost`. The poller ticks only `armed` PRs. `lost` means another session claimed the lease; this session no longer acts on the PR |

## `<N>.progress.json`: written only by the lease holder's session

The per-PR fields below. The poller reads the file. A session that takes
a PR over continues from this file, so settled threads, posted replies,
push caps and the Slack thread carry across the handover.

| Field | Type | Meaning |
|---|---|---|
| `slack_ts` | string or null | The PR's Slack thread root: the routine's thread, or for a `reviewed` PR the user's own. Null until `pr-watch/steps/06-notify.md` "Finding the thread" finds or starts one |
| `slack_root_checked` | boolean | `authored` only. `true` once a recorded `slack_ts` has been confirmed to be a root the routine posted |
| `posted_reply_ids` | array of node ids | Replies this watch posted (GraphQL `id`, not `databaseId`) |
| `settled_ids` | array of node ids | Comments that close a tail with no reply: first-arm baseline, Filter B skips, acknowledged threads |
| `escalated_ids` | array of node ids | Comments sent to Slack as needing the user |
| `handled_top_level_ids` | object id to disposition | `baseline`, `skipped`, `escalated`, `parsed`, or the fixer verdict. A Slack thread reply is keyed `slack:<reply ts>`; its event is `{"kind":"slack-reply","pr","thread_ts","reply_ts","human","bots"}`. Findings parsed out of an anchor comment are keyed `<anchor id>\|<path>\|<title>` (`pr-watch/references/known-bots-overlay.md`) |
| `last_pushed_head` | string or null | `authored` only. Sha of the last push this watch made |
| `ci_fix_pushes` | integer | `authored` only. CI fix commits since the last head the watch did not push, queued ones included; reset to 0 when a `ci-red` arrives on such a head; cap 3 |
| `review_fix_pushes` | integer | `authored` only. Fix commits for dispatch sets with no human record since the last head the watch did not push, queued ones included; reset to 0 when a fix arrives on such a head or any dispatch set holds a human record; cap 3 |
| `ci_reruns` | array of strings | `authored` only. `<head>\|<workflow>\|<check name>` for every check a rerun covers: the check handled and every other red check with the same `run_id` (GitHub Actions) or `build_id` (Azure Pipelines); written by `pr-watch/steps/07-ci.md` section 3 step 1. A check is rerun at most once per head |
| `ci_rerun_queued` | array of `{link, head, name, sibling_keys}` | `authored` only. Reruns waiting for the push-queue drain, `name` being the check name and `sibling_keys` the other checks' `ci_reruns`/`ci_handled` keys `pr-watch/steps/07-ci.md` section 3 step 1 added alongside this one; the drain (`pr-watch/steps/04-fix-path.md` section 8 step 4) removes exactly those keys from both on a failed rerun. Entries whose `head` is no longer the PR head are dropped there with a "CI rerun dropped" line |
| `ci_handled` | array of strings | `authored` only. `<head>\|<workflow>\|<check name>\|<completed_at>` for every check occurrence step 07 has already escalated, reported pre-existing, dispatched a fixer for, or covered with a rerun of its run or build (section 3 step 1); a re-emit of the same occurrence is skipped. Step 07 removes a key again after a first failed log read (rule 3) and after a gate or lock skip (sections 4 and 5) |
| `ci_log_retries` | array of strings | `authored` only. `ci_handled` keys whose log read failed once; written by `pr-watch/steps/07-ci.md` rule 3. A second failed read of the same occurrence escalates |
| `cap_notified_head` | string or null | `authored` only. The head the user was told about when `review_fix_pushes` reached its cap (`pr-watch/steps/04-fix-path.md` section 1). Bot-only sets on that same head are escalated into `escalated_ids` without a second message |
| `ci_log_occurrence` | string or null | `authored` only. The occurrence key whose redacted log is in `<worktree>/.pr-autopilot/ci-log-<N>.txt`; written by `pr-watch/steps/07-ci.md` rule 3 after it places the file. One file serves the whole PR and is never deleted, so this is what says whose log it holds: `pr-watch/steps/06-notify.md` quotes the file only for the occurrence named here |
| `finding_verdicts` | object thread id to verdict | `reviewed` only; the last re-review verdict posted on that thread (`pr-watch/steps/05-rereview.md`); a judge return that matches it is not replied or resolved again |
| `rereviewed_head` | string or null | `reviewed` only. The `new_head` of the last completed re-review round; written by `pr-watch/steps/05-rereview.md` step 8. The poller compares from it instead of the user's review commit when it is set |
| `queued_head` | string or null | `authored` only. Sha of the fix commit queued behind another PR's checks; set by `pr-watch/steps/04-fix-path.md` section 6 step 1, cleared by the drain (section 8 step 5) on every path. The drain pushes only when the worktree `HEAD` still equals it |
| `queued_at` | integer or null | `authored` only. Epoch seconds the PR joined `push_queue`; set by step 04 section 6 step 1, or by `pr-watch/steps/07-ci.md` section 3 step 2 when not already set; cleared by the drain. The drain stops waiting for other PRs' checks an hour after it |
| `wait_notice_at` | integer or null | `authored` only. The `queued_at` value the "Stopped waiting" line was posted for, so it posts once per wait; set by step 04 section 8 step 1, cleared by section 8 step 5 |
| `retry_after` | integer or null | Both roles. Epoch seconds after which the poller re-emits the PR's events once (pending set and red checks on an `authored` PR; reply, head-moved, or settled on a `reviewed` PR); set to now + 600 by every skip in step 04 sections 1 and 2, by `pr-watch/steps/03-route-event.md` A.1, by a first failed log read in `pr-watch/steps/07-ci.md` rule 3, by `pr-watch/steps/03-route-event.md` B.4 after it writes `escalated_ids`, and, for either role, by a failing `POLL` command that no step gives its own branch (`SKILL.md` hard rules) |
| `review_ask` | object or null | `authored` only; null until the review ask is sent. `{"drafted_at": ISO UTC string, "outbox_ts": the Slack ts of the message in `C0C205Q34SX`, "destination": channel id of the earlier ask's channel, or `none`}`. Written by `pr-watch/steps/08-review-ask.md` step 4 right after the send; once set, the poller never raises `review-ready` for the PR. Never written under `dry_run`. The orchestrator reads it |
| `merge_notified` | string or null | `authored` only. `<kind>:<head>` of the last `conflicting` or `behind-ready` line posted, set by `pr-watch/steps/03-route-event.md` G.3 and H.2; the poller raises neither kind again for that head |
| `skip_reason` | string or null | `authored` only. The reason of the last "Skipped" line posted; set by step 04's skips, cleared when step 04 section 2 acquires the lock. A skip with the same reason posts no line |

## `watch-poller.json`: written only by `POLL --monitor` and `--tick-all`

`last_reconciliation` (epoch seconds), `last_tick_at` (epoch seconds of the
last successful `--tick-all` tick; the oldest session ticks first),
`last_tick_event` (epoch seconds),
`last_tick_queue` (array), `closed` (array of PR keys; a key no longer in
`watch.json` `prs` is dropped at the start of each tick), `errors` (PR key
to the lease `last_error` value for each PR the last tick could not
check; `pr-watch/references/lease-contract.md`), `heads` (PR key to
head sha at the last tick), `poller_pid`, `claude_pid`,
`claude_started_at`, and `prs` keyed by PR key with `updated_at`,
`last_head`, `last_signature`, `last_rollup` (the head commit's check
rollup state), `last_ci_signature`, `pending_since`, `retried_at` (the
`retry_after` value the poller last acted on for the pending/reviewed
branch, so each `retry_after` forces one re-emit of it; kept across later
writes of the entry), and, `authored` PRs only, `ci_retried_at` (the same,
for the CI branch; spent independently, so a standing CI-only failure does
not keep forcing the pending set too), and, `reviewed` PRs only,
`compared` (`[old head, new head, changed paths]` of the last compare, so
the same head range is not fetched again). `review` maps an `authored` PR key to `checked` (`[head, updatedAt]` of the last review-ready evaluation) and `emitted` (the head a `review-ready` event was last raised for), so the event comes once per head. `merge` maps an `authored` PR key to `<kind>:<head>` of the last `conflicting` or `behind-ready` event, so each comes once per head between forced ticks; a forced tick raises it again until the progress file's `merge_notified` records it. `lease_dropped` and `lease_warned` (central ticks) record the leases whose
loss and whose write fault have already been reported, so each is raised
once; `failed_ticks` counts consecutive failed runs of this session (five
spool one `poller-error`); `closed` is cleared on the daily forced pass, so
a closed PR is re-checked. Deleting the file makes the next
tick a full reconciliation. `poller_pid` and `claude_pid` are recorded
for diagnosis; the ancestry checks read the live process list.

## `events.jsonl`: appended only by `POLL --tick-all`

One JSON object per line, `{"session", "pr", "kind", ...}` plus the fields
of the event kind. `tick` lines carry no `pr`. A line is appended after the
lease writes and before the poller state is saved, so an event the lease
writer filtered (lost or closing leases) is never spooled; a kill between
the append and the save re-raises that tick's events, which the reader
dedupes by signature. `--tick-all --dry-run` writes `events.dry-run.jsonl`
and `watch-poller.dry-run.json` instead and takes no leases. The
orchestrator reads the spool and sends the session each event as a
`/pr-watch event` message; the spool holds kinds, PR ids and SHAs, no
comment text, except that `poller-error` lines carry the raw error text
(the orchestrator drops it).

## `watch-heartbeat`: written only by `POLL --monitor`

The epoch seconds of the monitor's last sign of life, as a bare integer.
Written at the start of every tick, before every `gh` call, and after
every sleep, so the longest gap on a live monitor is one 120-second `gh`
timeout plus the 60-second sleep. A failed write is logged and never
stops the loop. The leases' `heartbeat` is what other sessions read.
`POLL --monitor-alive` does not read this file: the monitor is alive when
a `poll.py --monitor --session-dir <SESSION_DIR>` process runs under this
session's claude process.

## `watch-seen.json`: written only by `POLL --report` and `--reseed`

`{"<pr key>": [<every id seen>]}`. The NEW watermark of the report and
nothing else.

## Library files in the PR worktree

`<worktree>/.pr-autopilot/pr-<N>.json` follows
`pr-loop-lib/references/context-schema.md`; unknown keys are forbidden
there. Step 01 creates it with exactly `session_id`, `host_platform`,
`platform`, `repo_root`, `base`, `branch`, `head_sha`, `base_sha`,
`pr_number`, `pr_url`, `self_login`. Step 04 section 2 step 3a resyncs
`session_id` to `watch.json`'s current value on every fix, formatter
run, and drain, and step 04 adds `all_comments`,
`actionable`, `agent_returns`, `verifier_judgements`,
`files_changed_this_iteration`, `needs_human_items`, `last_push_sha`, and
`last_push_timestamp` as the library steps write them. The lock and log
follow `pr-loop-lib/references/state-protocol.md` and
`pr-loop-lib/references/log-format.md`.
