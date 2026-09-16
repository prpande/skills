# GitHub channel module

What is true of GitHub for every person. The person's own numbers,
phrasebook, and examples live in `~/.claude/human-reply/channels/github.md`,
written by setup. When the two disagree on a number, the profile wins; on
markup, this file wins.

## Surfaces

| Surface | Who reads it | Collector assigns it when | Default register |
|---|---|---|---|
| review thread reply | the PR author or a reviewer, on one line of code | a pull request review comment (`pulls/comments`) | no greeting, no sign-off |
| review summary | the PR author | the body of a submitted review, when not empty | no greeting |
| PR body | every reviewer | the body of a pull request the person opened | headers and lists allowed |
| issue comment | everyone watching the issue or PR conversation | a comment on an issue or on a PR's conversation tab (`issues/comments`) | no greeting |

The minimum is the smallest budget a measured profile may derive. The
default is the budget a surface gets when it has fewer than 30 pre-cutoff
records. Both are word counts with each link and fenced block counted as
one word.

```surfaces
# surface | minimum | default
review thread reply | 20 | 60
review summary | 20 | 80
PR body | 40 | 200
issue comment | 20 | 80
```

## Markup

GitHub renders GitHub Flavored Markdown on every surface.

- Cite code with a link to the line range at a commit:
  `https://github.com/<owner>/<repo>/blob/<sha>/<path>#L10-L20`. Line
  numbers go in the link, not in the prose.
- An exact proposed change goes in a `suggestion` fenced block on a review
  thread reply, and nowhere else.
- `@login` notifies the person. Never mention a bot account.
- `#123` links an issue or PR in the same repo; `owner/repo#123` across
  repos.
- A `>` line quotes; a blank line ends the quote.
- Identifiers go in backticks, multi-line snippets in fenced blocks with a
  language tag.

## Shapes

Skeletons only. Angle brackets are slots. The profile adds the person's
own examples per shape.

Fixed, on a review thread reply:

```
<what changed, one clause>, in <short sha>
```

Refuted, on a review thread reply:

```
<what the code does, one clause> <line-range link at a commit>
```

Superseded:

```
<what the code says now>, since <short sha>
```

Answered and left open:

```
<what is pending> <why, one clause>
```

Review summary:

```
<the verdict in one sentence>
<one line per blocking point, each pointing at its thread>
```

PR body:

```
<what the PR does and why, two or three sentences>
<changes, as a list when there are three or more>
<how it was tested>
```

Issue comment:

```
<the answer or the finding in one sentence>. <evidence, link inline>.
```

The default shape when none matches is the issue comment.

## Audit checklist

1. The first line of output named the channel, surface, budget, and
   profile provenance, and the draft is inside that budget.
2. The substance is in the first sentence.
3. Every identifier in backticks, every multi-line snippet in a fenced
   block, every code citation a line-range link at a commit or a
   repo-relative path.
4. Nothing from the comment being answered is repeated.
5. No greeting or thanks-opener on a review thread reply, review summary,
   or issue comment.
6. No @-mention of a bot account.
7. No promise of future work with a date.

## AI-filter patterns

The scaffolding patterns scored on this channel by
`human-reply/references/ai-filter.md`, one id per line. An `exempt:` list
names surfaces where the pattern is the native form and does not score.

```ai-filter
emoji-section-marker
tldr-block
labelled-list | exempt: PR body, review summary
headers-bold-labels | exempt: PR body, review summary
em-dash
parallel-triple
closing-restatement | exempt: PR body, review summary
vocabulary
not-x-but-y
```
