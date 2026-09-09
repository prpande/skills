---
name: slack-reply
description: >
  Use whenever a Slack message is being drafted, rewritten, or shortened for
  the user to post: replies in a thread, new channel posts, cross-team asks,
  PR review requests, investigation updates, design shares, bug triage
  replies, DMs; when the user says "draft a Slack reply", "reply to this
  thread", "post this to <channel>", "shorten this message", "make this sound
  like me", or "/slack-reply". Sets the reader tier and word budget before a
  word is written, then applies the user's own message shapes and phrasebook
  so the draft reads like their 2025 writing rather than an AI template.
argument-hint: "[draft <what to say> | rewrite <text> | audit <text>]"
allowed-tools: Read, Skill
---

# slack-reply

Slack drafts default to too much: a context paragraph, section labels, a
TL;DR on top of the full text, a highlights list, two sign-offs. The reader
pays for every line. This skill drafts the way the user writes when they
type it themselves: the point first, evidence inline, one ask, one sign-off.

The rules come from a corpus of 11,716 messages the user sent between
January 2025 and June 2026 (`references/corpus-notes.md` has the numbers
and the method). Their real median channel message is 20 words. Four in
five are under 40. The long ones have a fixed shape (`references/shapes.md`).

The skill produces text only. It never sends. The user posts it.

## Workflow

1. Name the reader tier (table below) and say it in one line before the
   draft, for example "Tier: channel, in-thread reply. Budget 60 words."
   If the tier is unclear, ask one question and stop.
2. Pick the shape from `references/shapes.md` that matches the message
   type. If none matches, use the in-thread reply shape.
3. Write the draft inside the budget using the rules and phrasebook below.
4. Run the audit checklist (last section). Fix every hit.
5. If a `humanizer` skill is installed, run the draft through it, then
   re-check the budget: the humanizer must not add words.
6. Deliver the draft in a code block with Slack markup as it should be
   pasted, plus the suggested channel or thread. Nothing else.

## Reader tiers and budgets

| Tier | Who | Budget | Register |
|---|---|---|---|
| Core squad DM | the user's immediate squad, 1:1 | one line, 6 to 12 words | Hinglish is normal; no greeting, no sign-off |
| Outer DM | anyone else, 1:1 | 1 to 3 sentences, cap 50 words; a cold ask can reach 80 | English; greeting only on the first message of the day |
| Group DM | small ad-hoc group | same as outer DM; use channel rules if another squad is in it | English |
| Channel, in-thread reply | squad and project channels | 1 to 4 sentences, cap 60 words | English; no greeting |
| Channel, new post or cross-team ask | another squad's channel, a guild, platform support | 60 to 120 words in the cross-team shape | English; one greeting line |
| Investigation write-up or proposal | any channel | cap 150 words plus one code block or link list | English |

The user names the core squad; if they have not, treat every DM as outer.
Anything over the budget belongs in a Notion doc, a PR description, or a
second message in the thread. Slack carries the pointer and the ask.

## Rules

1. Lead with the point. The first line is the finding, the answer, or the
   question. Context comes after it, only when the reader lacks it.
2. One ask per message. Several questions become a numbered list, one line
   each.
3. Evidence goes inline: a number, a New Relic link, a PR line, a short
   code block. The user's pattern is a link inside the sentence, for
   example "as seen in these <link|NR captures>".
4. Never restate what the thread already says. An in-thread reply assumes
   the reader has read the thread.
5. No headers, no bold labels, no emoji section markers. Bold appears in
   under 1% of the user's messages and headers never. The single native
   exception is one emoji marker per error class in a multi-part
   investigation update, never more than three.
6. Bullets only for three or more parallel items. Two items are a sentence.
   Nested bullets never. Cap three bullets in a channel post, five anywhere.
7. Line breaks between thoughts, not blank-line paragraphs. The user's long
   messages average 1.6 paragraphs; the structure is lines.
8. One hedge at most, and a real one: "I think", "IMO", "AFAIK", "From the
   top of my head", "Correct me if I got it wrong". Never stacked, never
   "might potentially".
9. Sign-off is one line: "Thanks!" or "Thanks! :slightly_smiling_face:" on
   an ask, nothing on a reply. Never thank twice.
10. Names and cc on the last line: "cc: @Anshul @Kushal". This is how the
    user loops the squad into a cross-team thread.
11. Banned: em dashes, curly quotes, "I hope this helps", "Would appreciate",
    "Please find below", ":pray:" as a sign-off, "Key highlights", a TL;DR
    block at the top, a closing sentence that summarises the message.
12. Keep the user's typing habits. "dont", "isnt", "wont" without
    apostrophes are how they write DMs; do not polish them out. In a
    cross-team channel post either form is fine.
13. Disagreement goes in the first sentence, the reason in the second. No
    softening paragraph, no pros-and-cons list. "That said," is the one
    pivot when part of the other view is right.
14. Keep code formatting. Table names, endpoints, class and method names,
    flag names, error strings, and header names go in backticks. A snippet
    of more than one line goes in a fenced block. A rewrite that drops the
    original's backticks has lost information, not words.

## Slack markup that survives sending

Drafts are delivered as markdown, and the Slack tool converts it. Two
conversions bite:

- A `>` line swallows every following line until a blank line. Put a blank
  line after each quoted line, before the answer, and another blank line
  before the next quote. Without them the whole reply renders as one
  blockquote.
- Inline code needs backticks; plain identifiers come out as prose.

When the draft is handed over through the Slack tool (for example a DM to
the user's own account), read the sent message back once and check the
quote boundaries and code spans rendered. Fix and resend if not.

## Phrasebook

Use these instead of inventing register.

Openers, only on a new post or the first contact of the day:
- "Hi <name>," / "Hey <name>" / "Hello <name>"
- "Hi folks," / "Hey folks," / "Hi team,"
- Cold outreach adds one of "Good morning!", "Happy Monday!", "Happy
  Friday!", "Hope you are doing well!", optionally with
  ":slightly_smiling_face:" or ":hi_hand2:". Never two of these.
- In-thread replies have no opener. Start with the content, or with
  "<@name>" when addressing one person in a busy thread.

Asks:
- "Please review whenever time permits."
- "Please take a look whenever time permits."
- "Can you please take a look and let me know <what>?"
- "Let me know if this makes sense." / "Let me know what folks think."
- "Thoughts <@name>?" / "<@name> what do you think here?"
- "Any guidance on this will be really helpful."
- "Could you point me to the right person or team?"
- "QQ, <question>?" for a quick question inside an active thread.

Evidence:
- "As seen in these <link|NR captures>"
- "<link|NR Query>" on its own line after the claim
- "<Pull Request NNN>: <title>" on its own line
- "TLDR: <one line>" at the end of a longer finding, or a single
  "> TLDR:" quote line after the first sentence. Never a block on top.

Hedges, pick one or none:
- "I think" / "IMO" / "AFAIK" / "From the top of my head" / "Correct me
  if I got it wrong" / "Maybe its just me, but"

Pivots:
- "That said," / "Also," / "Another thing I noticed"

Closers:
- "Thanks!" / "Thanks! :slightly_smiling_face:" / "Thanks a ton!
  :slightly_smiling_face:" when someone did real work
- "Really appreciate the help." after a resolved cross-team thread
- Nothing on in-thread replies

Visibility:
- "cc: <@name> <@name>" as the last line
- "JFYI" opens an informational post
- "PS:" for an aside or an interesting find after the main point

Tone markers the user uses and a template would not:
- ":sweat_smile:" after admitting something awkward
- "pardon the hyperbole" / "Sorry if I sound naive"
- "Nailed down the issue finally!" / "Interesting find"

## Modes

### draft <what to say>

Follow the workflow. When the user supplies thread context, read it first
so the draft does not repeat it.

### rewrite <text>

Same workflow applied to an existing draft. State the tier, cut to the
budget, keep every fact, link, and code span the original had, and show
the word count before and after. Prefer the user's phrasing over yours whenever the
original contains a usable sentence.

### audit <text>

Do not rewrite. List each checklist hit with the offending line quoted, and
the word count against the tier budget. End with pass or fail.

## Audit checklist

1. Tier named, and the draft is inside that tier's budget.
2. The point is in the first line.
3. Exactly one ask, phrased as a question or a "please review".
4. Every piece of evidence is a link, a number, or a short code block
   inline, not a paragraph.
5. No headers, bold labels, emoji markers, TL;DR block, or nested bullets.
6. The thread's existing context is not repeated.
7. At most one hedge.
8. Sign-off is one line, at most one smiley, cc line last.
9. No em dashes, curly quotes, ":pray:", "Would appreciate", "Key
   highlights", "I hope this helps".
10. Identifiers are in backticks, snippets in fenced blocks, and every
    `>` line is followed by a blank line.
11. Read once as the recipient: they can act with at most one linked doc
    open.

## Common mistakes

- Treating the budget as a target. The median channel message is 20 words;
  60 is the ceiling for a reply, not the goal.
- Adding a context sentence "to be safe". If the reader is in the thread,
  it costs them a line for nothing.
- Answering several questions in prose. Quote each with `>` and answer
  under it (`references/shapes.md`).
- Sending a proposal as a message. Three bullets at most; the doc carries
  the rest.
- Letting the humanizer pass grow the draft. Re-check the budget after it.
- Stripping backticks while shortening. `tblResourceVisitType` in prose
  reads as a typo; in code it reads as a table.
- Answer lines glued to the `>` line. They render inside the quote.

Related skill: `humanizer` strips AI wording; this skill sets length and
shape. Run this one first.
