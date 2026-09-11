# Known-bots overlay

Rows `pr-watch` appends after the table in
`pr-loop-lib/references/known-bots.md` whenever it runs Filter B. The
library file is not edited.

These accounts post as GitHub Apps. REST shows them as
`<name>[bot]`; GraphQL, which `poll.py --tails` reads, shows the bare
`<name>`, and that is the login in every record Filter B sees. The
library's rows are keyed on other logins (`sonarqube[bot]`,
`sonarqubecloud[bot]`), so without this overlay every comment here would
fall through to the unknown-bot fallback and read as actionable.

| Login | Where it posts | Signature (body starts with / contains) | Classification |
|---|---|---|---|
| `sonarqube-mbodevme` | Top-level PR comment | starts with `## [![Quality Gate passed]` | Skip — status only |
| `sonarqube-mbodevme` | Top-level PR comment | starts with `## [![Quality Gate failed]` | Actionable — surface the listed issues |
| `mindbody-ado-pipelines` | Top-level PR comment | starts with `# AI Generated Pull Request Summary` | Skip — describes the PR, no findings |
| `mindbody-ado-pipelines` | Top-level PR comment | starts with `# AI Generated Pull Request Review` | Actionable — one item, see below |
| `mergewatch-playlist` | Inline review comment | starts with `<!-- mergewatch-inline -->` | Actionable |
| `mergewatch-playlist` | Inline review comment | no `<!-- mergewatch-inline -->` marker | Skip — mergewatch answering in a thread; settles the tail |
| `mergewatch-playlist` | Top-level PR comment | starts with `<!-- mergewatch-review -->` | Parse — the summary, see below |
| `mergewatch-playlist` | Review body | starts with `<!-- mergewatch-review -->` | Parse — re-read the current summary, see below |

Signatures verified against live comments on the last 40 PRs of
`mindbody/Mindbody.Scheduling` on 2026-09-11.

## `mindbody-ado-pipelines` review

Posted once per PR, on the first gated run. The findings have no stable
markup: across 40 PRs they appear as numbered bold lines, numbered
`<summary>` headings, severity-emoji headings, and bullets under section
headings. Treat the whole body as one actionable item. The fixer splits it
into findings, fixes what it can, and escalates any finding that asks a
product or contract question. The reply is one top-level comment that
answers each finding in the review's own order.

## `mergewatch-playlist` summary

One summary comment per PR, edited in place on every push. Each push that
leaves findings also submits a new review whose body points at the
summary; that review is the event that a push changed the findings. The
library's worked example skips the pointer because `pr-autopilot`
re-reads every comment each cycle; `pr-watch` tracks top-level items by
id and would never see the edited summary again. When
either the summary or a pointer review surfaces, read the summary's
current body:

```bash
gh api "repos/$REPO/issues/$PR/comments" --paginate \
  --jq '[.[] | select(.body | startswith("<!-- mergewatch-review -->"))] | last | {id: .node_id, body}'
```

- The score line reads `> 🟢 **5/5 — …**` when there is nothing to act on;
  classify the item Skip.
- Findings are bullets of the form ``- **`<path>:<line>`** — <title>``
  under the finding sections (`### ⚠️ Unverified concerns (N)`,
  `<summary>🟡 Warnings (N)</summary>`, and any other section that
  carries such bullets). Each bullet, with the indented lines under it, is
  one actionable finding.
- Ignore the `📎 Previously reported findings` and `ℹ️ Review details`
  `<details>` blocks. A still-present finding is repeated in the live
  sections.
- Drop a finding when a `mergewatch-playlist` inline thread on the same
  path carries the same title; the thread is where it gets answered.
  Compare titles after stripping `**`, a leading emoji, and surrounding
  whitespace, case-insensitively: the inline comment's second line is
  `**🔴 <title>**`, the summary bullet's title is plain.
- Drop a finding already dispositioned. The key is
  `<summary id>|<path>|<title>`, replacing the `<parent-comment-id>:finding-<N>`
  record id that `pr-loop-lib/steps/03-triage.md` gives parsed findings:
  finding order changes when the summary is rewritten, so a positional
  key would re-raise answered findings. Line numbers move between pushes
  and titles do not, so the line is left out of the key. Record the
  disposition in `handled_top_level_ids` under that key, and the summary's
  own id and the pointer review's id under `parsed`.

A comment that matches no row falls through to the library's unknown-bot
fallback. When a status line changes shape, update the row here rather
than letting the fallback reply to it.
