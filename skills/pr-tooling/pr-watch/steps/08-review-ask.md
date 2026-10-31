# Step 08 — Ask for human review

Runs on a `review-ready` event (`pr-watch/steps/03-route-event.md`). The
poller raises it when an `authored` PR has a green rollup and has been
quiet for 30 minutes. The ask is drafted by this session, which holds the
PR's context, and goes to the user's outbox, never to the PR's own
channel. A `reviewed` PR never gets one.

## 1. Confirm

1. Run `POLL --review-ready <key> --session-dir <SESSION_DIR>`. It prints
   `{"pr", "head", "ready", "blockers"}`; `ready` is true only when the PR
   is open and not a draft, its required checks and rollup are green, no
   review thread is unresolved, nothing is pending, queued or waiting in
   the push queue, a reviewer bot has left a review or comment, no bot
   comment and no commit is newer than 30 minutes, no human other than
   the user has reviewed, and the progress file's `review_ask` is null.
2. `ready` false: stop. Post nothing. The poller raises the event again
   when the PR next changes.
3. `ready` true: also stop when this session has a fix for the PR in
   flight or a local commit not yet pushed (`git -C <worktree> status
   --porcelain` not empty, or `HEAD` not the PR head). A fix is not done
   until it is pushed, and a push resets the quiet window.
4. Bring the branch up to date before asking, once per PR. Read
   `baseRefName` (`gh pr view <N> --repo <owner>/<repo> --json baseRefName`),
   run `git -C <worktree> fetch origin`, then
   `git -C <worktree> merge-base --is-ancestor origin/<baseRefName> HEAD`.
   On a non-zero exit while the progress file's `ask_base_update` is
   null: run `pr-watch/steps/04-fix-path.md` section 11 (base update) and
   stop without asking. On its outcome `conflicting`, `escalated`,
   `queued` or `pushed`, set `ask_base_update` to the PR head read before
   it and write the progress file; on any other outcome write nothing.
   A push restarts the quiet window, and the poller raises `review-ready`
   again once the PR is green and quiet; after a conflict or an
   escalation it comes once the user's own push makes the PR green. When
   `ask_base_update` is already set, ask without updating again: the base
   can move faster than a PR goes quiet.

## 2. Find the destination

1. Search with `mcp__plugin_slack_slack__slack_search_public_and_private`,
   query `from:<@U07ENJD06T0> "github.com/<owner>/<repo>/pull"`, with the
   PR's real owner and repo.
2. Take the channel of the most recent hit whose channel is neither
   `C0C15VC8Y0Z` nor `C0C205Q34SX`. That channel's id is the
   `destination`, its name is what the first line of the message shows.
3. No such hit, or the search fails: `destination` is `none` and the
   first line says `For no earlier ask found; pick a channel:`.

## 3. Compose

Write the ask from what this session knows of the PR: its title, what it
changes and why, anything a reviewer should look at first, and its size
(`gh pr view <N> --repo <owner>/<repo> --json additions,deletions,changedFiles`).
Keep it to what a reviewer needs to start; no status of the bot loop, no
CI detail. Include the PR as `[<title>](<url>)`.

Run the `human-reply` skill in draft mode for channel `slack`, then the
`humanizer` skill, over the text. Leave `@` handles as plain text; the
user forwards the message and fixes mentions there.

The message sent is:

```
For <#channel-name>:
<the ask>
```

or `For no earlier ask found; pick a channel:` as the first line when the
destination is `none`.

## 4. Send and record

Under `dry_run`, append the message to
`<scratchpad>/pr-watch-dry-run/slack.md` and stop. Record nothing in the
progress file, and send nothing.

Otherwise:

1. Send it with `mcp__plugin_slack_slack__slack_send_message` to channel
   `C0C205Q34SX`, not as a thread reply. This is the one channel besides
   the PR threads in `C0C15VC8Y0Z` pr-watch posts to
   (`pr-watch/steps/06-notify.md`).
2. Write `review_ask` in the PR's progress file straight away, before
   anything else can fail: `{"drafted_at": "<iso utc now>", "outbox_ts":
   "<ts of the sent message>", "destination": "<channel id or none>"}`.
3. Read the message back once with `slack_read_thread` and check the PR
   link rendered as a link. A link that did not render is
   reported in the conversation; the message is not edited.
4. If the PR's `slack_ts` is set, or "Finding the thread" in
   `pr-watch/steps/06-notify.md` finds an existing thread, post the
   `review ask` row there. Do not start a thread for it.

The send is once per PR: a recorded `review_ask` ends it, and the poller
never raises the event for a PR whose `review_ask` is set.
