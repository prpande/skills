# Slack channel module

What is true of Slack for every person. The person's own numbers,
phrasebook, and examples live in `~/.claude/human-reply/channels/slack.md`,
written by setup. When the two disagree on a number, the profile wins; on
markup, this file wins.

## Surfaces

| Surface | Who reads it | Collector assigns it when | Default register |
|---|---|---|---|
| inner-circle DM | a person the interview named as inner circle, 1:1 | a 1:1 DM whose other member is on the inner-circle list | no greeting, no sign-off |
| outer DM | anyone else, 1:1 | any other 1:1 DM | greeting only on first contact of the day |
| group DM | a small ad-hoc group | a multi-person DM | as outer DM |
| channel thread reply | squad and project channels | a channel message inside a thread | no greeting |
| channel new post | another squad's channel, a guild, platform support | a top-level channel message of 120 words or fewer | one greeting line |
| write-up | any channel | a top-level channel message over 120 words | no greeting; one code block or link list at most |

The minimum is the smallest budget a measured profile may derive. The
default is the budget a surface gets when it has fewer than 30 pre-cutoff
records. Both are word counts with each link and fenced block counted as
one word.

```surfaces
# surface | minimum | default
inner-circle DM | 10 | 20
outer DM | 20 | 50
group DM | 20 | 50
channel thread reply | 20 | 60
channel new post | 40 | 120
write-up | 60 | 150
```

Anything over the budget belongs in a Notion page, a PR body, or a second
message in the thread. Slack carries the pointer and the ask.

## Markup that survives sending

Drafts are delivered as markdown and pasted into Slack, or sent through the
Slack tool by the person. Three conversions bite:

- A `>` line swallows every following line until a blank line. Put a blank
  line after each quoted line, before the answer, and another before the
  next quote.
- Inline code needs backticks; plain identifiers come out as prose. Table
  names, endpoints, class and method names, flags, error strings, and
  header names go in backticks. A snippet over one line goes in a fenced
  block.
- A bare URL at the end of a line can swallow the newline and the next
  word into the link. End the URL with punctuation or write
  `[title](url)`.

Mentions are `<@name>` for a person and `<!subteam^id>` for a group; in a
draft, write `@name` and let the person resolve it when pasting.

## Shapes

Skeletons only. Angle brackets are slots. The profile adds the person's
own examples per shape.

In-thread reply, one point:

```
<the point in one sentence>. <one sentence of evidence or reasoning, link inline>.
```

Answering several questions:

```
> <question one>

<answer>

> <question two>

<answer>
```

Cross-team ask:

```
<greeting and name>
<one or two sentences: what we are doing and why we are here, link inline>
<the ask as a question; two or more asks become a numbered list>
<sign-off line>
<cc line>
```

PR review request:

```
<greeting> <what the PR does, one clause>. <ask>.
<PR link and title>
<sign-off line>
```

Investigation update:

```
<headline: what was found>
<two to four lines: the mechanism, numbers and links inline>
<one line: workaround or next step>
```

Design or doc share:

```
<greeting>
<one sentence: what the doc proposes and for which flow>. <doc link inline>.
<the ask>
```

Pushback:

```
<the disagreement in one sentence>. <the reason in one sentence>.
```

Heads-up:

```
<the fact in one sentence>. <what it means for the reader, link inline>.
```

The default shape when none matches is the in-thread reply.

## Audit checklist

1. The first line of output named the channel, surface, budget, and
   profile provenance, and the draft is inside that budget.
2. The point is in the first line of the draft.
3. At most one ask.
4. Evidence is a link, a number, or a short code block inline, not a
   paragraph.
5. No headers, no bold labels, no TL;DR block on top, no nested bullets;
   emoji section markers only where the profile's shapes use them.
6. Nothing the thread already says is repeated.
7. Identifiers in backticks, snippets in fenced blocks, a blank line after
   every `>` line, no bare URL ending a line.
8. Read once as the recipient: they can act with at most one linked doc
   open.

## AI-filter patterns

The scaffolding patterns scored on this channel by
`human-reply/references/ai-filter.md`, one id per line. An `exempt:` list
names surfaces where the pattern is the native form and does not score.

```ai-filter
emoji-section-marker
tldr-block
labelled-list
headers-bold-labels
em-dash
parallel-triple
closing-restatement
vocabulary
not-x-but-y
```
