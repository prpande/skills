# Loop step 06 — Commit and push

Stage the fixer changes, commit with a structured message, push to remote.

## Skip conditions

- `context.files_changed_this_iteration` is empty. Proceed directly to
  step 07 (replies only, no push needed).

## Pre-stage secret scan

Re-run the patterns from `references/secret-scan-rules.md` across
`context.files_changed_this_iteration`. Any match halts the skill with the
BLOCK message from the reference. User must resolve before re-invoking.

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
git -c commit.gpgsign=false commit -m "$(cat <<EOF
Address PR review feedback (#${PR})

- ${AGENT1_REASON}
- ${AGENT2_REASON}
EOF
)"
```

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
