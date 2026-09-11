# Watch state schema

Three files in `<STATE_DIR>` (`<MAIN>/.pr-autopilot/`). Each has exactly
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
| `dry_run` | boolean | `true` for a `--dry-run` watch |
| `prs` | object keyed by PR number | See below |
| `push_queue` | array of PR numbers | Authored PRs with a local fix commit waiting to push |

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
| `last_pushed_head` | string or null | Sha of the last push this watch made |
| `ci_fix_pushes` | integer | CI fix commits since the last head the watch did not push, queued ones included; reset to 0 when a `ci-red` arrives on such a head; cap 3 |
| `ci_reruns` | array of strings | `<head>\|<workflow>\|<check name>` for every check rerun once; a check is rerun at most once per head |
| `ci_rerun_queued` | array of `{link, head}` | Reruns waiting for the push-queue drain; entries whose `head` is no longer the PR head are dropped there |

## `watch-poller.json` — written only by `POLL --monitor`

`last_reconciliation` (epoch seconds), `last_tick_event` (epoch seconds),
`last_tick_queue` (array), `closed` (array of PR numbers), and `prs` keyed
by PR number with `updated_at`, `last_head`, `last_signature`,
`last_rollup` (the head commit's check rollup state), and
`last_ci_signature`. Deleting the file makes the next tick a full
reconciliation.

## `watch-seen.json` — written only by `POLL --report` and `--reseed`

`{"<pr>": [<every id seen>]}`. The NEW watermark of the report and
nothing else.

## Library files in the PR worktree

`<worktree>/.pr-autopilot/pr-<N>.json` follows
`pr-loop-lib/references/context-schema.md`; unknown keys are forbidden
there. Step 01 creates it with exactly `session_id`, `host_platform`,
`platform`, `repo_root`, `base`, `branch`, `head_sha`, `base_sha`,
`pr_number`, `pr_url`, `self_login`. Step 04 adds `all_comments`,
`actionable`, `agent_returns`, `verifier_judgements`,
`files_changed_this_iteration`, `needs_human_items`, `last_push_sha`, and
`last_push_timestamp` as the library steps write them. The lock and log
follow `pr-loop-lib/references/state-protocol.md` and
`pr-loop-lib/references/log-format.md`.
