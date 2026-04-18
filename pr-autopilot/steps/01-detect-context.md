# Step 01 — Detect context

Gathers everything downstream steps need. Produces the `context` object
threaded through the entire skill.

## Outputs (context fields)

| Field | How detected |
|---|---|
| `platform` | `git remote get-url origin` substring match: `github.com` → `"github"`; `dev.azure.com` or `visualstudio.com` → `"azdo"`; else `"github"` + warning log |
| `base` | `gh pr view --json baseRefName` if a PR exists for the current branch; else `git symbolic-ref refs/remotes/origin/HEAD --short` (strip `origin/`); fallback `"main"` |
| `template_path` | First hit from: `.github/PULL_REQUEST_TEMPLATE.md`, `.github/PULL_REQUEST_TEMPLATE/*.md`, `docs/pull_request_template.md`, `.azuredevops/pull_request_template.md`. If multi-template directory, prompt user to pick |
| `pr_number` | `gh pr view --json number` (GitHub) or `az repos pr list --source-branch <branch>` (AzDO). Empty on first run — that is fine |
| `branch` | `git rev-parse --abbrev-ref HEAD` |
| `head_sha` | `git rev-parse HEAD` |
| `base_sha` | `git merge-base $base HEAD` |
| `uncommitted` | `git status --porcelain` — list of paths with status codes |
| `spec_candidates[]` | Glob: `docs/superpowers/specs/*.md`, `docs/superpowers/plans/*.md`, `specs/*/spec.md`, `specs/*/plan.md`, `specs/*/tasks.md`, `docs/specs/*.md`, `docs/plans/*.md` |
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

5. **Draft PR check** (only if a PR already exists for the current branch):
   ```bash
   # GitHub:
   gh pr view --json isDraft --jq .isDraft 2>/dev/null
   ```
   If result is `true`: HALT with "PR is in draft state. Mark it ready for review before running pr-autopilot."
   (pr-followup allows drafts; pr-autopilot does not.)

## Host platform detection

Populate `context.host_platform` per
`pr-loop-lib/references/state-protocol.md` "Host-platform detection"
section. Store one of: `claude-code`, `codex`, `gemini`, `other`.

## Session ID generation

Generate `context.session_id` (a UUID) per state-protocol's
"First-run setup" section. This value is constant across all
`ScheduleWakeup` resumes within the same skill invocation.

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
- `mtime_days = (now - file.mtime_days)` — keep if ≤ 30
- `keyword_overlap = count(branch_keywords & file_keywords)` — compute from
  file title, H1, H2 headings
- Rank by `(keyword_overlap desc, mtime_days asc)`
