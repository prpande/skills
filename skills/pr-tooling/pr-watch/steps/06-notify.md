# Step 06 — Slack notifications

Channel: `channel_id` from `watch.json`. Tool:
`mcp__plugin_slack_slack__slack_send_message`. One thread per PR; every
message after the root is a reply in it. Only the user reads this
channel, so messages are short plain lines and do not go through the
voice guide. Under `dry_run`, append each message to
`<scratchpad>/pr-watch-dry-run/slack.md` instead of sending.

## Root

The first message for a PR whose `slack_ts` is null is its root:

```
[#<N> <title>](<url>)
<role>, head <sha7>, <pending summary>
```

Record the returned `ts` as `slack_ts` and write `watch.json`. Read the
root back once with `mcp__plugin_slack_slack__slack_read_thread` and
check the link rendered. Never post a second root for a PR.

## Replies

| Occasion | Text |
|---|---|
| pushed | `Pushed <sha7>: <what changed>.` |
| queued | `Fix committed as <sha7>, queued behind #<M> while its checks run.` |
| needs you | `Needs you: <author> on <path>:<line> (<reason>).` then the quoted comment in a code block, then `Code says: <one line>.` then a link to the comment |
| needs you, no comment | `Needs you on #<N>: <reason>.` then the short sha if a local commit exists |
| skipped | `Skipped: <reason>. Retrying in 10 minutes.` (only when the PR's `skip_reason` differs; `pr-watch/steps/04-fix-path.md` section 1) |
| stopped waiting | `Stopped waiting for #<M>'s checks after an hour.` (once per `queued_at`; `pr-watch/steps/04-fix-path.md` section 8 step 1) |
| resolve failed | `Could not resolve the thread at <path>:<line>; it stays open.` |
| voice fallback | `Replied plainly on <where>: the drafted reply failed the contract audit twice.`, where `<where>` is `<path>:<line>` for a thread reply and `PR #<n>` for a top-level reply |
| checks unreadable | `Could not read #<M>'s checks: <first stderr line>.` |
| merge conflict | `Merge with origin/<base> conflicts in <paths>. Fix commit <sha7> is local and unpushed.` |
| re-review | `Re-reviewed <old7>..<new7>: <a> addressed, <p> partial, <n> not addressed, <s> superseded.` then one line per finding |
| author reply | `<author> replied on your thread at <path>:<line>:` then the quoted comment in a code block |
| CI fixed | `Pushed <sha7> for <check name>: <what changed>.` |
| CI rerun | `Reran <check name>: <the output line of POLL --ci-rerun>.` |
| CI rerun queued | `Rerun of <check name> queued behind #<M> while its checks run.` |
| CI rerun dropped | `Rerun of <check name> dropped: the PR head moved before it ran.` |
| CI pre-existing | `<check name> is red on <base> too; leaving it.` |
| CI needs you | `Needs you: [<check name>](<link>) is red at <head7> (<reason>).` — then, only when the PR's `ci_log_occurrence` is this check's occurrence key and `pr-watch/steps/07-ci.md` rule 3's destination check passes again over the file now, up to 20 lines from `grep -m 20 -E -e '##\[error\]' -e 'error [A-Z]+[0-9]+' -e 'Failed ' -e 'Test Run Failed'` over it, put through "Quoting someone else's text", in a code block; the session never reads the whole file |
| monitor restarted | `Watch monitor restarted.` |
| reconciled | `The daily check picked up work the event stream missed.` |
| poller error | `The watch poller has failed five ticks in a row: <error>. No events are handled until this is fixed.` in every PR thread that has a root; `<error>` is the event's `error` |
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
