# Step 04 — Open PR

Fill the PR body, check every shipped text against the code, push, and
open the PR. All review and its fixes already happened in step 03.5;
the branch is committed locally and not yet pushed. Under `--dry-run`,
4b writes its commit message to the dry-run directory without
committing, and 4c-4g are skipped; the body stays in the dry-run
directory as `pr-body.md`.

## 4a — Fill PR template

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
| `## Spec alignment notes` (only if `context.spec_alignment_notes` non-empty) | Bullet list summarizing spec updates |
| `## Deliberate differences and scope` (only if `context.declarations` non-empty) | One bullet per declaration: the statement, then `file:line` when it has one. Scope entries say where the remaining work is tracked. Added after `## Changes` when the template has no such section |
| `## Open questions for reviewers` (only if any `internal_review_findings` entry is `needs-human`) | One bullet per entry: the question, and `file:line` |

Internal review findings reach the PR only as these two sections. The
full record stays in the local review summary at
`<repo-root>/.pr-autopilot/pr-<N>-review-summary.md`.

## 4b — Shipped-text check

Every text the PR ships makes claims about the code, and reviewers
often find those claims wrong. Check them all once, after the body
exists and before anything is pushed.

Dispatch one `pr-reviewer` agent, `model: "sonnet"`. Fill the prompt
placeholders by mode:

| Placeholder | Normal run | `--dry-run` |
|---|---|---|
| `<code_ref>` | `head_sha` | the working tree (implementation, simplify edits and review fixes are uncommitted) |
| `<commit_messages>` | output of `git log --format=%B <base_sha>..<head_sha>` | the intended messages saved in the dry-run directory (`commit-msg.txt` and any other commit message file there) |
| `<diff_source>` | `git diff <base_sha>...HEAD` | `git diff <base_sha>` plus each in-scope untracked file as a new-file diff |

Prompt:

```
Check every claim this PR ships against the code at <code_ref>. Read-only.

PR body: /tmp/pr-body.md
Commit messages: <commit_messages>
Diff: <repo-root>/.pr-autopilot/branch-<slug>.diff, rewritten before dispatch as <diff_source>
Context map: <context_map_path or "none">

Texts to check: every PR body section (Security Impact and the file
table included), the commit messages, and in the diff: Swagger/OpenAPI
text and XML or doc comments, code comments, committed docs, and test
display names. For each claim (a behaviour, a name, a count, a status
code, a reason something is kept), check it against the code.

Report a claim when:
- the code does something else, or the named thing does not exist
- a count or list in the body does not match the diff
- it describes history (an earlier version, a rename, a fix round)
  instead of what the code does now
- it holds a local file path (a drive letter or home folder)
- a "Deliberate differences" bullet does not match the code it names

Return JSON: [{"where": "body" | "commit" | "code", "file": <path or
null>, "line": <int or null>, "claim": "...", "truth": "...",
"fix": "replacement text"}]. Return [] when every claim holds.
```

Apply the results:
- `body`: edit `/tmp/pr-body.md`.
- `code`: edit the text in place (text only, no behaviour change), then
  run the build and test commands detected per the Command detection
  table in `pr-loop-lib/steps/04.5-local-verify.md`, under its Execution
  rules. Do not invoke 04.5 as a step: it skips when
  `context.files_changed_this_iteration` is empty, which it is here.
  Before editing, copy each target file to
  `<repo-root>/.pr-autopilot/text-fix-snapshot/`; under `--dry-run` the
  tree also holds uncommitted implementation and review fixes. On
  failure, copy the snapshots back over the edited files, never `git
  checkout`, and list the claim in the final report as uncorrected. On pass, secret scan the changed
  files (BLOCKING) and commit locally:
  `Correct shipped text to match the code`.
- `commit`: commits are local and unpushed, but never rewrite history
  here. Put the correction in the body of the text-fix commit above. When
  there is no text-fix commit, create an empty commit
  (`git commit --allow-empty`) with the same subject and the correction
  in its body, so it is pushed with the branch. List it in the final
  report.

Log `shipped_text_checked {claims_reported, fixed_body, fixed_code}`.
A malformed reply is logged as an `error` event and the step continues.

## 4c — Push

Push with upstream tracking on first push:
```bash
git push -u origin <branch>
```

On subsequent invocations (if the branch already has an upstream),
plain `git push`.

## 4d — Create PR

GitHub:
```bash
gh pr create \
  --title "<title>" \
  --body-file /tmp/pr-body.md \
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
context.last_push_timestamp = <committer timestamp of HEAD at push>
context.last_push_sha = <HEAD SHA after push>
```

These seed the loop library. Every commit is in this one push, so iter
1's Filter A cursor starts at the PR's own head and drops no reviewer
comment posted after it.

## 4f — Announce

Print:
```
PR opened: <url>
Pre-open review: <n> findings fixed, <n> declared, <n> open questions, <n> dismissed by /code-review.
Entering comment loop. Next fetch in 5 minutes (loop exits after two consecutive quiescent iterations).
```

## 4g — Self-post guard, then hand off

Verify per `pr-loop-lib/references/invariants.md`:

- **S04g.1** — No top-level PR comment authored by
  `context.self_login` has a **first-line** body matching
  `^\s*#{1,6}\s*code[\s-]*review\b` (case-insensitive). Checked via
  the paginating REST endpoint (required because `gh pr view --json
  comments` does not paginate and can miss comments past the first
  page on busy PRs):

  ```bash
  OWNER_REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
  # Capture output and exit code separately — piping directly to grep
  # masks gh api failures: if gh api errors, grep gets empty stdin,
  # exits 1 (no match), and the || branch falsely prints "OK".
  SELF_COMMENT_LINES=$(gh api "repos/${OWNER_REPO}/issues/${PR}/comments" --paginate \
    --jq '.[] | select(.user.login == "'"$SELF_LOGIN"'") | .body | split("\n")[0]' 2>&1)
  GH_EXIT=$?
  if [ "$GH_EXIT" -ne 0 ]; then
    echo "HALT S04g.1: gh api failed (exit ${GH_EXIT}): ${SELF_COMMENT_LINES}"
    exit 1
  fi
  if echo "$SELF_COMMENT_LINES" \
       | grep -qiE '^[[:space:]]*#{1,6}[[:space:]]*code[[:space:]-]*review\b'; then
    echo "HALT S04g.1: self-authored code-review comment found on PR #${PR}"
    exit 1
  fi
  echo "S04g.1: OK — no self-authored code-review comment on PR #${PR}"
  ```

  Pure `gh` + its embedded jq engine; no external dep introduced.
  Breakdown of the `--jq` filter:
  - `.[] | select(.user.login == "$SELF_LOGIN")` — iterate comments,
    keep only self-authored.
  - `.body | split("\n")[0]` — split body on newlines, take the
    first element (possibly blank).
  - One line per comment is emitted; `grep -iE` tests each against the
    code-review heading regex, tolerating leading whitespace via
    `^[[:space:]]*`.

  Comments that start with a blank first line (rare) produce an empty
  stdin line to grep, which doesn't match the heading regex — safe.
  `gh api --paginate` reads every page so the check can't miss a
  comment past page 1 on busy PRs.

  **Escaping footnote.** An earlier revision of this step used
  `map(select(test("\\S")))` to drop blank lines inside jq. The
  `\\S` escape survives single-quoted shell interpolation in isolation
  but is fragile through several nesting layers (heredocs, `$(…)`
  substitution, some harnesses), and a broken jq parse silently
  short-circuits the pipeline — grep gets empty stdin and the `||`
  branch prints "OK" even though the check didn't run. The
  `split("\n")[0]` form avoids all of that by not using a regex
  inside jq at all.

  A hit means something posted `/code-review` output to the PR, which
  this skill never does. Hard halt with a diagnostic naming the
  regressing commit / call-site.

Then hand off to `pr-loop-lib/steps/01-wait-cycle.md` (the wait is on —
first fetch will happen after the delay).
