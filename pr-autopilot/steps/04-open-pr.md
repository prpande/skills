# Step 04 — Open PR

Create the first commit (including spec updates from step 03) and open
the PR.

## 4a — Secret scan (BLOCKING)

Apply `pr-loop-lib/references/secret-scan-rules.md` to every file in
`context.uncommitted` (filtered to "related" per step 01) plus every file
in `context.spec_updates` + any file modified by step 02 fixer dispatches.

Any match → halt with the BLOCK message from the secret-scan reference.
Do not stage, do not push.

## 4b — Commit and push

Stage exactly the files:

- `context.uncommitted` (the "related" subset from step 01, if user opted
  in)
- Files modified by step 02 preflight fixers
- Files modified by step 03 spec updates

```bash
git add <specific paths>
```

Never `git add .` or `git add -A`.

Commit message convention detection:
- Check `CONTRIBUTING.md` for commit-message guidance.
- Else check the last 20 commits on the base branch for patterns
  (`feat:`, `fix:`, `chore:`, etc.).
- Apply detected pattern; if none detected, use a short imperative subject
  focused on the "why".

Subject inferred from `context.what_was_built` (from step 02) + the
dominant change category.

Body: one-paragraph summary pointing to the spec file(s) that motivate
the change, if any.

```bash
git commit -m "$(cat <<EOF
<subject>

<body>
EOF
)"
```

Commit signing follows the user's local git configuration. Do NOT pass
`-c commit.gpgsign=false`, `--no-gpg-sign`, or `--no-verify` — the
orchestrator SKILL.md hard rule forbids bypassing signing or hooks unless
the user explicitly asks. If signing fails locally, surface the error
instead of silencing it.

Push with upstream tracking on first push:
```bash
git push -u origin <branch>
```

On subsequent invocations (if the branch already has an upstream),
plain `git push`.

## 4c — Fill PR template

If `context.template_path` is set:
1. Read the template file.
2. Parse section headings (lines starting with `##`).
3. Auto-fill each section per the Section Fill Rules below.
4. Replace any remaining `PR Author TODO:` placeholders with the
   best-effort prose from the fill rules.
5. Write to `/tmp/pr-body.md`.

If `context.template_path` is empty:
Use `pr-loop-lib/references/pr-template-fallback.md` template. Apply the
same fill rules.

### Section Fill Rules

| Section pattern | Fill source |
|---|---|
| `## Overview` or `## Summary` | 2-3 sentence inferred "why" from conversation + spec files + commit messages |
| `## Changes` | Files Changed table (`git diff --stat` + one-line per file) plus bullet summary of material changes |
| `## Security Impact` | Heuristic classifier (auth/authz, crypto, input validation, new endpoints, DB patterns, logging that could expose data). Append "No security impact." checkbox style or describe the impact |
| `## Testing` | Test count and type summary from any locally-run suites, plus any spec-referenced test-plan links |
| `## Related Work` | Auto-linked tickets (`AB#\d+`, `[A-Z]+-\d+`, `#\d+`) + any cross-repo PR URLs found in branch name or commit messages |
| `## Known minor observations` (only if `context.preflight_minor_findings` non-empty) | Bulleted list of the minor findings with `file:line` refs |
| `## Spec alignment notes` (only if `context.spec_alignment_notes` non-empty) | Bullet list summarizing spec updates |

## 4d — Create PR

GitHub:
```bash
gh pr create \
  --title "<title>" \
  --body "$(cat /tmp/pr-body.md)" \
  --base "$BASE"
```

AzDO:
```bash
az repos pr create \
  --title "<title>" \
  --description "@/tmp/pr-body.md" \
  --source-branch "$BRANCH" \
  --target-branch "$BASE"
```

Title:
- If first-commit subject is conventional-commit style (`feat:`, `fix:`,
  etc.), use that.
- Else derive from the Overview section first sentence, ≤ 70 characters.

## 4e — Record outputs

```
context.pr_number = <from create response>
context.pr_url = <from create response>
context.last_push_timestamp = <committer timestamp of first commit>
context.last_push_sha = <HEAD SHA after push>
```

These seed the loop library.

## 4f — Announce and hand off

Print:
```
PR opened: <url>
Entering comment loop. Next fetch in 10 minutes.
```

Then hand off to `pr-loop-lib/steps/01-wait-cycle.md` (the wait is on —
first fetch will happen after the delay).

## 4g — Invoke host-native code-review skill (fire-and-forget)

After `gh pr create` (or `az repos pr create`) succeeds and
`context.pr_number` + `context.pr_url` are recorded, invoke the host's
native code-review skill. Its output becomes a PR comment that iter 1
of the comment loop processes.

### Host-skill table

| `context.host_platform` | Skill name | Invocation | Posts to PR? |
|---|---|---|---|
| `claude-code` | `review` | Use the Skill tool: `Skill(skill="review", args="<PR>")` | **No — orchestrator must post** (see below) |
| `codex` | (not yet mapped) | Skip; log `code_review_invoked` with `skipped: true` | n/a |
| `gemini` | (not yet mapped) | Skip; log `code_review_invoked` with `skipped: true` | n/a |
| `other` | (none) | Skip; log `code_review_invoked` with `skipped: true` | n/a |

The claude-code host exposes the skill as `review` (not `code-review`).
Earlier revisions of this table named it `code-review` — that was
documentation drift; the slash-command / skill name in installed
claude-code is `review`.

### Invocation

1. Look up the skill name for `context.host_platform` in the table above.
2. If the skill is mapped:
   a. Log a `code_review_invoked` event with `host`, `skill`, and
      current UTC timestamp.
   b. Invoke the skill via the host's skill-dispatch mechanism.
      The claude-code `review` skill renders its review body into the
      orchestrator's context — **it does not post to the PR itself**.
      The orchestrator MUST capture the rendered review and post it as
      a top-level PR comment (`gh pr comment <PR> --body "..."`) so
      iter 1's Filter B.5 can rescue and process it.
   c. Convention for the posted body: begin with `### Code review\n`
      so Filter B.5's rescue pattern matches. Findings follow the
      numbered-item format documented in
      `pr-loop-lib/steps/03-triage.md` (Filter B.5 rescue).
   d. Set `context.code_review_invoked = true` and
      `context.code_review_invoked_at = <timestamp>`.
3. If not mapped:
   a. Log `code_review_invoked` with `{host, skipped: true}`.
   b. Leave `context.code_review_invoked = false`.

### Why "post once and continue"

The `review` skill takes 1-3 minutes to render. We pay that inline
(it returns to the orchestrator's context), but the orchestrator then
posts the output and continues without waiting for reviewer-bot
roundtrips. The loop's step 01 waits 10 minutes before the first
comment fetch, so the posted `/code-review` comment lands in iter 1
naturally alongside any Copilot review.

### Rerun on `pr-followup`

When `pr-followup` re-enters the loop later, do NOT re-invoke
`/code-review`. The skill's own eligibility check prevents duplicate
reviews (it checks whether the same user has already posted a review
comment). `pr-followup` skips step 04g regardless.
