# Known-bot signatures

Used by `steps/03-triage.md` filter B. Each row gives a rule that
classifies a comment as actionable or skip-able.

## Default classification table (cross-team, ships with the skill)

| Login | Where it posts | Signature (body contains / starts with) | Classification |
|---|---|---|---|
| `Copilot` | Inline review comment | Any body with `path` set on the API response | Actionable |
| `copilot-pull-request-reviewer[bot]` | Review body | contains `### Suppressed comments` or `previously missed issue</strong>` or `previously missed issues</strong>` | Parse — one finding per item, see "Copilot review body" below |
| `copilot-pull-request-reviewer[bot]` | Review body | neither | Skip — verdict, overview and counts; inline comments carry the other findings |
| `sonarqube[bot]` | Top-level PR comment | `Quality Gate passed` | Skip — status only |
| `sonarqube[bot]` | Top-level PR comment | `Quality Gate failed` | Actionable — surface listed issues |
| `sonarqubecloud[bot]` | Top-level PR comment | `Quality Gate passed` | Skip — status only |
| `sonarqubecloud[bot]` | Top-level PR comment | `Quality Gate failed` | Actionable — surface listed issues |
| `github-actions[bot]` | Top-level PR comment | Any | Usually skip; check if body contains failure details (then actionable) |
| `dependabot[bot]` | Top-level PR comment | Any | Skip for this skill's scope (dependency updates are out of scope) |

The default list is deliberately short. Only bots that are well-known
across teams ship as defaults.

### Copilot review body

Most Copilot findings are inline comments. Two kinds live only in its
review body: the items under `### Suppressed comments`, and, in a body
that opens with `<!-- ccr-overview-v2 -->`, the items of the "previously
missed issues" block (findings in code that has not changed since its
last review). Write the body to a file and run:

```
python "$HOME/.claude/skills/pr-loop-lib/scripts/copilot_review.py" <body-file>
```

It prints `{"classification", "findings"}`. Each finding becomes one
actionable item: surface `review`, id `<review id>:finding-<N>` in output
order, its `path` and `line`, as body the `text` when it begins with
the `title` and otherwise the `title` followed by the `text`, led by
`[High] `, `[Medium] ` or `[Low] ` when `severity` is set, and `copilot_key`
its `key`. The open-issues and resolved-since-last-review blocks are never
findings. An iteration that records a disposition for one is never
quiescent in step 08, whatever the verdicts. Exit 2 means the body names one of
the two sections but the script could not read an item: treat the whole
body as one actionable item with id `<review id>` and `copilot_key`
`copilot|review|<review id>`. Exit 64 means the call was wrong (quote a
body path that holds a space) or the file could not be opened: fix the
call and run it again; it is neither a skip nor an unreadable body. Pass
a file, not a pipe: a Windows PowerShell pipe turns non-ASCII characters
in paths into `?`.

Copilot repeats a finding it still sees in its next review, under a new
review id and often reworded. Each finding's `key` is
`copilot|<path>|<title>`. Before raising one, look its key up in
`context.copilot_dispositions`; when it is not there, compare the finding
with the recorded keys for the same path, and when it names the same
defect as one of them, record its key with that verdict and raise
nothing. When it is not clearly the same defect, raise it. A finding
whose key, or the key whose defect it repeats, holds `retry` is not a
repeat: no agent judged it, so raise it with that key as its
`copilot_key`, and step 07 records the new verdict there. The exit-2
whole-body item above has no key a later review can repeat, so its
`retry` is not raised again; it stays in `context.needs_human_items`.

A review whose `copilot|review|<review id>` is in `context.copilot_dispositions`
is dropped before its body is written out or parsed. Step 03 records that
key as `settled` when the script returns no finding or every finding is
dropped as a repeat; step 07 records it once every finding of the review
has a key there. Under `--dry-run` nothing is recorded in
`context.copilot_dispositions`.
`pr-watch/references/known-bots-overlay.md` keeps the same keys in its
progress file.

## Unknown-bot fallback

If the commenter is not in the table above, apply these rules:

1. **Skip** if body is an approval: matches `/^(LGTM|👍|✅|approved|looks good)[\s.!]*$/i`, or body is empty.
2. **Skip** if body is only HTML comments (matches `/\A\s*(<!--.*?-->\s*)+\z/s`).
3. **Skip** if body is a `<details>` summary with no actionable text inside (detect by stripping `<details>/<summary>` tags and checking if remaining text is empty or a single link).
4. Otherwise **treat as actionable**. Safer default for unknown sources.

## Adding team-specific bots

Teams often run internal review bots that aren't in the default list.
Extend by appending rows to the default table.

### Example 1 — scorecard-style review bot with anchor comment

A review bot that posts a canonical anchor comment and pointer-only
review submissions.

Add:

| `<your-bot>[bot]` | Top-level PR comment | `<!-- your-review-id -->` HTML anchor | Parse — the anchor comment carries the canonical finding list; scores 3/5 or higher are actionable |
| `<your-bot>[bot]` | Review body | `🟡 N/5 — <text> — [View full review]` or similar pointer-only body | Skip — the review body is a pointer to the anchor; anchor is canonical |

Parsing rule for the anchor:
- The anchor body contains a findings list (table or bullets). Extract
  each finding as one item. The score line indicates severity:
  - `5/5` — blocker
  - `4/5` — important
  - `3/5` — review recommended (actionable unless trivial)
  - `2/5` or lower — skip

### Example 2 — AI-generated summary + review bot

A bot that posts "AI Generated Pull Request Summary" (wrapper,
descriptive) and "AI Generated Pull Request Review" (parse).

Add:

| `<your-bot>[bot]` | Top-level PR comment | `# AI Generated Pull Request Summary` | Skip — wrapper text, descriptive only |
| `<your-bot>[bot]` | Top-level PR comment | `# AI Generated Pull Request Review` | Parse — extract findings inside `<details>` blocks; each finding is actionable |

Parsing rule for "AI Generated Pull Request Review":
- Findings live inside `<details>` blocks. Each `<summary>` is a
  finding title; the block body contains the evidence + proposed
  change. Extract one actionable item per `<details>` block whose
  summary does not start with "Pull request overview" or "Summary"
  (those are wrappers).

## Rules for adding new rows

When adding a team-specific bot rule:
1. **Login** — exact match. Use the GitHub/AzDO login that appears in
   the comment author field.
2. **Where it posts** — one of `inline` (review comments),
   `top-level PR comment` (issue comments), or `review body`.
3. **Signature** — either a substring the body starts with, or a
   distinctive HTML anchor comment (e.g., `<!-- my-bot-id -->`).
   Keep it specific enough to not false-match other bots.
4. **Classification** — one of `Skip`, `Actionable`, `Parse`.
   `Parse` requires a parsing subsection explaining how to extract
   individual findings from the comment body.
