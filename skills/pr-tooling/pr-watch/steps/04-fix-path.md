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
- `status --porcelain` prints anything: the user is working there. Skip
  with reason "uncommitted changes in the worktree" and stop.
- `HEAD` differs from the payload's `head`:
  - `git -C <worktree> merge-base --is-ancestor HEAD <head>` succeeds
    (local is behind): `git -C <worktree> merge --ff-only <head>` and
    continue;
  - otherwise skip with reason "the local branch has diverged from the
    PR head" and stop.

Then, for a fix entered from step 03 (not from `pr-watch/steps/07-ci.md`
and not from the drain):

- the payload `head` is not `last_pushed_head`, or any record in the
  dispatch set has an `author_type` other than `Bot`: set
  `review_fix_pushes` to 0 and write `watch.json`;
- otherwise, when `review_fix_pushes` is `3`: escalate ("needs you, no
  comment", reason "bot findings keep coming after 3 fix pushes") and
  stop. A human comment or a push the watch did not make clears it.

To skip with a reason:

1. Set the PR's `retry_after` in `watch.json` to now + 600, in epoch
   seconds (`python -c "import time; print(int(time.time()) + 600)"`).
2. If the PR's `skip_reason` is not this reason, post "Skipped: <reason>.
   Retrying in 10 minutes." in the PR thread and set `skip_reason` to the
   reason.
3. Write `watch.json`. Once `retry_after` passes, the poller re-emits
   the PR's pending set and its red checks.

## 2. Relocate and lock

1. `EnterWorktree` with `path` = the PR's worktree.
2. Acquire `<worktree>/.pr-autopilot/pr-<N>.lock` per "Acquiring the
   lock" in `pr-loop-lib/references/state-protocol.md`, using
   `watch.json`'s `session_id`. A fresh lock held by another session
   means `pr-followup` or another watch is active on this PR: return to
   `origin_worktree` with `EnterWorktree` only (the lock is another
   session's; do not run section 9's release), skip with reason "another
   session holds the PR lock" (section 1), and stop. Once the lock is
   held, set the PR's `skip_reason` to null if it is set and write
   `watch.json`.
3. Resync the library state file:
   - 3a. Set `pr-<N>.json` `session_id` to `watch.json`'s `session_id`
     and write it at once per "Writing state" in the state protocol, so
     G1 never trips on a session id the lock protocol had no other
     reason to refresh.
   - 3b. Update `pr-<N>.json`: `head_sha` = the payload `head`;
     `all_comments` and `actionable` = the dispatch set's records;
     `agent_returns`, `verifier_judgements`,
     `files_changed_this_iteration`, `needs_human_items` = `[]`. Write it
     the same way.
4. Append a `subagent_dispatch` log event per
   `pr-loop-lib/references/log-format.md`.

The fix path from step 03 and `pr-watch/steps/07-ci.md` section 5 run
steps 1, 2, 3a, 3b, and 4. The formatter (`pr-watch/steps/07-ci.md`
section 4) runs steps 1, 2, 3a, and 3b with an empty dispatch set, so
`all_comments`, `actionable`, and `agent_returns` are `[]` and a drain of
its commit replies to nothing. Only the drain (section 8) runs steps 1,
2, and 3a without 3b; 3b would erase the `agent_returns` it replies from.

## 3. Dispatch and verify

Run `pr-loop-lib/steps/04-dispatch-fixers.md` as written, except:

- Prompt: the defenses text, then `pr-loop-lib/references/fixer-prompt.md`,
  then `pr-watch/references/fixer-addendum.md`. Placeholder and nonce
  substitution covers all three. `{{UI_DEFERRAL_OVERRIDE}}` is `false`.
- Fixers run with `model: "sonnet"`; the verifier with `model: "haiku"`.
- A `ui-deferred` return is demoted to `needs-human` with its reason.
- A `partial` or `not-addresses` verifier judgement rolls the fixer's
  `files_changed` back with section 10, in place of the library's own
  `git checkout`; `pr-watch` never pushes a partial fix. The attempted
  change goes into the escalation text.

Then run `pr-loop-lib/steps/04.5-local-verify.md` as written.

## 4. Sort the returns

- `fixed`, `fixed-differently` that survived verification: to section 5.
- `replied`, `not-addressing`: reply only (section 7). If the thread's
  last comment is the user's own and the verdict is `replied` or
  `not-addressing`, post nothing; append that comment's id to
  `settled_ids`.
- `needs-human`: escalate (`pr-watch/steps/06-notify.md`), add the ids to
  `escalated_ids`, post nothing on GitHub. For a top-level item also set
  `handled_top_level_ids[<item id>] = "escalated"`.

No returns in section 5: go to section 7, then section 9.

## 5. Commit

1. `git add -- <files_changed of the surviving returns>`.
2. Secret scan the staged diff (`git diff --cached`) with the rules in
   `pr-loop-lib/references/secret-scan-rules.md`. A hit: unstage
   (`git restore --staged -- <files>`), roll the files back with
   section 10, escalate ("needs you, no comment", reason "secret scan
   hit"), go to section 9.

   Under `dry_run`, once the diff is staged and clear of the secret
   scan: write `git diff --cached` to
   `<scratchpad>/pr-watch-dry-run/<N>.md`, then
   `git restore --staged -- <files>` and roll the files back with
   section 10 to leave the worktree as it was.
   Go to section 7 (which writes to the same dry-run file instead of
   posting) and then section 9. Steps 3 to 6 below never run under
   `dry_run`.

   Nothing is committed, so there is no sha for section 7 step 1 to put
   in a `Fixed.` reply. Write `<no sha: dry run>` where the sha would go
   and keep the rest of the shape; the point of the dry-run file is to
   show the reply that would be posted, and a reply missing its sha
   clause would not show it. `pr-watch/references/reply-voice.md` takes
   the placeholder in the sha's place, in the shape and in its audit.
3. Work item: the first `AB#<digits>` in the PR title, else the PR body,
   else `git log -1 --format=%s`.
4. Write the message to `<scratchpad>/commit-<N>.txt`: one line,
   `AB#<id>: <what changed, lower case after the colon, no period>`, or
   just `<what changed>` when no work item was found. No body, no
   trailer.
5. `git commit -F <scratchpad>/commit-<N>.txt`. When the fix came from
   step 03 and no record in the dispatch set was human-authored, add 1 to
   `review_fix_pushes` and write `watch.json`; a queued commit counts too.
6. `git merge-base --is-ancestor origin/<base> HEAD`. On a non-zero exit,
   `git merge --no-edit origin/<base>`. On a conflict, `git merge --abort`
   and escalate with the conflicting paths and "Fix commit <sha7> is local
   and unpushed.", then go to section 9. After a clean merge that moved
   the branch, run `pr-loop-lib/steps/04.5-local-verify.md` again. If
   that changes any file or fails, do not push: escalate ("needs you,
   no comment", reason "merge with origin/<base> breaks the build; fix
   <sha7> is local and unpushed"), then section 9. The merge needs no
   second secret scan: it brings in only commits already on the remote,
   and a conflict aborts rather than being resolved, so the fixer's
   commit, scanned in step 2, is the only new content pushed.

## 6. Push or queue

1. Unless `serialize_pushes` is `false`, run the pending-check scan for
   every other `authored` PR `M` in `watch.json`:
   `gh pr checks <M> --repo <SLUG> --required --json bucket --jq 'map(select(.bucket=="pending")) | length'`.
   A non-zero exit counts as 0. When its stderr says neither "no
   required checks reported" nor "no checks reported", also post "Could
   not read #<M>'s checks: <first stderr line>." in the PR thread, once
   per scan.
   Any count above 0: set the PR's `queued_head` to
   `git -C <worktree> rev-parse HEAD` and `queued_at` to now (epoch
   seconds), add `<N>` to `push_queue`, write `watch.json`, post "Fix
   committed as <sha7>, queued behind #<M> while its checks run.", and go
   to section 9. The replies wait for the drain.
2. `POLL --assert-author <N> --repo <SLUG>`. Non-zero: do not push;
   escalate ("needs you, no comment", reason "push guard refused"),
   go to section 9.
3. `git push origin HEAD:refs/heads/<branch>`. On a non-fast-forward
   rejection: `git fetch origin`, `git merge --no-edit origin/<branch>`,
   then rerun `pr-loop-lib/steps/04.5-local-verify.md`, run the guard
   again, and push once more the same way. Never force. A conflict
   (after `git merge --abort`), a 04.5 failure, a guard refusal, or a
   second rejection: escalate ("needs you, no comment", with the
   conflicting paths for a conflict, or otherwise the specific reason),
   then section 9; sections 6.4 to 7 do not run. The merge needs no second secret scan: it brings in only
   commits already on the remote, and a conflict aborts rather than being
   resolved, so the fixer's commit, scanned in section 5 step 2, is the
   only new content pushed.
4. Record `last_pushed_head` (`git rev-parse HEAD`) in `watch.json`, and
   `last_push_sha` and `last_push_timestamp` in `pr-<N>.json`.
5. Post "Pushed <sha7>: <what changed>." in the PR thread.

## 7. Reply and resolve

For each return with something to say. A return whose `feedback_id`
starts with `ci:` came from `pr-watch/steps/07-ci.md` and gets no reply
on GitHub.

Before the first reply or resolve of a pass, run
`POLL --assert-author <N> --repo <SLUG>`. Non-zero: post nothing,
escalate ("needs you, no comment", reason "reply guard refused"), and go
to section 9.

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
   A reply mutation that exits non-zero or returns no `id`: append
   nothing, escalate ("needs you, no comment", reason "reply failed on
   <thread path:line, or the top-level item's id>"), and continue with
   the next return; steps 3 and 4 do not run for this one. Under
   `dry_run` no mutation runs, so this failure branch does not apply:
   the mutation goes to the dry-run file, step 3 has no id to append,
   and step 4 runs.
3. Append the posted reply's returned `id` to `posted_reply_ids` and
   write `watch.json` at once. For a top-level item also set
   `handled_top_level_ids[<record id>]` to the verdict, where
   `<record id>` is the id of the answered item (the return's record
   id), never the id of the reply just posted.
4. Resolve, with
   `mutation($t: ID!) { resolveReviewThread(input: {threadId: $t}) { thread { isResolved } } }`,
   when:
   - the thread was opened by a bot and the verdict is `fixed`,
     `fixed-differently`, `not-addressing` with evidence, or `replied`
     because the code is gone; or
   - a human opened or joined it asking for a change, and the fix was
     verified. Most review comments ask for their change as a question
     ("can we make this checked?", "should this be nullable?"); a
     question mark does not make it one to leave open.
   Leave it open when the human's latest comment asks for an answer
   rather than a change, or sets a condition on one. Never resolve to
   tidy up. A resolve that exits non-zero
   or does not return `isResolved: true`: post the "resolve failed" line
   (`pr-watch/steps/06-notify.md`) in the PR thread and continue with the
   next return. Under `dry_run` the resolve goes to the dry-run file and
   this failure branch does not apply.

## 8. Drain the push queue

On a `tick` event, take the first PR `N` in `push_queue`:

1. The pending-check scan of section 6 step 1 (the command, with a
   non-zero exit counted as 0 and nothing posted) for every other
   authored PR. Any pending check on PR `M`: when now - `queued_at` is
   below 3600, stop; the next `tick` retries. At 3600 or more: when the
   PR's `wait_notice_at` is not `queued_at`, post "Stopped waiting for
   #<M>'s checks after an hour.", set `wait_notice_at` to `queued_at`, and
   write `watch.json`; then continue with step 2. A stop here and a lock
   held by another session (step 3.3) are the only exits that leave `N`
   in `push_queue`; every other exit below, whatever section it happens
   in, ends at step 5.
2. Read the live head:
   `gh pr view <N> --repo <SLUG> --json headRefOid --jq .headRefOid` →
   `<head>`.
3. A queued commit exists only when the PR's `queued_head` is set. When
   it is not set, skip this step entirely: push nothing and run nothing
   in the worktree. Otherwise:
   1. `git -C <worktree> rev-parse HEAD`. When it is not `queued_head`,
      push nothing: escalate ("needs you, no comment", reason "the
      worktree has commits the watch did not make; queued fix <sha7 of
      queued_head> not pushed") and continue at step 4.
   2. `git -C <worktree> fetch origin`.
   3. Section 2 steps 1, 2, and 3a. If another session holds the lock,
      return as section 2.2 says, without its skip; `N` stays queued and
      the next `tick` retries.
   4. Run section 1's branch checks and its `status --porcelain` check
      before either branch below. Then
      `git -C <worktree> merge-base --is-ancestor <head> HEAD`. On
      success (the remote is simply behind the queued commit): go
      straight to step 3.5. Section 1's `HEAD`-versus-`head` check does
      not run here: step 3.1 already proved `HEAD` is `queued_head`, so
      `HEAD` being ahead of `<head>` is the expected state. A branch or
      `status --porcelain` failure above posts no "Skipped" line; step 5
      escalates instead. On failure (the remote moved to a commit the
      queued fix does not contain): section 6.3's merge-and-reverify
      with `origin/<branch>`.
   5. Section 6 steps 2 to 5.
   6. Section 7 for the returns stored in `pr-<N>.json` `agent_returns`.

   Inside the drain, any exit that section 1, 6.3, 6, 7, or 10 would
   send to section 9 comes back here: skip the rest of step 3, run steps
   4 and 5, then section 9. After step 3.6, likewise steps 4 and 5, then
   section 9.
4. In the entries below, `<check>` is the entry's `name`, or its `link`
   when it has no `name`. For each entry in the PR's `ci_rerun_queued`
   whose `head` is `<head>`, run
   `POLL --ci-rerun "<link>" --repo <SLUG> --state-dir <STATE_DIR>` and
   post the "CI rerun" line (`pr-watch/steps/06-notify.md`) with its
   output; a non-zero exit escalates ("CI needs you") with its stderr
   line, then removes the entry's `sibling_keys` from `ci_reruns` and
   from `ci_handled` (absent on an entry from an older state file:
   nothing removed), so section 2 of `pr-watch/steps/07-ci.md` handles
   them on their own next occurrence; the drain continues. Under
   `dry_run`, write that exact `POLL --ci-rerun` command to
   `<scratchpad>/pr-watch-dry-run/<N>.md` instead of running it. Every
   other entry's head has been replaced: post "Rerun of <check> dropped:
   the PR head moved before it ran." (the "CI rerun dropped" line) for
   each. Set `ci_rerun_queued` to `[]`.
5. Finish the drain:
   1. Only when step 3 got past step 3.1 and did not reach a completed
      push (the gate skipped, a merge conflicted, the push guard refused,
      or a second push rejection was not resolved): escalate ("needs you,
      no comment", reason "queued fix <sha7> could not be pushed",
      `<sha7>` from `queued_head`).
   2. Always, except after step 3.3's lock-held return, where `N` stays
      queued. Whether step 3 pushed, escalated, or did not run: remove
      `N` from `push_queue`, set `queued_head`, `queued_at`, and
      `wait_notice_at` to null, and write `watch.json`.

One drained PR per `tick`. Section 9 runs only when step 3.3 took the
lock.

## 9. Release and return

1. Release the lock: `rm -rf <worktree>/.pr-autopilot/pr-<N>.lock`, and
   log `lock_released`.
2. `EnterWorktree` with `path` = `origin_worktree` from `watch.json`.

## 10. Roll back

The caller names the files to roll back.

1. For each path, `git -C <worktree> ls-files --error-unmatch -- <path>`.
   Exit 0: the path is tracked. Any other exit: when
   `git -C <worktree> check-ignore -q -- <path>` exits non-zero, delete
   the file; when it exits 0 (an ignored file git cannot restore), leave
   it and escalate ("needs you, no comment", reason "rollback cannot
   restore ignored file <path>").
2. When any path is tracked, `git -C <worktree> checkout -- <tracked paths>`
   as one command.
3. `git -C <worktree> status --porcelain -- <the rolled-back paths>` must
   print nothing. If it prints anything, escalate ("needs you, no
   comment", reason "rollback left changes in the worktree") and go to
   section 9. Changes to other paths are not this rollback's.
