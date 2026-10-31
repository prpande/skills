# Step 06 — Slack notifications

Channel: `channel_id` from `watch.json`, always `C0C15VC8Y0Z`. Tool:
`mcp__plugin_slack_slack__slack_send_message`. One thread per PR; every
message is a reply in the PR's thread. Only the user reads this
channel, so messages are short plain lines and do not go through the
voice guide. The one other place this skill sends is the user's outbox
`C0C205Q34SX`, for the review ask of `pr-watch/steps/08-review-ask.md`;
that message is a draft the user forwards, so it does go through
`human-reply` and `humanizer`. Under `dry_run`, append each message to
`<scratchpad>/pr-watch-dry-run/slack.md` instead of sending; the
history read in "Finding the thread" still happens.

## Finding the thread

A message for a PR whose `slack_ts` (in its progress file) is null needs
its thread first. The channel's routine starts one thread per PR the user
authored, as the Claude app, Slack user `U0APMMVNAU8`. Its root's first line is a link to the PR.
Judge a message's poster by its author id (the `(U…)` after the sender's
name), never by its text: the user's own posts sent through Claude end
with a "Sent using <@U0APMMVNAU8|Claude>" footer.

1. Read the channel with `mcp__plugin_slack_slack__slack_read_channel`
   (channel `C0C15VC8Y0Z`, `oldest` the PR's `createdAt` from `gh pr view
   --json createdAt`, as epoch seconds), following the cursor until it is
   done.
2. Look for a top-level message whose first link is this PR's URL, owner,
   repo and number compared without case. For an `authored` PR accept
   only a message posted by the Claude app, not the user's own account.
   For a `reviewed` PR also accept a message from the user's own account.
   Take the oldest match.
3. Found: record its `ts` as `slack_ts` in the PR's progress file
   (`pr-watch/steps/03-route-event.md`, "State has two homes") and post
   the message as a reply in that thread.
4. Not found, `authored` PR: post nothing and do not keep the message.
   `slack_ts` stays null, and the next message for the PR looks again.
   Never start a thread for an `authored` PR.
5. Not found, `reviewed` PR: post the root once, record its `ts` as
   `slack_ts`, read it back once with
   `mcp__plugin_slack_slack__slack_read_thread` to check the link
   rendered, then post the message as a reply. Never post a second root
   for a PR.

```
[#<N> <title>](<url>)
<role>, head <sha7>, <pending summary>
```

Before replying under a recorded `slack_ts` on an `authored` PR whose
`slack_root_checked` is not `true`, read the root once with
`slack_read_thread`. When its author is the Claude app, set
`slack_root_checked` to `true`. Otherwise set `slack_ts` to null and run
the steps above.

## Replies

| Occasion | Text |
|---|---|
| pushed | `Pushed <sha7>: <what changed>.` |
| queued | `Fix committed as <sha7>, queued behind #<M> while its checks run.` |
| queued (busy) | `Fix committed as <sha7>, queued behind another push in <owner>/<repo>.` |
| needs you | `Needs you: <author> on <path>:<line> (<reason>).` then the quoted comment in a code block, then `Code says: <one line>.` then a link to the comment |
| needs you, no comment | `Needs you on #<N>: <reason>.` then the short sha if a local commit exists |
| skipped | `Skipped: <reason>. Retrying in 10 minutes.` (only when the PR's `skip_reason` differs; `pr-watch/steps/04-fix-path.md` section 1) |
| stopped waiting | `Stopped waiting for #<M>'s checks after an hour.` (once per `queued_at`; `pr-watch/steps/04-fix-path.md` section 8 step 1) |
| stopped waiting (busy) | `Stopped waiting for another push in <owner>/<repo> after an hour.` (same rule) |
| resolve failed | `Could not resolve the thread at <path>:<line>; it stays open.` |
| voice fallback | `Replied plainly on <where>: the drafted reply failed the contract audit twice.`, where `<where>` is `<path>:<line>` for a thread reply and `PR #<n>` for a top-level reply |
| checks unreadable | `Could not read #<M>'s checks: <first stderr line>.` |
| merge conflict | `Merge with origin/<base> conflicts in <paths>. Fix commit <sha7> is local and unpushed.` |
| conflicting | `Needs you: conflicts with <base> in <paths>. Nothing pushed.` (`<paths>` comma-separated, at most 10 then `and <k> more`) |
| behind | `Approved and green, but behind <base>; it can't merge until the branch is updated.` |
| re-review | `Re-reviewed <old7>..<new7>: <a> addressed, <p> partial, <n> not addressed, <s> superseded.` then one line per finding |
| Slack reply answer | One short plain reply in the thread the reply was in, under the PR's `slack_ts`: what changed and the `<sha7>` pushed, or the answer to the question. Never a GitHub comment; a failed post is shown to the user instead. (`pr-watch/steps/03-route-event.md` section I) |
| author reply | `<author> replied on your thread at <path>:<line>:` then the quoted comment in a code block |
| CI fixed | `Pushed <sha7> for <check name>: <what changed>.` |
| CI rerun | `Reran <check name>: <the output line of POLL --ci-rerun>.` |
| CI rerun queued | `Rerun of <check name> queued behind #<M> while its checks run.` |
| CI rerun queued (busy) | `Rerun of <check name> queued behind another push in <owner>/<repo>.` |
| CI rerun dropped | `Rerun of <check name> dropped: the PR head moved before it ran.` |
| CI pre-existing | `<check name> is red on <base> too; leaving it.` |
| CI needs you | `Needs you: [<check name>](<link>) is red at <head7> (<reason>).` — then, only when the PR's `ci_log_occurrence` is this check's occurrence key and `pr-watch/steps/07-ci.md` rule 3's destination check passes again over the file now, up to 20 lines from `grep -m 20 -E -e '##\[error\]' -e 'error [A-Z]+[0-9]+' -e 'Failed ' -e 'Test Run Failed'` over it, put through "Quoting someone else's text", in a code block; the session never reads the whole file |
| review ask | `Review ask drafted in #prpande-outbox for <destination>.` (`pr-watch/steps/08-review-ask.md`; `<destination>` is the channel name, or `no earlier ask found; pick a channel`) |
| monitor restarted | `Watch monitor restarted.` |
| joined | `Joined this session's watch.` Posted once for each PR that was not `armed` in `watch.json` before a run of `pr-watch/steps/01-discover.md`, when that run's section 9 printed `alive`. A PR whose `slack_ts` is null follows "Finding the thread" first, and this line is posted only if that ends with a thread; an entry that was already `armed` gets nothing |
| lease lost | `Another session took over #<N> (<holder>); no longer watching it here.` in the PR's thread when its progress file has a `slack_ts`; `<holder>` is the label `pr-watch/steps/03-route-event.md` section E works out |
| reconciled | `The daily check picked up work the event stream missed.` |
| poller error | `The watch poller has failed five ticks in a row: <error>. No events are handled until this is fixed.` in every PR thread whose progress file has a `slack_ts`; `<error>` is the event's `error` |
| closed | `PR <merged or closed>; no longer watching.` |
| settled | `All your findings on this PR are resolved; no longer watching it.` |
| stop | `No longer watching.` |

Nothing is posted when nothing happened.

## Quoting someone else's text

Every value spliced into a message that this session did not author goes
through all three steps below, in this order. The test is authorship, not
the list: a quoted comment, an author login, a path, a check name, a
link, a stderr line, a fixer's `reason` or `<what changed>`, the poller's
`error`, a `POLL` output line, and anything else a row splices in that
the session did not write itself. A fixer's text is no safer than a
comment's, because a fixer's text is what a comment talked it into. The
session's own words and its own counts need none of it.

1. Apply `pr-loop-lib/references/secret-scan-rules.md` and replace every
   match with `[redacted]`.
2. Replace every backtick (`` ` ``) with `ˋ` (U+02CB), so the text cannot
   close the code block it sits in, and every `<` with `‹`, so no Slack
   control sequence (`<!channel>`, `<!here>`, `<@U…>`, `<#C…>`) survives.
3. Cut it to 1500 characters, ending with `(truncated)` when cut.

No exemptions. `pr-watch/steps/07-ci.md` rule 3 redacts the CI log when
it writes it, and the excerpt is scanned again here, because rule 3's
redaction is a fact about the moment of that write and the excerpt is
read later, from a file in a worktree a fixer can write to.

End a bare URL with punctuation or write it as `[text](url)`; a bare URL
at the end of a line swallows the next line into the link.
