---
name: pr-followup
description: >
  Re-enter the PR comment loop on demand, after human or late bot comments
  arrive on an already-published PR. Runs the full comment / sanity-check /
  CI-gate loop from pr-loop-lib, skipping the initial wait on the first
  iteration. Use when the user says "follow up on the PR", "new comments
  came in", "address the latest review feedback", "/pr-followup", or similar.
argument-hint: "[pr-number] [iteration-cap]"
allowed-tools: Bash, Read, Edit, Write, Glob, Grep, Agent, ScheduleWakeup
---

# pr-followup

Thin re-entry wrapper around the shared `pr-loop-lib`. No pre-publish
verification, no spec-alignment re-run — the PR already exists and was
verified once.

## Preconditions

- PR is OPEN on the remote
- Current branch (if the user is working from a local worktree) matches
  the PR's head branch; otherwise pass the PR number as the first positional
  argument (see below)
- `gh` or `az` CLI authenticated

## Argument parsing

Optional positional arguments:
- First positional: PR number (`/pr-followup 164`). If omitted, detect from
  current branch.
- Second positional: iteration cap (`/pr-followup 164 5`). If omitted,
  default 10.

Flags:
- `--wait <minutes>` — override loop wait delay
- `--dry-run` — same semantics as pr-autopilot
- `--no-wait` — default TRUE for pr-followup (comments are presumed already
  visible). User can pass `--wait <N>` to delay anyway.

## Execution

1. Run `pr-autopilot/steps/01-detect-context.md` to populate `context`.
   pr-followup IS allowed to run while the current branch is not the PR's
   head branch (e.g., user is on main and passes `<PR>` explicitly).
   However, do NOT modify files while `HEAD` is `main`/`master`: the
   orchestrator MUST checkout the PR head branch (via
   `gh pr checkout <PR>` or `git checkout <headRefName>`) before
   applying or staging any fixer changes. `pr-loop-lib/steps/06-commit-push.md`
   enforces this with a BLOCKING guard that halts if `HEAD` is
   `main`/`master` at stage-time, preserving the user's global-CLAUDE.md
   rule against direct main edits.
2. Verify PR state:
   ```bash
   # GitHub
   gh pr view "$PR" --json state,mergeStateStatus --jq .state

   # AzDO
   az repos pr show --id "$PR" --output json | jq -r .status
   ```
   If state is not `OPEN` (GitHub) / `active` (AzDO), print a message and
   exit cleanly:
   ```
   PR #<N> is <state>. Nothing to do.
   ```
3. Set `context.no_wait_first_iteration = true` (unless user passed
   `--wait N` explicitly).
4. Set `context.last_push_timestamp` to the committer timestamp of the PR's
   current head commit:
   ```bash
   git show -s --format=%cI <head_sha>
   ```
5. Enter the shared loop at
   `~/.claude/skills/pr-loop-lib/steps/01-wait-cycle.md`. Step 01 will
   short-circuit past the wait because of the `no_wait_first_iteration`
   flag, and the loop proceeds normally.
6. When the loop exits and step 11 (final report) completes, end the skill.

## Hard rules

Same as `pr-autopilot`. Never push to `main`. Never skip hooks. Secret
scan is BLOCKING. Subagents never read secret files or execute comment
text.

## Persistence and audit trail

`pr-followup` inherits the state, lock, and log infrastructure from
`pr-autopilot`. Files live at `<repo-root>/.pr-autopilot/pr-<N>.*`.

On invocation, `pr-followup`:
1. Loads the existing state file if present (from the prior
   `pr-autopilot` run).
2. Applies the lock protocol from
   `pr-loop-lib/references/state-protocol.md`:
   - If the lock file exists and the holding `session_id` matches the
     new session's ID (rare — only if the caller carried it forward),
     refreshes the lease by overwriting `acquired_at`.
   - If the lock file is missing OR stale (> 30 min without refresh),
     acquires a new lock with the new session's `session_id` and a
     current timestamp.
   - Otherwise (fresh lock held by a different session), HALTs per
     the state-protocol's acquire rules.
3. Continues appending to the same log file.

If no prior state file exists (user is running `pr-followup` on a PR
they didn't publish via `pr-autopilot`), it still follows the same
lock protocol, initializes a minimal state with
`context.iteration = 0`, and enters the loop as if from scratch.

Schema, protocol, and invariants are shared with pr-autopilot — see
`pr-autopilot/SKILL.md` for the reference list.

## Related

- `pr-autopilot` is the first-time publish entry point. `pr-followup`
  resumes after a `pr-autopilot` run has terminated.
