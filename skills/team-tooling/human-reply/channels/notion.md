# Notion channel module

What is true of Notion for every person. The person's own numbers,
phrasebook, and examples live in `~/.claude/human-reply/channels/notion.md`,
written by setup. When the two disagree on a number, the profile wins; on
markup, this file wins.

## Surfaces

| Surface | Who reads it | Collector assigns it when | Default register |
|---|---|---|---|
| page comment | everyone following the page | a comment in a discussion attached to the page itself | no greeting |
| inline comment | the author of the highlighted text | a comment in a discussion anchored to a block or a text selection | no greeting, one or two sentences |

The minimum is the smallest budget a measured profile may derive. The
default is the budget a surface gets when it has fewer than 30 pre-cutoff
records. Both are word counts with each link and fenced block counted as
one word.

```surfaces
# surface | minimum | default
page comment | 20 | 60
inline comment | 10 | 40
```

Notion is the weakest collector: comments are reached page by page, so
the sample is capped at 500 records and the profile header says so.

## Markup

Comments take rich text, not full page markdown.

- Headers, tables, and toggles do not render in a comment. Use line breaks.
- Inline code, bold, italic, and links render.
- Mention a person with `@name`; the person resolves it when pasting.
- Link a page by pasting its URL; Notion turns it into a page mention.
- A long answer belongs on the page as an edit or a new block, with the
  comment pointing at it.

## Shapes

Skeletons only. Angle brackets are slots. The profile adds the person's
own examples per shape.

Inline comment:

```
<the point about the highlighted text in one sentence>
```

Page comment answering a question:

```
<the answer in one sentence>. <the reason or the link>.
```

Page comment raising a concern:

```
<the concern in one sentence>. <what would resolve it>.
```

The default shape when none matches is the page comment answering a
question.

## Audit checklist

1. The first line of output named the channel, surface, budget, and
   profile provenance, and the draft is inside that budget.
2. The point is in the first sentence.
3. No headers, tables, or toggles.
4. Nothing already in the highlighted text or the page is restated.
5. Identifiers in backticks.

## AI-filter patterns

The scaffolding patterns scored on this channel by
`human-reply/references/ai-filter.md`, one id per line. An `exempt:` list
names surfaces where the pattern is the native form and does not score.

```ai-filter
emoji-section-marker
tldr-block
labelled-list | exempt: page comment
headers-bold-labels | exempt: page comment
em-dash
parallel-triple
closing-restatement | exempt: page comment
vocabulary
not-x-but-y
```
