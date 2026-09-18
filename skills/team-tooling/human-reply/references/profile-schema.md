# Profile schema

The normative formats for the files setup writes under
`~/.claude/human-reply/` and for what a reader subagent returns. Headings
are fixed: runtime reads the files by section and a person edits them by
hand. A section with nothing in it keeps its heading.

## profile.md

```
# Voice profile
built: 2026-09-16 | method: measured | channels: slack, github
cutoff: 2026-01 | window: 2025-09-16..2026-09-16
inner circle: Ana, Raj
borrowed from: Mei (traits listed below)

## Hedges
- "I think", at most one hedge per message [slack, github]

## Typing habits
- keeps apostrophes out of contractions in short messages [slack, github]

## Disagreement
- first sentence states the disagreement, second gives the reason [slack, github]

## Sign-offs
- asks end with "Thanks!" and nothing after [slack, github]

## Banned
- anything on the humanizer skill's word list
- "Great catch" [slack, github]

## Borrowed traits
- opens replies with the verdict, no greeting | from Mei | adopted 2026-09-16 | told: yes
```

Header lines:

- `method` is the Python probe from the detect step: `measured` or
  `estimated`. Each channel file's own `method` is authoritative for that
  channel.
- `cutoff` is `YYYY-MM` or `never`. `inner circle` is `none` when empty.
  `borrowed from` is `none` when nothing was adopted.

Voice entries are one line each and end with the channels that returned
them in square brackets. An entry lives here only when two or more
channels returned it. The `humanizer` line under Banned is always present
and has no channels.

## channels/<channel>.md

```
# Slack voice
sample: 1412 messages, 2025-09-16..2026-09-16, 61 dropped by the AI filter | method: measured | threshold: 3 | redaction: script
status: partial (drop rate 0.46 after the threshold adjustment)

## Surfaces
| Surface | Audience | Records | Median | 75th | 90th | Budget | Label | Register |
|---|---|---|---|---|---|---|---|---|
| outer DM | anyone else, 1:1 | 212 (140 pre-cutoff) | 14 | 22 | 38 | 40 | measured | greeting only on first contact of the day |

## Pattern rates
| Pattern | Share of messages over 60 words |
|---|---|
| hedge | 0.35 |

| Quarter | Messages | 90th | Over 150 words |
|---|---|---|---|
| 2025Q4 | 310 | 41 | 0.01 |

## Phrasebook
### openers
- "Hey folks" (12)

## Shapes
### outer DM: quick answer
When: a direct question with a yes or no answer.
Skeleton:
    <answer>. <one reason>.
Examples:
    yes, <name> merged it this morning. it is behind the flag still.

## Habits
- lowercase first letter in DMs

## Calibration notes
- DMs to the squad stay under ten words
```

Header lines:

- `sample` gives the kept record count, the window, and the drop count.
- `method` is `measured` or `estimated` for this channel.
- `threshold` is always written.
- `redaction` is `script` or `model`.
- `status` is present only when the channel is partial, and lists every
  reason in `per_channel.<channel>.partial` from `setup.json` separated by
  `; `, such as `status: partial (calibration rejected)`.

Surfaces table:

- One row per surface in the channel module's `surfaces` block, in that
  order, even when the surface has no records.
- `Records` shows the total and, in brackets, the pre-cutoff count.
- On an estimated channel, `Median`, `75th`, and `90th` hold ranges and
  the budget is derived from the upper bound of the `90th` range.
- `Label` is `measured` or `estimated`. `Register` comes from the channel
  module's Surfaces table, amended by calibration notes.

Shapes use `### <surface>: <shape name>`, then `When:`, `Skeleton:`, and
`Examples:` with each skeleton and example indented four spaces.

## Reader return format

A reader subagent returns one JSON object:

```
{
  "shapes": [
    {"surface": "outer DM", "name": "quick answer",
     "when": "a direct question with a yes or no answer",
     "skeleton": "<answer>. <one reason>.",
     "examples": ["yes, <name> merged it this morning. it is behind the flag still."]}
  ],
  "phrasebook": {
    "openers": ["Hey folks"], "asks": [], "evidence": [], "hedges": ["I think"],
    "pivots": [], "closers": [], "visibility": [], "tone markers": []
  },
  "typing_habits": ["lowercase first letter in DMs"],
  "disagreement": ["first sentence states the disagreement, second gives the reason"],
  "sign_offs": ["asks end with \"Thanks!\" and nothing after"],
  "banned": ["never writes \"Great catch\""]
}
```

- `surface` is a surface name from the channel module.
- `phrasebook` has exactly the eight role keys shown; a role with nothing
  is an empty list.
- `banned` lists constructions common in drafted messages that the person
  never uses in the sample.
- No other keys. After the merge, each phrasebook phrase becomes
  `{"phrase": "...", "count": n}`.
