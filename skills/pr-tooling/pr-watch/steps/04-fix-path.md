# Step 04 — Fix path (authored PRs)

Entered from step 03 with a PR number, its `--tails` payload, and the
dispatch set; from a `tick` event at "Drain the push queue"; or from
`pr-watch/steps/07-ci.md` with a CI fix. One PR at a time. Under `dry_run`, every mutation below writes what it would do to
`<scratchpad>/pr-watch-dry-run/<N>.md` instead.

## 1. Gate

From `origin_worktree`:

```
git -C <worktree> fetch origin
git -C <worktree> status --porcelain
git -C <worktree> rev-parse HEAD
git -C <worktree> branch --show-current
```

- The branch is `main` or `master`: stop and escalate. Hard rule.
- The branch is not this PR's recorded `branch` in `watch.json`: stop
  and escalate ("needs you, no comment", reason "worktree checked out
  a different branch than the PR").
- `status --porcelain` prints anything: the user is working there. Post
  "Skipped: uncommitted changes in the worktree." in the PR thread and
  stop. The next event retries.
- `HEAD` differs from the payload's `head`:
  - `git -C <worktree> merge-base --is-ancestor HEAD <head>` succeeds
    (local is behind): `git -C <worktree> merge --ff-only <head>` and
    continue;
  - otherwise post "Skipped: the local branch has diverged from the PR
    head." and stop.

## 2. Relocate and lock

1. `EnterWorktree` with `path` = the PR's worktree.
2. Acquire `<worktree>/.pr-autopilot/pr-<N>.lock` per "Acquiring the
   lock" in `pr-loop-lib/references/state-protocol.md`, using
   `watch.json`'s `session_id`. A fresh lock held by another session
   means `pr-followup` or another watch is active on this PR: return to
   `origin_worktree` with `EnterWorktree` only (the lock is another
   session's; do not run section 9's release), post "Skipped: another
   session holds the PR lock.", stop.
3. Update `pr-<N>.json`: `session_id` = `watch.json`'s `session_id`;
   `head_sha` = the payload `head`; `all_comments` and `actionable` =
   the dispatch set's records; `agent_returns`, `verifier_judgements`,
   `files_changed_this_iteration`, `needs_human_items` = `[]`. Write it
   per "Writing state" in the state protocol, in this same write so a
   resumed watch's first fix never trips G1 on a session id the lock
   protocol had no other reason to refresh.
4. Append a `subagent_dispatch` log event per
   `pr-loop-lib/references/log-format.md`.

## 3. Dispatch and verify

Run `pr-loop-lib/steps/04-dispatch-fixers.md` as written, except:

- Prompt: the defenses text, then `pr-loop-lib/references/fixer-prompt.md`,
  then `pr-watch/references/fixer-addendum.md`. Placeholder and nonce
  substitution covers all three. `{{UI_DEFERRAL_OVERRIDE}}` is `false`.
- Fixers run with `model: "sonnet"`; the verifier with `model: "haiku"`.
- A `ui-deferred` return is demoted to `needs-human` with its reason.
- A `partial` verifier judgement rolls the fixer's files back
  (`git checkout -- <files_changed>`) like `not-addresses`; `pr-watch`
  never pushes a partial fix. The attempted change goes into the
  escalation text.

Then run `pr-loop-lib/steps/04.5-local-verify.md` as written.

## 4. Sort the returns

- `fixed`, `fixed-differently` that survived verification: to section 5.
- `replied`, `not-addressing`: reply only (section 7). If the thread's
  last comment is the user's own and the verdict is `replied` or
  `not-addressing`, post nothing; append that comment's id to
  `settled_ids`.
- `needs-human`: escalate (`pr-watch/steps/06-notify.md`), add the ids to
  `escalated_ids`, post nothing on GitHub.

No returns in section 5: go to section 7, then section 9.

## 5. Commit

1. `git add -- <files_changed of the surviving returns>`.
2. Secret scan the staged diff (`git diff --cached`) with the rules in
   `pr-loop-lib/references/secret-scan-rules.md`. A hit: unstage
   (`git restore --staged -- <files>`), roll the files back, escalate
   ("needs you, no comment", reason "secret scan hit"), go to
   section 9.

   Under `dry_run`, once the diff is staged and clear of the secret
   scan: write `git diff --cached` to
   `<scratchpad>/pr-watch-dry-run/<N>.md`, then
   `git restore --staged -- <files>` and `git checkout -- <files>` to
   leave the worktree as it was, and delete any file the fixer created.
   Go to section 7 (which writes to the same dry-run file instead of
   posting) and then section 9. Steps 3 to 6 below never run under
   `dry_run`.
3. Work item: the first `AB#<digits>` in the PR title, else the PR body,
   else `git log -1 --format=%s`.
4. Write the message to `<scratchpad>/commit-<N>.txt`: one line,
   `AB#<id>: <what changed, lower case after the colon, no period>`, or
   just `<what changed>` when no work item was found. No body, no
   trailer.
5. `git commit -F <scratchpad>/commit-<N>.txt`.
6. `git merge-base --is-ancestor origin/<base> HEAD`. On a non-zero exit,
   `git merge --no-edit origin/<base>`. On a conflict, `git merge --abort`
   and escalate with the conflicting paths and "Fix commit <sha7> is local
   and unpushed.", then go to section 9. After a clean merge that moved
   the branch, run `pr-loop-lib/steps/04.5-local-verify.md` again. If
   that changes any file or fails, do not push: escalate ("needs you,
   no comment", reason "merge with origin/<base> breaks the build; fix
   <sha7> is local and unpushed"), then section 9.

## 6. Push or queue

1. Unless `serialize_pushes` is `false`: for every other `authored` PR `M`
   in `watch.json`, run
   `gh pr checks <M> --repo <SLUG> --json bucket --jq 'map(select(.bucket=="pending")) | length'`.
   Any non-zero count: add `<N>` to `push_queue`, post "Fix committed as
   <sha7>, queued behind #<M> while its checks run.", and go to section 9.
   The replies wait for the drain.
2. `POLL --assert-author <N> --repo <SLUG>`. Non-zero: do not push;
   escalate ("needs you, no comment", reason "push guard refused"),
   go to section 9.
3. `git push origin HEAD:refs/heads/<branch>`. On a non-fast-forward
   rejection: `git fetch origin`, `git merge --no-edit origin/<branch>`,
   then rerun `pr-loop-lib/steps/04.5-local-verify.md`, run the guard
   again, and push once more the same way. Never force. A conflict, a
   04.5 failure, a guard refusal, or a second rejection: escalate
   ("needs you, no comment", with the conflicting paths for a conflict,
   or otherwise the specific reason), then section 9; sections 6.4 to 7
   do not run.
4. Record `last_pushed_head` (`git rev-parse HEAD`) in `watch.json`, and
   `last_push_sha` and `last_push_timestamp` in `pr-<N>.json`.
5. Post "Pushed <sha7>: <what changed>." in the PR thread.

## 7. Reply and resolve

For each return with something to say. A return whose `feedback_id`
starts with `ci:` came from `pr-watch/steps/07-ci.md` and gets no reply
on GitHub.

1. Write the reply from the return's `verdict`, `reason`, `reply_text`
   (facts only), the short sha, and the files, using
   `pr-watch/references/reply-voice.md`. Run its audit and its last step.
2. Thread reply: write `<scratchpad>/reply.json`
   ```json
   {"query": "mutation($t: ID!, $b: String!) { addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $t, body: $b}) { comment { id } } }",
    "variables": {"t": "<thread_id>", "b": "<reply>"}}
   ```
   and run `gh api graphql --input <scratchpad>/reply.json`.
   Top-level reply: the PR's node id from
   `gh pr view <N> --repo <SLUG> --json id --jq .id`, then the same with
   `mutation($s: ID!, $b: String!) { addComment(input: {subjectId: $s, body: $b}) { commentEdge { node { id } } } }`.
3. Append the returned `id` to `posted_reply_ids` and write `watch.json`
   at once. For a top-level item also set `handled_top_level_ids[<id>]`
   to the verdict.
4. Resolve, with
   `mutation($t: ID!) { resolveReviewThread(input: {threadId: $t}) { thread { isResolved } } }`,
   when:
   - the thread was opened by a bot and the verdict is `fixed`,
     `fixed-differently`, `not-addressing` with evidence, or `replied`
     because the code is gone; or
   - a human opened or joined it, asked for something concrete (not a
     question), and the fix was verified.
   Leave it open when the human's latest comment asks a question or sets
   a condition. Never resolve to tidy up.

## 8. Drain the push queue

On a `tick` event, take the first PR `N` in `push_queue`:

1. Section 6 step 1's check for every other authored PR. Any pending
   check: stop; the next `tick` retries. This and a lock held by another
   session (step 3.1) are the only exits that leave `N` in
   `push_queue`; every other exit below, whatever section it happens
   in, ends at step 5.
2. Read the live head:
   `gh pr view <N> --repo <SLUG> --json headRefOid --jq .headRefOid` →
   `<head>`.
3. `git -C <worktree> fetch origin`, then
   `git -C <worktree> rev-list --count origin/<branch>..HEAD`. Above 0
   means a queued commit:
   1. Section 2 steps 1 and 2. If another session holds the lock,
      return as section 2.2 says without its "Skipped" line; `N` stays
      queued and the next `tick` retries.
   2. `git -C <worktree> merge-base --is-ancestor <head> HEAD`. On
      success (the remote is simply behind the queued commit): section
      1's gate, accepting that `HEAD` is ahead of the PR head by the
      queued commit. On failure (the remote moved to a commit the
      queued fix does not contain): section 6.3's merge-and-reverify
      with `origin/<branch>`.
   3. Section 6 steps 2 to 5.
   4. Section 7 for the returns stored in `pr-<N>.json` `agent_returns`.

   Inside the drain, any exit that section 1, 6.3 or 6 would send to
   section 9 comes back here: skip the rest of step 3, run steps 4 and
   5, then section 9. After step 3.4, likewise steps 4 and 5, then
   section 9.
4. For each entry in the PR's `ci_rerun_queued` whose `head` is `<head>`,
   run `POLL --ci-rerun "<link>" --repo <SLUG>` and post the "rerun"
   line (`pr-watch/steps/06-notify.md`); drop the others, their head has
   been replaced. Set `ci_rerun_queued` to `[]`.
5. Remove `N` from `push_queue` and write `watch.json`. When step 3 did
   not reach a completed push (the gate skipped, a merge conflicted, the
   push guard refused, or a second push rejection was not resolved),
   escalate here instead of repeating that step's own "Skipped" line
   ("needs you, no comment", reason "queued fix <sha7> could not be
   pushed", `<sha7>` the local `HEAD` before this drain).

One drained PR per `tick`.

## 9. Release and return

1. Release the lock: `rm -rf <worktree>/.pr-autopilot/pr-<N>.lock`, and
   log `lock_released`.
2. `EnterWorktree` with `path` = `origin_worktree` from `watch.json`.
