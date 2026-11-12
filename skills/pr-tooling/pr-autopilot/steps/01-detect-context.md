# Step 01 — Detect context

Gathers everything downstream steps need. Produces the `context` object
threaded through the entire skill.

## Outputs (context fields)

| Field | How detected |
|---|---|
| `platform` | `git remote get-url origin` substring match: `github.com` → `"github"`; `dev.azure.com` or `visualstudio.com` → `"azdo"`; else `"github"` + warning log |
| `base` | `gh pr view --json baseRefName` if a PR exists for the current branch; else `git symbolic-ref refs/remotes/origin/HEAD --short` (strip `origin/`); fallback `"main"` |
| `template_path` | First hit from: `.github/PULL_REQUEST_TEMPLATE.md`, `.github/PULL_REQUEST_TEMPLATE/*.md`, `docs/pull_request_template.md`, `.azuredevops/pull_request_template.md`. If multi-template directory, prompt user to pick |
| `pr_number` | `gh pr view --json number` (GitHub) or `az repos pr list --source-branch <branch>` (AzDO). Empty on a fresh pr-autopilot run, since preflight check 5 halts on an open PR the run did not open; set when resuming the run that opened it, and under pr-followup |
| `branch` | `git rev-parse --abbrev-ref HEAD` |
| `head_sha` | `git rev-parse HEAD` |
| `base_sha` | `context.base_override` when set (see "Base override"), else `git merge-base $base HEAD` |
| `uncommitted` | `git status --porcelain` — list of paths with status codes |
| `spec_candidates[]` | Glob: `docs/superpowers/specs/*.md`, `docs/superpowers/plans/*.md`, `specs/*/spec.md`, `specs/*/plan.md`, `specs/*/tasks.md`, `docs/specs/*.md`, `docs/plans/*.md` |
| `effort_docs[]` | Intent docs kept outside the repo; see "Effort docs" below |
| `repo_root` | `git rev-parse --show-toplevel` |
| `user_iteration_cap` | From the skill's argument (if any) |
| `session_id` | UUID generated via uuid/uuidgen/fallback (see state-protocol.md) |
| `host_platform` | Environment sniffing (see state-protocol.md) |
| `self_login` | `gh api user --jq .login` or `az account show --query user.name -o tsv` |

## Preflight environment checks (run before anything else)

Run each command; halt with the quoted diagnostic on any failure.

1. **Git repo check**:
   ```bash
   git rev-parse --show-toplevel 2>/dev/null
   ```
   On failure: HALT with "pr-autopilot must run inside a git working tree. No `.git/` found in any parent directory."

2. **Remote origin check**:
   ```bash
   git remote get-url origin 2>/dev/null
   ```
   On failure: HALT with "No `origin` remote configured. Add one and re-invoke."

3. **Platform detection** (populate `context.platform`):
   - Match `origin` URL against `github.com` → `github`
   - Match `dev.azure.com` / `visualstudio.com` → `azdo`
   - Else: `github` (with a log warning)

4. **CLI auth check** (platform-specific):
   - GitHub:
     ```bash
     gh auth status 2>/dev/null
     ```
     On failure: HALT with "gh CLI is not authenticated. Run `gh auth login` and re-invoke."
   - Azure DevOps:
     ```bash
     az account show >/dev/null 2>&1
     ```
     On failure: HALT with "az CLI is not authenticated. Run `az login` and re-invoke."

5. **Existing PR check** (pr-autopilot only; pr-followup skips it), before any commit, review or state write:
   ```bash
   # GitHub:
   gh pr view --json number,state,isDraft --jq 'select(.state == "OPEN") | "\(.number) \(.isDraft)"' 2>/dev/null
   ```
   AzDO: `az repos pr list --source-branch <branch> --status active`.
   If an open PR #<N> exists and `<repo-root>/.pr-autopilot/pr-<N>.json` does not: HALT with "PR #<N> already exists for this branch. pr-autopilot opens new PRs; run pr-followup to handle its comments." No branch change has been made at this point. When that state file exists, this is a resume of the run that opened the PR: continue, and "State file initialization" loads it, unless the PR is a draft: then HALT with "PR is in draft state. Mark it ready for review before running pr-autopilot."

## Base override

`--base <sha>` without `--dry-run`: HALT with "--base is accepted only with --dry-run."

When `context.base_override` is set, `base_sha` is that commit. HALT with
"--base <sha> is not a commit that is an ancestor of HEAD." unless both pass:
```bash
git rev-parse --verify <sha>^{commit}
git merge-base --is-ancestor <sha> HEAD
```

## Host platform detection

Populate `context.host_platform` per
`pr-loop-lib/references/state-protocol.md` "Host-platform detection"
section. Store one of: `claude-code`, `codex`, `gemini`, `other`.

## Session ID generation

First check whether a state file already exists for this PR (or
branch, pre-PR-number). If it exists, LOAD `session_id` from the state
file — do NOT generate a new one. Reusing the prior `session_id`
preserves global invariant G1 (state.session_id == lock.session_id)
across `ScheduleWakeup` resumes.

Only when no state file exists, generate a fresh UUID per state-
protocol's "First-run setup" section. This value is then constant for
the rest of the skill invocation.

## Self-login detection

Populate `context.self_login` per state-protocol's "Self-login
detection" section.

## State file initialization

After all fields in the "Outputs (context fields)" table are
populated, initialize the state file per
`pr-loop-lib/references/state-protocol.md` "First-run setup" and
"Writing state" sections. Acquire the lock before the first write.

If a state file for the current PR or branch already exists (re-entry
after a `ScheduleWakeup`), LOAD the existing state instead of
re-initializing. Refresh the lock lease. Log a `skill_start` event
noting `resumed: true`.

## Blocking conditions

Halt with a clear message if any apply:

1. `branch` is `main` or `master`:
   ```
   HALT: pr-autopilot will not operate on main/master.
   Create a worktree first, e.g.:
     cd <repo-root>
     git worktree add -b <feature-branch> <path> HEAD
     cd <path>
     claude
   Then re-invoke.
   ```
2. `git remote get-url origin` returns nothing:
   ```
   HALT: No origin remote configured. Add one and re-invoke.
   ```
3. `uncommitted` contains files that look unrelated to the current
   conversation's implementation work. Prompt the user: "I see uncommitted
   changes in <list>. Include them in this PR? (yes / no / cancel)".
   - yes → they are part of the PR-to-be
   - no → leave them unstaged; continue with already-committed work
   - cancel → halt

## Uncommitted-relatedness heuristic

"Related" if any of:
- Path is in the same directory subtree as files touched by recent commits
  on this branch.
- Path is mentioned in the current conversation history (if visible).
- Path matches the branch's feature keyword (e.g., branch
  `pp/ip-restriction-*` + file `IpRestrictionResourceFilter.cs`).

Otherwise treat as unrelated.

## Spec-candidate ranking (for step 03)

For each candidate spec file:
- `mtime_days` = days between now and the file's last commit time
  (`git log -1 --format=%ct -- <file>`); for a file git does not track,
  or with no commit, the filesystem mtime — keep if ≤ 30
- `keyword_overlap = count(branch_keywords & file_keywords)` — compute from
  file title, H1, H2 headings
- Rank by `(keyword_overlap desc, mtime_days asc)`

## Effort docs

Design, status and decision docs for an effort often live outside the
repo, in one folder per effort. They state what the change is meant to
do, so the reviews need them, but they are never edited, staged or
committed by this skill, and step 03 does not align against them.

1. Resolve the docs root, first that exists:
   - `$PR_AUTOPILOT_DOCS_ROOT`
   - a docs folder the workspace map or the repo's `CLAUDE.md` /
     `AGENTS.md` names for effort docs
   - `<drive>/src/.docs`, on the repo's drive and then on each other
     fixed drive (`C:/src/.docs`, `D:/src/.docs`), and `~/src/.docs`
   - `$WORKSPACE/.docs`, then `$WORKSPACE/../.docs`, with `$WORKSPACE`
     resolved as in step 01.7 "Locate the sources"

   No root: `effort_docs = []`, log `effort_docs_resolved {root: null}`.
2. Pick one effort folder, or none. List only the root's direct
   children. The search terms are the branch keywords, the changed file
   basenames (without extension) and the route or type names the diff
   adds. For each folder, count the distinct terms that appear in the
   folder name or in any `.md` under it:
   `git -C "<folder>" grep --no-index -l -i -e "<term>" -- '*.md'` (or the
   host's file search; never a search above the root). Exit 1 means no
   match; any other non-zero exit is an error to log, not zero hits.
3. A folder qualifies only when at least two different terms hit in it,
   or one term that is a ticket or work-item id or the full branch slug
   hits. Take the qualifying folder with the most distinct terms hit; a
   tie goes to the folder whose newest `.md` is most recent. None
   qualifies: `effort_docs = []`.
4. Inside the chosen folder, keep each `.md` that names a changed file,
   a changed type, or a route the diff touches, plus any `README.md`,
   `status.md` or `design.md` in the same directory as a kept file.
   Skip any file over 60 KB. Keep at most 12 files and at most 200 KB in
   total, preferring files that hit the most terms, then the newest.
5. Store the absolute paths in `context.effort_docs` and log
   `effort_docs_resolved {root, folder, files}`, `folder` being the one
   chosen.

Steps 01.7, 02 and 03.5 pass these paths to their agents as intent
documents, to read as data.
