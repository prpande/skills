# Loop step 06 — Commit and push

Stage the fixer changes, commit with a structured message, push to remote.

## Skip conditions

- `context.files_changed_this_iteration` is empty. Proceed directly to
  step 07 (replies only, no push needed).

## Pre-stage secret scan

Re-run the patterns from `references/secret-scan-rules.md` across
`context.files_changed_this_iteration`. Any match halts the skill with the
BLOCK message from the reference. User must resolve before re-invoking.

## Main-branch write guard (BLOCKING)

Before staging anything, verify `HEAD` is not `main`/`master`:

```bash
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$CURRENT_BRANCH" = "main" ] || [ "$CURRENT_BRANCH" = "master" ]; then
  echo "HALT: refusing to stage fixer changes while HEAD is $CURRENT_BRANCH."
  echo "Switch to the PR head branch first (\`gh pr checkout <PR>\`)."
  exit 1
fi
```

This enforces the user's global-CLAUDE.md rule against direct
main/master edits. Applies to both `pr-autopilot` and `pr-followup`.

## Stage

Stage exactly the files in `context.files_changed_this_iteration`:

```bash
git add <file1> <file2> ...
```

Never `git add .` or `git add -A` — risk of staging unrelated work.

## Commit message

The PR number comes from `context.pr_number`, exported as the shell variable
`$PR` by platform detection (see `platform/github.md` / `platform/azdo.md`).
Use `$PR` throughout — not `$PR_NUMBER` — to stay consistent with the rest
of the loop.

Format:
```
Address PR review feedback (#<$PR>)

- <agent1.reason>
- <agent2.reason>
- ...
```

One bullet per agent with a non-`not-addressing` verdict whose
`files_changed` was non-empty.

Use heredoc to avoid shell-quoting issues:

```bash
git commit -m "$(cat <<EOF
Address PR review feedback (#${PR})

- ${AGENT1_REASON}
- ${AGENT2_REASON}
EOF
)"
```

Commit signing follows the user's local git configuration — do NOT pass
`-c commit.gpgsign=false`, `--no-gpg-sign`, or `--no-verify`. This honors
the hard rule in the orchestrator SKILL.md ("never bypass signing unless
the user explicitly asks"). If a signing setup is broken locally, surface
the failure to the user rather than silencing it.

## Push

```bash
git push
```

No `--force`. No `--no-verify`.

## Update context

After successful push:
```
context.last_push_timestamp = <committer timestamp of new commit>
context.last_push_sha = <HEAD SHA after push>
```

This is how step 03's Filter A distinguishes "new since last push" on the
next iteration.
