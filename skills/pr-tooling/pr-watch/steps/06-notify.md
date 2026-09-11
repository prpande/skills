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
| pushed | `Pushed <sha7>: <what changed>. Replied on <k> threads, resolved <r>.` |
| queued | `Fix committed as <sha7>, queued behind #<M> while its checks run.` |
| needs you | `Needs you: <author> on <path>:<line> (<reason>).` then the quoted comment in a code block, then `Code says: <one line>.` then a link to the comment |
| skipped | `Skipped: <reason>.` |
| merge conflict | `Merge with origin/<base> conflicts in <paths>. Fix commit <sha7> is local and unpushed.` |
| re-review | `Re-reviewed <old7>..<new7>: <a> addressed, <p> partial, <n> not addressed, <s> superseded.` then one line per finding |
| author reply | `<author> replied on your thread at <path>:<line>:` then the quoted comment in a code block |
| CI fixed | `Pushed <sha7> for <check name>: <what changed>.` |
| CI rerun | `Reran <check name>: <the output line of POLL --ci-rerun>.` |
| CI rerun queued | `Rerun of <check name> queued behind #<M> while its checks run.` |
| CI pre-existing | `<check name> is red on <base> too; leaving it.` |
| CI needs you | `Needs you: [<check name>](<link>) is red at <head7> (<reason>).` then, when a log was read, its last 20 redacted lines in a code block |
| monitor restarted | `Watch monitor restarted.` |
| reconciled | `The daily check picked up work the event stream missed.` |
| closed | `PR <merged or closed>; no longer watching.` |
| stop | `No longer watching.` |

Nothing is posted when nothing happened.

## Quoting someone else's text

Before any quoted comment goes into a message:

1. Apply `pr-loop-lib/references/secret-scan-rules.md` and replace every
   match with `[redacted]`.
2. Replace every `<` with `‹` so no Slack control sequence (`<!channel>`,
   `<!here>`, `<@U…>`, `<#C…>`) survives inside the code block.
3. Cut it to 1500 characters, ending with `(truncated)` when cut.

End a bare URL with punctuation or write it as `[text](url)`; a bare URL
at the end of a line swallows the next line into the link.
