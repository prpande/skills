# Watch state schema

Four files in `<STATE_DIR>` (`<MAIN>/.pr-autopilot/`). Each has exactly
one writer. `.pr-autopilot/` must be ignored by git; step 01 adds it to
`<git common dir>/info/exclude` when it is not, and never edits
`.gitignore`.

## Writing

The session writes `watch.json` atomically: write the whole new object to
`watch.json.tmp` with the Write tool, then rename it over `watch.json`
(`mv -f` in Bash or `Move-Item -Force` in PowerShell). Never edit
`watch.json` in place. Re-read it before every write; events are handled
one at a time, so no two session writes race. The poller files are never
written by the session.

## `watch.json` — written only by the session

| Field | Type | Meaning |
|---|---|---|
| `session_id` | string (UUID) | The session that armed the watch; also the `session_id` in every library lock this watch takes |
| `owner`, `repo` | string | The GitHub repository |
| `self_login` | string | `gh api user --jq .login` at arm |
| `channel_id` | string | Slack channel for notifications |
| `origin_worktree` | string (absolute path) | Where the session returns after every fix |
| `serialize_pushes` | boolean | `false` only with `--parallel-pushes` |
| `bot_allowlist` | array of logins | Logins always classified as bots, whatever type GitHub reports |
| `ado_orgs` | array of strings | Azure DevOps organisations `POLL --ci-log` and `--ci-rerun` may send the PAT to, matched without case; a link to any other organisation, a missing key, or a value that is not a list of strings, fails without a request. The link's org must also match `^[A-Za-z0-9._-]+$` and its project `^[A-Za-z0-9._ %!&()@~-]+$`. Written by `pr-watch/steps/01-discover.md` section 4: `["mindbody"]` for a new watch, and on resume only when the key is missing |
| `dry_run` | boolean | `true` for a `--dry-run` watch; a saved watch with `dry_run: true` is never resumed by a non-dry-run invocation (`pr-watch/steps/01-discover.md` section 2 deletes it and the poller and seen files, starting fresh) |
| `prs` | object keyed by PR number | See below |
| `push_queue` | array of PR numbers | Authored PRs with a local fix commit or a CI rerun waiting for other PRs' checks |

Per PR:

| Field | Type | Meaning |
|---|---|---|
| `role` | `authored` \| `reviewed` | From the PR's live author at discovery |
| `worktree` | string or absent | Absolute path; `authored` only |
| `branch` | string | Head branch name |
| `title`, `url` | string | For Slack roots |
| `slack_ts` | string or null | The PR's Slack root |
| `posted_reply_ids` | array of node ids | Replies this watch posted (GraphQL `id`, not `databaseId`) |
| `settled_ids` | array of node ids | Comments that close a tail with no reply: first-arm baseline, Filter B skips, acknowledged threads |
| `escalated_ids` | array of node ids | Comments sent to Slack as needing the user |
| `handled_top_level_ids` | object id to disposition | `baseline`, `skipped`, `escalated`, `parsed`, or the fixer verdict. Findings parsed out of an anchor comment are keyed `<anchor id>\|<path>\|<title>` (`pr-watch/references/known-bots-overlay.md`) |
| `last_pushed_head` | string or null | `authored` only. Sha of the last push this watch made |
| `ci_fix_pushes` | integer | `authored` only. CI fix commits since the last head the watch did not push, queued ones included; reset to 0 when a `ci-red` arrives on such a head; cap 3 |
| `review_fix_pushes` | integer | `authored` only. Fix commits for dispatch sets with no human record since the last head the watch did not push, queued ones included; reset to 0 when a fix arrives on such a head or any dispatch set holds a human record; cap 3 |
| `ci_reruns` | array of strings | `authored` only. `<head>\|<workflow>\|<check name>` for every check a rerun covers: the check handled and every other red check with the same `run_id` (GitHub Actions) or `build_id` (Azure Pipelines); written by `pr-watch/steps/07-ci.md` section 3 step 1. A check is rerun at most once per head |
| `ci_rerun_queued` | array of `{link, head, name}` | `authored` only. Reruns waiting for the push-queue drain, `name` being the check name; entries whose `head` is no longer the PR head are dropped there with a "CI rerun dropped" line |
| `ci_handled` | array of strings | `authored` only. `<head>\|<workflow>\|<check name>\|<completed_at>` for every check occurrence step 07 has already escalated, reported pre-existing, dispatched a fixer for, or covered with a rerun of its run or build (section 3 step 1); a re-emit of the same occurrence is skipped. Step 07 removes a key again after a first failed log read (rule 3) and after a gate or lock skip (sections 4 and 5) |
| `ci_log_retries` | array of strings | `authored` only. `ci_handled` keys whose log read failed once; written by `pr-watch/steps/07-ci.md` rule 3. A second failed read of the same occurrence escalates |
| `finding_verdicts` | object thread id to verdict | `reviewed` only; the last re-review verdict posted on that thread (`pr-watch/steps/05-rereview.md`); a judge return that matches it is not replied or resolved again |
| `rereviewed_head` | string or null | `reviewed` only. The `new_head` of the last completed re-review round; written by `pr-watch/steps/05-rereview.md` step 8. The poller compares from it instead of the user's review commit when it is set |
| `queued_head` | string or null | `authored` only. Sha of the fix commit queued behind another PR's checks; set by `pr-watch/steps/04-fix-path.md` section 6 step 1, cleared by the drain (section 8 step 5) on every path. The drain pushes only when the worktree `HEAD` still equals it |
| `queued_at` | integer or null | `authored` only. Epoch seconds the PR joined `push_queue`; set by step 04 section 6 step 1, or by `pr-watch/steps/07-ci.md` section 3 step 2 when not already set; cleared by the drain. The drain stops waiting for other PRs' checks an hour after it |
| `wait_notice_at` | integer or null | `authored` only. The `queued_at` value the "Stopped waiting" line was posted for, so it posts once per wait; set by step 04 section 8 step 1, cleared by section 8 step 5 |
| `retry_after` | integer or null | Both roles. Epoch seconds after which the poller re-emits the PR's events once (pending set and red checks on an `authored` PR; reply, head-moved, or settled on a `reviewed` PR); set to now + 600 by every skip in step 04 sections 1 and 2, by `pr-watch/steps/03-route-event.md` A.1, by a first failed log read in `pr-watch/steps/07-ci.md` rule 3, and, for either role, by a failing `POLL` command that no step gives its own branch (`SKILL.md` hard rules) |
| `skip_reason` | string or null | `authored` only. The reason of the last "Skipped" line posted; set by step 04's skips, cleared when step 04 section 2 acquires the lock. A skip with the same reason posts no line |

## `watch-poller.json` — written only by `POLL --monitor`

`last_reconciliation` (epoch seconds), `last_tick_event` (epoch seconds),
`last_tick_queue` (array), `closed` (array of PR numbers; a number no
longer in `watch.json` `prs` is dropped at the start of each tick), and
`prs` keyed by PR number with `updated_at`, `last_head`,
`last_signature`, `last_rollup` (the head commit's check rollup state),
`last_ci_signature`, `retried_at` (the `retry_after` value the poller
last acted on for the pending/reviewed branch, so each `retry_after`
forces one re-emit of it; kept across later writes of the entry), and,
`authored` PRs only, `ci_retried_at` (the same, for the CI branch;
spent independently, so a standing CI-only failure does not keep
forcing the pending set too). Deleting the file makes the next tick
a full reconciliation.

## `watch-heartbeat` — written only by `POLL --monitor`

The epoch seconds of the monitor's last sign of life, as a bare integer.
Written at the start of every tick, before every `gh` call, and after
every sleep, so the longest gap on a live monitor is one 120-second `gh`
timeout plus the 60-second sleep. A failed write is logged and never
stops the loop. `pr-watch/steps/01-discover.md` section 2 treats a
heartbeat under 300 seconds old as a live watch.

## `watch-seen.json` — written only by `POLL --report` and `--reseed`

`{"<pr>": [<every id seen>]}`. The NEW watermark of the report and
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
