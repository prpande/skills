---
name: human-reply
description: >
  Use whenever a message is being drafted, rewritten, shortened, or checked
  for the user to post on Slack, GitHub, or Notion: thread replies, DMs,
  channel posts, PR review replies, review summaries, PR bodies, issue
  comments, Notion page and inline comments; when the user says "reply to
  this thread", "draft a comment on this PR", "answer this Notion comment",
  "make this sound like me", "shorten this", or "/human-reply". Also runs
  the one-time setup that builds the user's voice profile from their own
  messages. Drafts in the user's measured voice for that channel. Text
  only, never posts.
argument-hint: "[setup [slack|github|notion] | draft <what to say> | rewrite <text> | audit <text>]"
allowed-tools: Read, Bash, Write, Skill, ToolSearch, Agent, mcp__plugin_slack_slack__slack_search_public_and_private, mcp__plugin_slack_slack__slack_read_thread, mcp__plugin_slack_slack__slack_search_users, mcp__claude_ai_Notion__notion-fetch, mcp__claude_ai_Notion__notion-search, mcp__claude_ai_Notion__notion-get-comments, mcp__claude_ai_Notion__notion-list-recent-pages, mcp__claude_ai_Notion__notion-get-users
---

# human-reply

Writes a message the way the user writes it on that channel. Platform
facts live in the `human-reply/channels/` folder. The user's own numbers,
phrasebook, shapes, and habits live in `~/.claude/human-reply/`, written
by setup. This skill never calls a tool that sends, posts, comments, or
reacts.

## Route

| Arguments | Mode |
|---|---|
| `setup`, or `setup <channel>` | setup |
| `draft <what to say>`, or a request to reply or write | draft |
| `rewrite <text>`, or "make this sound like me", "shorten this" | rewrite |
| `audit <text>` | audit |

With no arguments and no request in the conversation, ask which mode.

## Setup

Follow the eight step files in the `human-reply/setup/` folder in number
order: 01-detect, 02-interview, 03-collect, 04-filter, 05-measure,
06-read, 07-calibrate, 08-finish. Read a step only when the previous one
is done. Setup writes only under `~/.claude/human-reply/`.

## Draft, rewrite, and audit

### 1. Channel

Settle the channel from, in order:

1. an explicit channel in the arguments or the request
2. a URL in the request: `slack.com` is Slack, `github.com` is GitHub,
   `notion.so` or `notion.site` is Notion
3. the pasted thread: Slack mentions like `<@U...>` and `:emoji:`, GitHub
   review comments with file paths and line numbers, Notion page text

When none of these settles it, ask one question naming the three channels
and stop.

Read `~/.claude/human-reply/channels/<channel>.md`. When it does not
exist, do not draft: say there is no profile for that channel and that
`/human-reply setup <channel>` builds one. There is no generic voice.

### 2. Surface and budget

Read the channel module in the `human-reply/channels/` folder. Pick the
surface from its Surfaces table by where the message will be posted. On
Slack, a 1:1 DM is an inner-circle DM when the other person is on the
`inner circle` line of `~/.claude/human-reply/profile.md`.

Take the budget and label from the profile's Surfaces row. Print this as
the first line of output, before anything else:

```
<Channel>, <surface>, budget <n> words, profile <method> <built date>[, <label> budget][, partial: <reasons>]
```

For example: `Slack, channel thread reply, budget 60 words, profile
measured 2026-09-16`. Add the `estimated budget` part when the row's
label is `estimated`, and the partial part when the profile header has a
`status` line. A wrong channel or surface shows up here before anything
is pasted.

### 3. Shape

Pick the shape from the profile's Shapes for that surface. When none
fits, use the default shape the channel module names.

### 4. Write

Write inside the budget, counting each link and each fenced block as one
word. Use:

- the profile's phrasebook, and the hedges, typing habits, disagreement
  pattern, sign-offs, and Borrowed traits from
  `~/.claude/human-reply/profile.md`; where the channel profile's Habits
  say otherwise, Habits win for that channel
- each Borrowed trait as the user's own habit, never attributed to the
  colleague it came from
- nothing on the Banned list
- the channel module's markup rules

A reply inside a thread never restates the thread. For `rewrite`, keep
every fact, link, code span, and mention of the original.

### 5. Audit

Check the draft against the channel module's audit checklist and every
rule under the profile's Calibration notes. Fix every hit.

### 6. Humanizer

When the `humanizer` skill is installed, run the draft through it with
the instruction in `human-reply/references/humanizer-handoff.md` and follow the checks
that file lists after it returns. On any conflict, the profile's
phrasebook wins.

### 7. Deliver

After the first line, print the draft in one fenced block with the
channel's markup exactly as it should be pasted, then one line saying
where it goes. Nothing else. For `rewrite`, that line also gives the word
count before and after. The outer fence is longer than any fence inside
the draft: four backticks when the draft holds a three-backtick fence,
such as a `suggestion` block.

### Audit mode

For `audit <text>`, do steps 1 to 3 and step 5 on the given text without
changing it. Print the first line, then each checklist or calibration hit
with the offending line quoted, then the word count against the budget,
then `pass` or `fail`.

## Called by another skill

`pr-watch` calls `draft` with channel `github`, the surface, and the
content the reply must carry as the ask. Put that content in the draft.
Do not read the caller's own rules; items it wants included or removed
arrive in the ask.
