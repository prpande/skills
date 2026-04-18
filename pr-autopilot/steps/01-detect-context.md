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
