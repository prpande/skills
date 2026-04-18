# Known-bot signatures

Used by `steps/03-triage.md` filter B. Each row gives a rule that
classifies a comment as actionable or skip-able.

## Default classification table (cross-team, ships with the skill)

| Login | Where it posts | Signature (body contains / starts with) | Classification |
|---|---|---|---|
| `Copilot` | Inline review comment | Any body with `path` set on the API response | Actionable |
| `copilot-pull-request-reviewer[bot]` | Review body | `Copilot reviewed N out of N changed files` | Skip — meta/summary; inline comments carry the findings |
| `sonarqube[bot]` (any `sonarqube*[bot]` login) | Top-level PR comment | `Quality Gate passed` | Skip — status only |
| `sonarqube[bot]` (any `sonarqube*[bot]` login) | Top-level PR comment | `Quality Gate failed` | Actionable — surface listed issues |
| `github-actions[bot]` | Top-level PR comment | Any | Usually skip; check if body contains failure details (then actionable) |
| `dependabot[bot]` | Top-level PR comment | Any | Skip for this skill's scope (dependency updates are out of scope) |

The default list is deliberately short. Only bots that are well-known
across teams ship as defaults.

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
