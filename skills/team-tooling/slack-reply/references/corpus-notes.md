# Corpus notes

Where the budgets and rules come from, so they can be re-derived or
challenged later.

## Corpus

Every message the user sent between 2025-01-01 and 2026-06-30, collected
through the Slack MCP search (`from:<@me> after:X before:Y`, one calendar
month per window, channels and DMs as separate windows, re-windowed from
the last captured date whenever the search hit its 20-page cap). 12,300
raw records, 11,716 after dropping the self-DM, empty messages, and three
bot-style channels (automated sweep posts, a bookmarks channel, an agent
test channel).

| Tier | Messages | Median words | 75th pct | 90th pct | Over 60 words |
|---|---|---|---|---|---|
| Channel | 2,543 | 20 | 41 | 74 | 14% |
| Group DM | 292 | 17 | 33 | 77 | 15% |
| DM, outside core squad | 1,545 | 10 | 19 | 36 | 4% |
| DM, core squad | 7,336 | 6 | 12 | 20 | under 1% |

Word counts collapse code blocks and links to one token each, so a message
with a 40-line stack trace still counts as short prose.

The core squad tier is a proxy for the user's Slack VIP list, which the
tooling cannot read. It was set to the four people the user DMs most.

## Drift, channels only

| Quarter | 90th pct words | Messages over 150 words |
|---|---|---|
| 2025 Q1 | 70 | 0.8% |
| 2025 Q2 | 67 | 0.7% |
| 2025 Q3 | 76 | 3.0% |
| 2025 Q4 | 85 | 3.9% |
| 2026 Q1 | 73 | 3.9% |
| 2026 Q2 | 94 | 5.7% |

The 2026 tail is where the "too verbose" complaint comes from. Reading
every channel message over 60 words (385 of them) showed the long 2026
ones share scaffolding the 2025 ones never have: emoji section labels, a
TL;DR block before the full text, "Key highlights" bullets, an opening
paragraph restating context the thread already had, and a two-sentence
sign-off.

## Pattern rates in the user's own long messages

Of the 461 messages over 60 words sent to a channel, group DM, or outer
DM:

| Pattern | Share |
|---|---|
| Starts with Hi / Hey / Hello | 35% |
| Ends with a smiley | 20% |
| Ends with "Thanks!" | 17% |
| Has a cc line | 16% |
| Contains bullets | 29% |
| Contains one hedge ("I think", "maybe", "not sure") | 26% |
| Contains a question | 39% |
| Contains a link | 44% |
| Quote-reply with `>` | 5% |
| Bold text | 3% |
| Code block | 8% |

Mean 6.3 sentences at 18 words each, 1.6 paragraphs. That is the shape
the rules encode: several short lines, not blocks.

## Re-deriving

The scripts that produced these numbers are trivial (regex field parser
over the search dumps, tiering by channel ID and DM participants, word
counts, per-quarter aggregates). The raw dumps were deleted after analysis
because pasted messages contained live credentials; re-collect rather than
look for them.
