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

### Emit `git_commit_argv` for S06.3 audit trail

Immediately **before** the `git commit` invocation, emit a
`git_commit_argv` log event recording the exact flags this step is about
to use. Invariant S06.3 (`invariants.md`) checks this event to verify no
hook-skipping / signing-bypass flag was used — checking the commit
message (as the α version did) is meaningless because those flags live
in argv, never in the message.

```bash
COMMIT_ARGV="-m <heredoc-message-placeholder>"  # populated with the exact
                                                # flags about to be passed
                                                # to `git commit`
TS=$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)
printf '%s\n' "{\"ts\":\"$TS\",\"pr\":${PR:-0},\"session_id\":\"$SESSION_ID\",\"iteration\":${ITERATION:-0},\"step\":\"06-commit-push\",\"event\":\"git_commit_argv\",\"data\":{\"argv\":\"$COMMIT_ARGV\"}}" >> "$LOG"

git commit -m "$(cat <<EOF
...
EOF
)"
```

`argv` is a flat space-joined string, not a JSON array — avoids
requiring `jq` for construction. Lossy for args with embedded spaces
(the commit message itself is the obvious such arg); for S06.3's
flag-presence grep this is fine. Do NOT interpolate the commit message
into the logged `argv` — keep `argv` to the flag tokens only, or use a
placeholder like `<heredoc-message-placeholder>` in place of the
message, so the event stays small and predictable.

This event fires once per `git commit` invocation in this step. If
this step retries a commit, emit a fresh event per retry.

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
