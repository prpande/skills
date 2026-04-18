# Known-bot signatures

Used by `steps/03-triage.md` filter B. Each row gives a rule that
classifies a comment as actionable or skip-able.

## Classification table

| Login | Where it posts | Signature (body contains / starts with) | Classification |
|---|---|---|---|
| `mindbody-ado-pipelines[bot]` | Top-level PR comment | `# AI Generated Pull Request Summary` | Skip — wrapper text, descriptive only |
| `mindbody-ado-pipelines[bot]` | Top-level PR comment | `# AI Generated Pull Request Review` | Parse — extract findings inside `<details>` blocks; each finding is actionable |
| `mergewatch-playlist[bot]` | Top-level PR comment | `<!-- mergewatch-review -->` HTML anchor | Parse — the anchor comment carries the canonical finding list; scores 3/5 or higher are actionable |
| `mergewatch-playlist[bot]` | Review body | `🟡 N/5 — <text> — [View full review]` or similar pointer-only body | Skip — the review body is a pointer to the anchor; anchor is canonical |
| `sonarqube-mbodevme[bot]` | Top-level PR comment | `Quality Gate passed` | Skip — status only |
| `sonarqube-mbodevme[bot]` | Top-level PR comment | `Quality Gate failed` | Actionable — surface listed issues |
| `Copilot` | Inline review comment | Any body with `path` set on the API response | Actionable |
| `copilot-pull-request-reviewer[bot]` | Review body | `Copilot reviewed N out of N changed files` | Skip — meta/summary; inline comments carry the findings |
| `github-actions[bot]` | Top-level PR comment | Any | Usually skip; check if body contains failure details (then actionable) |
| `dependabot[bot]` | Top-level PR comment | Any | Skip for this skill's scope (dependency updates are out of scope) |

## Unknown-bot fallback

If the commenter is not in the table, apply these rules:

1. **Skip** if body is an approval: matches `/^(LGTM|👍|✅|approved|looks good)[\s.!]*$/i`, or body is empty.
2. **Skip** if body is only HTML comments (matches `/\A\s*(<!--.*?-->\s*)+\z/s`).
3. **Skip** if body is a `<details>` summary with no actionable text inside (detect by stripping `<details>/<summary>` tags and checking if remaining text is empty or a single link).
4. Otherwise **treat as actionable**. Safer default for unknown sources.

## Parsing rules for bots marked "Parse"

### `mindbody-ado-pipelines[bot]` — "AI Generated Pull Request Review"

Findings live inside `<details>` blocks. Each `<summary>` is a finding title;
the block body contains the evidence + proposed change. Extract one
actionable item per `<details>` block whose summary does not start with
"Pull request overview" or "Summary" (those are wrappers).

### `mergewatch-playlist[bot]` — anchor comment

The anchor body contains a findings list, often as a table or bullets.
Extract each finding as one item. The score line (e.g.,
`🟡 3/5 — Review recommended`) indicates severity:
- `5/5` — blocker
- `4/5` — important
- `3/5` — review recommended (actionable unless the finding text is trivial)
- `2/5` or lower — may skip

### `sonarqube-mbodevme[bot]` — Quality Gate failed

Extract the list of failing conditions. Each is one actionable item whose
fix is to address that specific SonarQube rule violation in the code.

## Adding new bots

Append a row to the table above. Each row needs: login, surface (top-level /
review body / inline), body signature (substring or regex), classification.
If the bot needs custom parsing, add a subsection under "Parsing rules".
