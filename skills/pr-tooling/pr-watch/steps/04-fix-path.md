# Step 04 — Fix path (authored PRs)

Entered from step 03 with the PR key `owner/repo#N`, its `--tails`
payload, and the dispatch set; from a `tick` event at "Drain the push
queue"; from `pr-watch/steps/07-ci.md` with a CI fix; or from
`pr-watch/steps/03-route-event.md` section H or
`pr-watch/steps/08-review-ask.md` for a base update (section 11). One PR
at a time. Under `dry_run`, every mutation below writes what it would do to
`<scratchpad>/pr-watch-dry-run/<owner>-<repo>-<N>.md` instead.

The key gives `<owner>/<repo>` and `<N>`; every `--repo` below is
`<owner>/<repo>`. `<worktree>` is the PR's `worktree` in `watch.json`.
Every per-PR field named below (`retry_after`, `skip_reason`,
`review_fix_pushes`, `last_pushed_head`, `queued_head`, `posted_reply_ids`,
`escalated_ids`, and the rest) is read from and written to the PR's
progress file (`pr-watch/steps/03-route-event.md`, "State has two
homes"); "write the progress file" means placing it with `state_put.py`.
`status` and `push_queue` are written to `watch.json`.

`<key>` is the PR key `owner/repo#N`. The library's state file and lock
are `<worktree>/.pr-autopilot/pr-<N>.json` and
`<worktree>/.pr-autopilot/pr-<N>.lock`; `pr-<N>.json` below means that
file.

The PR is a launch-repo PR when
`git -C <origin_worktree> rev-parse --path-format=absolute --git-common-dir`
and the same command on `<worktree>` print the same path; otherwise it is
an other-repo PR. An other-repo PR is never relocated to: the session
stays where it is, its files are edited with absolute paths under
`<worktree>`, and every git command names `git -C <worktree>`. They are
written that way below for both cases. `origin_worktree` is where the
session stood when it armed, which is not always the repo it was
launched in; when `EnterWorktree` refuses a launch-repo PR's worktree
(section 2 step 1), handle the PR as an other-repo PR for the rest of
this pass.

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
  `review_fix_pushes` to 0, `cap_notified_head` to null, and write the
  progress file;
- otherwise, when `review_fix_pushes` is `3`: escalate ("needs you, no
  comment", reason "bot findings keep coming after 3 fix pushes"), add
  the dispatch set's ids to `escalated_ids`, set `cap_notified_head` to
  the payload `head`, write the progress file, and stop. A human comment or a
  push the watch did not make clears it; a human comment that never
  reaches this section is cleared by `pr-watch/steps/03-route-event.md`
  A.7 instead.
  When `cap_notified_head` already is that head, do all of it except the
  escalation: the user has the message, and nothing the message is about
  can have changed, because the cap is what stops the push that would
  change it. Otherwise a bot that re-reviews on its own schedule buys the
  user one notification per round for one situation.

To skip with a reason:

1. Set the PR's `retry_after` to now + 600, in epoch
   seconds (`python -c "import time; print(int(time.time()) + 600)"`).
2. If the PR's `skip_reason` is not this reason, post "Skipped: <reason>.
   Retrying in 10 minutes." in the PR thread and set `skip_reason` to the
   reason.
3. Write the progress file. Once `retry_after` passes, the poller re-emits
   the PR's pending set and its red checks.

## 2. Relocate and lock

1. A launch-repo PR: `EnterWorktree` with `path` = the PR's worktree.
   When it refuses, the PR is an other-repo PR from here on.
   An other-repo PR: nothing; the session stays where it is.
2. Acquire `<worktree>/.pr-autopilot/pr-<N>.lock` per "Acquiring the
   lock" in `pr-loop-lib/references/state-protocol.md`, using
   `watch.json`'s `session_id`. The lease already keeps every other
   watch off this PR, so a fresh lock held by another session means
   `pr-followup` or `pr-autopilot` is active on it: for a launch-repo PR
   return to `origin_worktree` with `EnterWorktree` only (the lock is
   another session's; do not run section 9's release), skip with reason
   "another session holds the PR lock" (section 1), and stop. Once the
   lock is held, set the PR's `skip_reason` to null if it is set and
   write the progress file.
3. Resync the library state file:
   - 3a. Set `pr-<N>.json` `session_id` to `watch.json`'s `session_id`
     and write it at once per "Writing state" in the state protocol, so
     G1 never trips on a session id the lock protocol had no other
     reason to refresh. Compose it in the scratchpad and place it with
     `state_put.py` (`pr-watch/references/watch-state-schema.md`,
     "Writing"): the Write tool refuses an other-repo worktree.
   - 3b. Update `pr-<N>.json`: `head_sha` = the payload `head`;
     `all_comments` and `actionable` = the dispatch set's records;
     `agent_returns`, `verifier_judgements`,
     `files_changed_this_iteration`, `needs_human_items` = `[]`. Place it
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
- The worktree root is `<worktree>`: pass it to
  `pr-loop-lib/steps/04-dispatch-fixers.md` and
  `pr-loop-lib/steps/04.5-local-verify.md`, so `{{WORKTREE_ROOT}}` in the
  prompts, the `files_changed` check, and the local build and test all
  resolve to it.
- Fixers run with `model: "sonnet"`; the verifier with `model: "haiku"`.
- Append to every fixer brief a block headed `PR diff stat:` holding the
  output of `git -C <worktree> diff origin/<base>...HEAD --stat`. The
  addendum's check b reads it, because a fixer's `git diff *` permission
  does not match `git -C`.
- An other-repo PR: also append "The repository is at `<worktree>`, not
  your working directory. Read it with Read, Grep, and Glob on absolute
  paths under it. Run no git command, whatever the prompt above says
  about `git -C`; check b uses the PR diff stat above."
- A `ui-deferred` return is demoted to `needs-human` with its reason.
- A `partial` or `not-addresses` verifier judgement rolls the fixer's
  `files_changed` back with section 10, in place of the library's own
  `git checkout`; `pr-watch` never pushes a partial fix. The attempted
  change goes into the escalation text.

Then run `pr-loop-lib/steps/04.5-local-verify.md` as written, unless a
return carries `suspicious: true`. Local verify builds and runs whatever
stands in the worktree, and that flag is the one case where what stands
there is distrusted, so it must not be built or run: skip the verify and
take the suspicious branch at once. For a `ci:` record that is
`pr-watch/steps/07-ci.md` section 5 step 4. For any other record it is
the same shape: escalate ("needs you, no comment", reason "fixer refused
the dispatch: <the fixer's reason>"), add the record's ids to
`escalated_ids` and, for a top-level item, set
`handled_top_level_ids[<item id>] = "escalated"` — without that the same
feedback is pending again on the next poll and goes back to a fixer, so
the refusal would be a pause rather than the end of it — roll back with
section 10 over every path `git -C <worktree> status --porcelain` and
`git -C <worktree> ls-files --others --exclude-standard` name rather than
the return's `files_changed`, then section 9.

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

1. `git -C <worktree> add -- <files_changed of the surviving returns>`.
2. Secret scan the staged diff (`git -C <worktree> diff --cached`) with the rules in
   `pr-loop-lib/references/secret-scan-rules.md`. A hit: unstage
   (`git -C <worktree> restore --staged -- <files>`), roll the files back with
   section 10, escalate ("needs you, no comment", reason "secret scan
   hit"), go to section 9.

   Under `dry_run`, once the diff is staged and clear of the secret
   scan: write `git -C <worktree> diff --cached` to
   `<scratchpad>/pr-watch-dry-run/<owner>-<repo>-<N>.md`, then
   `git -C <worktree> restore --staged -- <files>` and roll the files back with
   section 10 to leave the worktree as it was.
   Go to section 7 (which writes to the same dry-run file instead of
   posting) and then section 9. Steps 3 to 6 below never run under
   `dry_run`.

   Nothing is committed, so there is no sha for section 7 step 1 to put
   in a `Fixed.` reply. Write `<no sha: dry run>` where the sha would go
   and keep the rest of the shape; the point of the dry-run file is to
   show the reply that would be posted, and a reply missing its sha
   clause would not show it. `pr-watch/references/reply-contract.md` takes
   the placeholder in the sha's place, in the shape and in its audit.
3. Work item: the first `AB#<digits>` in the PR title, else the PR body,
   else `git -C <worktree> log -1 --format=%s`.
4. Write the message to `<scratchpad>/commit-<N>.txt`: one line,
   `AB#<id>: <what changed, lower case after the colon, no period>`, or
   just `<what changed>` when no work item was found. No body, no
   trailer.
5. `git -C <worktree> commit -F <scratchpad>/commit-<N>.txt`. When the
   fix came from step 03 and no record in the dispatch set was
   human-authored, add 1 to `review_fix_pushes` and write the progress
   file; a queued commit counts too.
6. `git -C <worktree> merge-base --is-ancestor origin/<base> HEAD`. On a
   non-zero exit, `git -C <worktree> merge --no-edit origin/<base>`. On a
   conflict, `git -C <worktree> merge --abort`
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

1. Unless `serialize_pushes` is `false`, run the pending-check scan under
   the repo's push lock. Under `dry_run` take no lock (nothing under
   `prs/` is written in a rehearsal); `busy` cannot occur there.
   - Take the lock: `POLL --push-lock take <key> --session-dir <SESSION_DIR>`.
     Exit 0 prints `taken`. A non-zero exit prints `busy`: another push
     or rerun in `<owner>/<repo>` holds it. `busy` queues the PR exactly
     as a pending check does.
   - The PR set: the `authored` entries of `watch.json` `prs` whose
     `status` is `armed` and whose repo is `<owner>/<repo>`, plus the
     keys `POLL --repo-peers <key>` prints, without this PR and without
     duplicates. Never a PR in another repo.
   - For each such PR `M`:
     `gh pr checks <M's number> --repo <owner>/<repo> --required --json bucket --jq 'map(select(.bucket=="pending")) | length'`.
   A non-zero exit counts as 0. When its stderr says neither "no
   required checks reported" nor "no checks reported", also post "Could
   not read #<M>'s checks: <first stderr line>." in the PR thread, once
   per scan.
   Any count above 0, or `busy`: set the PR's `queued_head` to
   `git -C <worktree> rev-parse HEAD` and `queued_at` to now (epoch
   seconds) in the progress file, add `<key>` to `push_queue`, write the
   progress file and `watch.json`, release the lock when this step took
   it (`POLL --push-lock release <key> --session-dir <SESSION_DIR>`), post the "queued" line
   (`pr-watch/steps/06-notify.md`; its "queued (busy)" row for `busy`),
   and go to section 9. The replies wait for the drain.
2. `POLL --assert-author <N> --repo <owner>/<repo>`. Non-zero: do not push;
   escalate ("needs you, no comment", reason "push guard refused"),
   go to section 9.
3. When this section or the drain's scan holds the push lock, run
   `POLL --push-lock take <key> --session-dir <SESSION_DIR>` first. It
   refreshes the lock this session holds, so the push and the wait in
   step 6 fit inside the 300-second stale window. `busy` there means the
   lock went stale and another session took it: queue as step 1's `busy`
   does, without releasing a lock this session no longer holds.
   `git -C <worktree> push origin HEAD:refs/heads/<branch>`. On a
   non-fast-forward rejection: `git -C <worktree> fetch origin`,
   `git -C <worktree> merge --no-edit origin/<branch>`,
   then rerun `pr-loop-lib/steps/04.5-local-verify.md`, run the guard
   again, and push once more the same way. Release the push lock
   before the re-verify, and run step 1 again after it, before the
   second push; a queue there ends in section 9 with the merge
   committed locally and `queued_head` set to the new `HEAD`. Inside
   the drain that rescan follows drain step 1's rules instead: the hour
   rule applies and nothing is posted, and a stop there releases the
   lock, sets `queued_head` to the new `HEAD`, leaves `queued_at`
   unchanged, writes the progress file, and ends in section 9 with `N`
   still queued, running
   neither drain step 4 nor step 5. Never
   force. A conflict
   (after `git -C <worktree> merge --abort`), a 04.5 failure, a guard refusal, or a
   second rejection: escalate ("needs you, no comment", with the
   conflicting paths for a conflict, or otherwise the specific reason),
   then section 9; sections 6.4 to 7 do not run. The merge needs no second secret scan: it brings in only
   commits already on the remote, and a conflict aborts rather than being
   resolved, so the fixer's commit, scanned in section 5 step 2, is the
   only new content pushed.
4. Record `last_pushed_head` (`git -C <worktree> rev-parse HEAD`) in the
   progress file, and `last_push_sha` and `last_push_timestamp` in
   `pr-<N>.json` (placed with `state_put.py`).
5. Post "Pushed <sha7>: <what changed>." in the PR thread.
6. Release the push lock when this section or the drain's scan took it:
   one foreground `python` loop, run with a timeout of at least 180000
   ms, reads
   `gh pr checks <N> --repo <owner>/<repo> --required --json bucket --jq 'map(select(.bucket=="pending")) | length'`
   every 10 seconds (a failed read counts as 0) and ends when the count
   is above 0 or 120 seconds have passed since the push or rerun; then
   `POLL --push-lock release <key> --session-dir <SESSION_DIR>`. That count is the one other sessions'
   scans read, and it turns on for a rerun as it does for a push. A
   rerun that took the lock is held and released the same way. Every
   exit that took the lock and pushed nothing releases it at once,
   through section 9.

## 7. Reply and resolve

For each return with something to say. A return whose `feedback_id`
starts with `ci:` came from `pr-watch/steps/07-ci.md` and gets no reply
on GitHub. A return whose `feedback_id` starts with `slack:` came from a
Slack thread reply (`pr-watch/steps/03-route-event.md` section I): its
reply goes to the PR's Slack thread through `pr-watch/steps/06-notify.md`
("Slack reply answer"), never to GitHub, and steps 2 to 4 below do not run
for it beyond setting `handled_top_level_ids[<record id>]` to the verdict
once the post succeeded. The drain's step 3.6 runs this section, so the
same carve-out applies there.

Before the first reply or resolve of a pass, run
`POLL --assert-author <N> --repo <owner>/<repo>` (not for a `slack:` return, which posts
only to Slack and needs no GitHub author check). Non-zero: post nothing,
escalate ("needs you, no comment", reason "reply guard refused"), and go
to section 9.

1. Write the reply from the return's `verdict`, `reason`, `reply_text`
   (facts only), the short sha, and the files, following Writing a reply
   in `pr-watch/references/reply-contract.md`. Post only the reply text.
2. Thread reply: write `<scratchpad>/reply.json`
   ```json
   {"query": "mutation($t: ID!, $b: String!) { addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $t, body: $b}) { comment { id } } }",
    "variables": {"t": "<thread_id>", "b": "<reply>"}}
   ```
   and run `gh api graphql --input <scratchpad>/reply.json`.
   Top-level reply: the PR's node id from
   `gh pr view <N> --repo <owner>/<repo> --json id --jq .id`, then the same with
   `mutation($s: ID!, $b: String!) { addComment(input: {subjectId: $s, body: $b}) { commentEdge { node { id } } } }`.
   A reply mutation that exits non-zero or returns no `id`: append
   nothing, escalate ("needs you, no comment", reason "reply failed on
   <thread path:line, or the top-level item's id>"), and continue with
   the next return; steps 3 and 4 do not run for this one. Under
   `dry_run` no mutation runs, so this failure branch does not apply:
   the mutation goes to the dry-run file, step 3 has no id to append,
   and step 4 runs.
3. Append the posted reply's returned `id` to `posted_reply_ids` and
   write the progress file at once. For a top-level item also set
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

On a `tick` event, first drop from `push_queue` every key whose entry in
`watch.json` `prs` is not `armed`, and write `watch.json` when any was
dropped. Then take the first remaining key; `<owner>/<repo>` and `N` come
from it. When step 1 stops it, or step 3.3 returns, take the next key
whose repo is not one already stopped in this drain and start again at
step 1 (first in line within a repo); when none is left, the tick ends. At most one PR is
drained per `tick`:

1. The pending-check scan of section 6 step 1 as that step defines it
   (its PR set, its push lock, its `busy` rule), with a non-zero exit
   of a `gh pr checks` count counted as 0 and nothing posted. Any pending check on PR `M`, or
   `busy`: when now - `queued_at` is below 3600, release the lock when
   the scan took it and stop this key; the next `tick` retries. At 3600
   or more: when the PR's `wait_notice_at` is not `queued_at`, post the
   "stopped waiting" line (`pr-watch/steps/06-notify.md`; its "stopped
   waiting (busy)" row for `busy`), set
   `wait_notice_at` to `queued_at`, and write the progress file; then
   continue with step 2. A stop here, a PR lock held by another
   session (step 3.3), and a stop in section 6.3's rescan are the only
   exits that leave `N` in `push_queue`;
   every other exit below, whatever section it happens in, ends at
   step 5.
2. Read the live head:
   `gh pr view <N> --repo <owner>/<repo> --json headRefOid --jq .headRefOid` →
   `<head>`.
3. A queued commit exists only when the PR's `queued_head` is set. When
   it is not set, skip this step entirely: push nothing and run nothing
   in the worktree. Otherwise:
   1. `git -C <worktree> rev-parse HEAD`. When it is not `queued_head`,
      push nothing: escalate ("needs you, no comment") and continue at
      step 4. The reason depends on
      `git -C <worktree> cat-file -e <queued_head>^{commit}`: when it
      fails, the fix was committed in another clone, by the session that
      held this PR before a takeover (`pr-watch/steps/01-discover.md`
      §5), so the reason is "queued fix <sha7 of queued_head> was
      committed in another clone by the session that held this PR
      before; it is not in <worktree> and was not pushed"; otherwise it is
      "the worktree has commits the watch did not make; queued fix <sha7
      of queued_head> not pushed".
   2. `git -C <worktree> fetch origin`.
   3. Section 2 steps 1, 2, and 3a. If another session holds the lock,
      release the push lock when step 1 took it, then return as
      section 2.2 says, without its skip; `N` stays queued and the next
      `tick` retries.
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
   5. Section 6 steps 2 to 6.
   6. Section 7 for the returns stored in `pr-<N>.json` `agent_returns`.

   Inside the drain, any exit that section 1, 6.3, 6, 7, or 10 would
   send to section 9 comes back here: skip the rest of step 3, run steps
   4 and 5, then section 9, except the section 6.3 rescan stop above.
   After step 3.6, likewise steps 4 and 5, then section 9.
4. In the entries below, `<check>` is the entry's `name`, or its `link`
   when it has no `name`. When step 3 pushed, `<head>` is stale: treat
   every entry as replaced. Otherwise, for each entry in the PR's
   `ci_rerun_queued` whose `head` is `<head>`, run
   `POLL --ci-rerun "<link>" --repo <owner>/<repo> --session-dir <SESSION_DIR>` and
   post the "CI rerun" line (`pr-watch/steps/06-notify.md`) with its
   output; a non-zero exit escalates ("CI needs you") with its stderr
   line, then removes the entry's `sibling_keys` from `ci_reruns` and
   from `ci_handled` (absent on an entry from an older state file:
   nothing removed), so section 2 of `pr-watch/steps/07-ci.md` handles
   them on their own next occurrence; the drain continues. Under
   `dry_run`, write that exact `POLL --ci-rerun` command to
   `<scratchpad>/pr-watch-dry-run/<owner>-<repo>-<N>.md` instead of running it. Every
   other entry's head has been replaced: post "Rerun of <check> dropped:
   the PR head moved before it ran." (the "CI rerun dropped" line) for
   each. Set `ci_rerun_queued` to `[]`. After a rerun that started, wait
   and release the push lock as section 6 step 6 does.
5. Finish the drain:
   1. Only when step 3 got past step 3.1 and did not reach a completed
      push (the gate skipped, a merge conflicted, the push guard refused,
      or a second push rejection was not resolved): escalate ("needs you,
      no comment", reason "queued fix <sha7> could not be pushed",
      `<sha7>` from `queued_head`).
   2. Always, except after step 3.3's lock-held return and section 6.3's
      rescan stop, where `N` stays queued. Whether step 3 pushed, escalated, or did not run: remove
      `N`'s key from `push_queue`, set `queued_head`, `queued_at`, and
      `wait_notice_at` to null, write the progress file and `watch.json`,
      and release the push lock when this drain still holds it.

One drained PR per `tick`. Section 9 runs only when step 3.3 took the
lock.

## 9. Release and return

1. Release the lock: `rm -rf <worktree>/.pr-autopilot/pr-<N>.lock`, and
   log `lock_released`.
2. Release the push lock when this pass took it and section 6 step 6
   has not (`POLL --push-lock release <key> --session-dir <SESSION_DIR>`; it releases only a lock this
   session holds, so it is harmless when none is). Not under `dry_run`.
3. A launch-repo PR: `EnterWorktree` with `path` = `origin_worktree`
   from `watch.json`. An other-repo PR: nothing; the session never
   left.

## 10. Roll back

The caller names the files to roll back, as paths relative to
`<worktree>`.

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

## 11. Base update

Brings an `authored` PR's branch up to date with its base and pushes that
merge. There is no fix, no reply and no thread to resolve, and the push
does not count toward `review_fix_pushes`. `<base>` is the PR's
`baseRefName`. The section ends with one outcome, which its caller reads:
`skipped`, `up-to-date`, `rehearsed`, `conflicting`, `escalated`,
`queued` or `pushed`.

1. Section 2 steps 1, 2, 3a and 3b, with an empty dispatch set as the
   formatter runs them, so a drain of a queued merge replies to nothing.
   When section 2 stops on another session's lock, the outcome is
   `skipped`.
2. `git -C <worktree> fetch origin`. When `git -C <worktree> status
   --porcelain` is not empty, or `HEAD` is not the PR head
   (`gh pr view <N> --repo <owner>/<repo> --json headRefOid`), the
   outcome is `skipped`; go to section 9. A fix is in flight, and its own
   push merges the base (section 5 step 6).
3. `git -C <worktree> merge-base --is-ancestor origin/<base> HEAD`. Exit
   0: the outcome is `up-to-date`; go to section 9.
4. Under `dry_run`, write `git -C <worktree> merge --no-edit
   origin/<base>` and the push that would follow to
   `<scratchpad>/pr-watch-dry-run/<owner>-<repo>-<N>.md`; the outcome is
   `rehearsed`, and nothing else in this section runs. Go to section 9.
5. `git -C <worktree> merge --no-ff --no-commit origin/<base>`. On a
   conflict, `git -C <worktree> merge --abort`, post "conflicting"
   (`pr-watch/steps/06-notify.md`) with the conflicting paths, set
   `merge_notified` to `conflicting:<PR head>`, write the progress file,
   and go to section 9 with the outcome `conflicting`. Never resolve the
   conflict here.
6. Run the build and test commands that "Command detection" in
   `pr-loop-lib/steps/04.5-local-verify.md` finds, under its "Execution
   rules". Its skip condition and its failure flow do not apply: there is
   no fixer to retry. When a command fails, or `git -C <worktree> status
   --porcelain` shows a change that is not staged or an untracked file,
   run `git -C <worktree> merge --abort`, escalate ("needs you, no
   comment", reason "merge with origin/<base> breaks the build; nothing
   was committed"), and go to section 9 with the outcome `escalated`.
   When `status --porcelain` still prints anything after the abort, add
   "the worktree still has changes" to the reason.
7. `git -C <worktree> commit --no-edit`.
8. Section 6 (push or queue), with "merged <base>" as what changed. The
   outcome is `queued` when section 6 queues the PR, `escalated` when it
   escalates, and `pushed` otherwise. The merge needs no secret scan: it
   brings in only commits already on the remote, and a conflict aborts
   rather than being resolved.
9. Section 9.
