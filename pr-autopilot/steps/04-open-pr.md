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
| `## Spec alignment notes` (only if `context.spec_alignment_notes` non-empty) | Bullet list summarizing spec updates |

**Note (β):** α had a `## Known minor observations` row here that
folded `context.preflight_minor_findings` into the PR body. β removes
this entirely — Minor findings from preflight live only in the local
review-summary artifact at `<repo-root>/.pr-autopilot/pr-<N>-review-
summary.md`, never on the PR. See `steps/02-preflight-review.md`
"Review-summary artifact" and Section 5 of the β spec.

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

## 4g — Invoke host-native code-review skill (internal capture only)

After `gh pr create` (or `az repos pr create`) succeeds and
`context.pr_number` + `context.pr_url` are recorded, invoke the host's
native code-review skill. **Under β, the rendered review is captured
into the orchestrator's context and processed internally — it is NOT
posted as a PR comment.** Findings are deduped against preflight and
the non-duplicates are dispatched through the same fixer mechanics
preflight uses (step 04-dispatch-fixers, scoped to `P02.*`). Any
resulting fixes are committed + pushed before the comment loop begins.

### Host-skill table

| `context.host_platform` | Skill name | Invocation | Posts to PR? |
|---|---|---|---|
| `claude-code` | `review` | Use the Skill tool: `Skill(skill="review", args="<PR>")` | **No — captured locally; not posted** |
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
      orchestrator's context.
   c. **Capture** the rendered review into
      `context.code_review_raw_output`. **Do NOT call `gh pr
      comment` / `az repos pr comment` with the rendered body.**
      No under any branch. The whole point of β's Section 5 is that
      this output stays private to the invoking user.
   d. Set `context.code_review_invoked = true` and
      `context.code_review_invoked_at = <timestamp>`.
   e. Parse, dedup, dispatch (next subsection).
3. If not mapped:
   a. Log `code_review_invoked` with `{host, skipped: true}`.
   b. Leave `context.code_review_invoked = false`. Skip the parse /
      dispatch / commit subsections below.

### Parse the captured output

The `review` skill's output format is the numbered-finding shape
Filter B.5 Stage 1 expects. Apply the same parser:

```
N. <description> (<source>)

<https://github.com/owner/repo/blob/SHA/path#L<start>-L<end>>
```

For each numbered finding, produce a record:
- `body: "<description>"` (first line of the numbered item, without
  the trailing `(<source>)`)
- `path: "<parsed from the SHA URL>"`
- `line: <start>` — INTEGER, not string; first number in
  `L<start>-L<end>`. (Same shape rule as Filter B.5 Stage 1 — storing
  as string trips G3.)
- `id: "code-review:finding-<N>"` (stable within this session;
  1-indexed by the order findings appear in
  `context.code_review_raw_output`)
- `severity: "important"` — `/code-review` findings are treated as
  Important by default. The `review` skill does not return a severity
  field, and preflight's adversarial subagent has already caught
  Critical-severity issues (dispatched inline in step 02), so what
  `/code-review` surfaces post-open is by construction Important or
  less. Operators tuning this default may set `severity: "minor"` at
  the dispatch site if `/code-review` produces verbose low-priority
  comments in a given project.
- `source: "code-review"` — marks the origin for `internal_review_findings`

If parsing fails (malformed numbered section, no `<https://...>` URL,
missing description):
- Log an `error` event with `stage: "04g-parse"`.
- Skip this finding. Do NOT dispatch malformed inputs to a fixer.

**Empty / zero-finding output.** If `context.code_review_raw_output`
is empty (the host's `review` skill returned nothing — e.g., "no
issues found") OR if parsing yields zero well-formed findings, skip
the Dedup, Dispatch, and Commit+push subsections below. Set
`context.code_review_invoked = true`, append a single
"no findings" line to the review-summary file's `/code-review`
section, and hand off to `4f`. This is the happy path — treat it as
success, not as an error.

### Dedup against preflight findings

For each parsed finding, compute its `description_hash` per the
normalization in `pr-autopilot/steps/02-preflight-review.md`
"Per-finding `description_hash`" section (five-step normalization:
strip fences/HTML → lead paragraph → lowercase+whitespace-collapse →
truncate 200 → SHA-1).

If the hash equals any `preflight_passes.merged[].description_hash`:
- Log a `triage_dedup_hit` event with
  `{feedback_id: "code-review:finding-<N>", preflight_match_id: <merged[].id>, source: "code-review"}`.
- Skip dispatching this finding (preflight already handled it).
- Append to `context.internal_review_findings` with
  `status: "captured-only"` and a note linking to the preflight entry.

### Dispatch non-duplicates

For each non-duplicate finding, dispatch a fixer subagent per the
procedure in `pr-loop-lib/steps/04-dispatch-fixers.md`. Scope of
post-dispatch invariants is `P02.*` (same as preflight); S04.* do not
apply (there is no triage `actionable[]` yet). The verifier procedure,
policy ladder, and overlap re-verify all apply unchanged — each fixer
return is verified; `feedback-wrong` verdicts roll back without
posting a reply to the PR (the reply text is captured for the local
summary only).

Record each outcome in `context.internal_review_findings`:

```json
{
  "source": "code-review",
  "severity": "important",   // /code-review findings are treated as Important by default
  "file": "...",
  "line": 42,
  "description": "...",
  "status": "fixed" | "fixed-differently" | "feedback-wrong" | "needs-human",
  "fixer_feedback_id": "code-review:finding-<N>",
  "verifier_judgement": "addresses" | "partial" | "not-addresses" | "feedback-wrong"
}
```

Append each record to the review-summary file at
`context.internal_review_summary_path` in a new `## /code-review
post-open` section (or update an existing one if step 04g is retried).

### Commit + push any resulting fixes

If any fixer landed a diff (`context.files_changed_this_iteration`
non-empty after dispatch):

1. Apply the `pr-loop-lib/steps/06-commit-push.md` procedure, with:
   - Commit subject: `Address internal /code-review findings
     (preflight)`
   - Body: one bullet per fix with the finding description + fixer
     reason.
   - Same secret scan, main-branch guard, `git_commit_argv` emission,
     and signing rules as the loop's step 06.
2. After successful push, update `context.last_push_sha` to the new
   HEAD SHA.
3. **Do NOT update `context.last_push_timestamp`** in 04g. `last_push_
   timestamp` is the cursor iter 1's Filter A uses to decide which
   comments are "new enough" to process. External reviewer bots
   (Copilot, SonarCloud) can post their own review comments in the
   seconds between `gh pr create` and 04g's push; bumping the cursor
   to 04g's push timestamp would drop those comments silently. The
   cursor stays at the PR-create commit's timestamp (set in 4e) until
   loop step 06 performs its own push in response to real PR comments.

If no fixer produced a diff (all `replied`, `not-addressing`, or
`needs-human`), do not commit. Continue to hand-off.

### Invariants

After step 04g completes, verify per
`pr-loop-lib/references/invariants.md`:

- **S04g.1** — No top-level PR comment authored by
  `context.self_login` has a **first-line** body matching
  `^\s*#{1,6}\s*code[\s-]*review\b` (case-insensitive). Checked via
  the paginating REST endpoint (required because `gh pr view --json
  comments` does not paginate and can miss comments past the first
  page on busy PRs):

  ```bash
  OWNER_REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
  # Fetch all self-authored comment bodies as a JSON array, then use
  # python3 to iterate correctly over multi-line bodies. The earlier
  # awk/jq/RS="\0" pipeline was structurally broken — `gh api --jq`
  # does not NUL-separate records, so `RS="\0"` treated the entire
  # stream as a single record and only the first comment's first line
  # was ever checked.
  python3 -c '
import json, re, subprocess, sys

owner_repo = subprocess.check_output(
    ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
    text=True,
).strip()
pr = "'"$PR"'"
self_login = "'"$SELF_LOGIN"'"

# gh api --paginate yields one JSON value per page; --slurp combines
# them into one array of arrays which we flatten.
raw = subprocess.check_output(
    ["gh", "api", f"repos/{owner_repo}/issues/{pr}/comments", "--paginate",
     "--slurp"],
    text=True,
)
pages = json.loads(raw)
bodies = [c["body"] for page in pages for c in page
          if c.get("user", {}).get("login") == self_login]

regex = re.compile(r"^\s*#{1,6}\s*code[\s-]*review\b", re.IGNORECASE)
for body in bodies:
    first = next((ln.lstrip() for ln in body.splitlines() if ln.strip()), "")
    if regex.match(first):
        print("HALT S04g.1: self-authored code-review comment found:")
        print("  first line: " + first[:120])
        sys.exit(1)
print("S04g.1: OK — no self-authored code-review comment on PR #" + pr)
'
  ```

  Using `python3` here is consistent with `scripts/validate.py` — it
  is already a build-time dependency of the skill, so no new runtime
  dep is introduced. The earlier awk/jq pipeline was broken: it tried
  to NUL-separate via `RS="\0"` but `gh api --jq` concatenates bodies
  with only a newline, making the entire stream one awk record. The
  Python version loads the JSON directly, iterates per comment, and
  extracts the first non-blank line per body correctly.

  Matching only the first non-blank line avoids a false positive when
  an unrelated comment quotes the heading in the middle of its body
  (e.g., a user discussing what the skill does). `--paginate --slurp`
  ensures every page is read so the check can't miss a comment past
  page 1 on busy PRs.

  A hit means the orchestrator regressed into α's posting behavior
  (the `gh pr comment` call from α crept back in somehow). Hard halt
  with a diagnostic naming the regressing commit / call-site.

### Rerun on `pr-followup`

When `pr-followup` re-enters the loop later, do NOT re-invoke
`/code-review`. The skill's own eligibility check prevents duplicate
reviews when the review was previously posted, but under β we no
longer post — so the eligibility signal is the stored
`context.code_review_invoked = true` flag. `pr-followup` skips step
04g regardless when that flag is true.
