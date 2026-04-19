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

Commit signing follows the user's local git configuration — do NOT pass
`-c commit.gpgsign=false`, `--no-gpg-sign`, or `--no-verify`. This honors
the hard rule in the orchestrator SKILL.md ("never bypass signing unless
the user explicitly asks"). If a signing setup is broken locally, surface
the failure to the user rather than silencing it.

The actual `git commit` invocation is shown in the "Emit
`git_commit_argv`" subsection below — the same `COMMIT_MSG` heredoc
feeds both the log event and the commit, so we don't render two
copies of it here.

### Emit `git_commit_argv` for S06.3 audit trail

Immediately **before** the `git commit` invocation, emit a
`git_commit_argv` log event recording the exact flags this step is about
to use. Invariant S06.3 (`invariants.md`) checks this event to verify no
hook-skipping / signing-bypass flag was used — checking the commit
message (as the α version did) is meaningless because those flags live
in argv, never in the message.

Build the commit-flag list in a Bash array used as the single source of
truth for **both** the log event and the real `git commit`. Any future
flag addition MUST update this array — that's the point: the log is
honest about what git actually received.

```bash
# Build the message first via heredoc into a shell variable, so the
# COMMIT_ARGS array can reference it. Never inline the heredoc inside
# the array definition — heredocs inside array contexts don't expand
# on all Bash versions.
COMMIT_MSG=$(cat <<EOF
Address PR review feedback (#${PR})

- ${AGENT1_REASON}
- ${AGENT2_REASON}
EOF
)

# Source-of-truth flag list. If a future revision adds a flag, append
# it here so both the log and the commit see it.
# Forbidden by orchestrator hard rule (do NOT add): --no-verify,
# --no-gpg-sign, -c commit.gpgsign=false.
COMMIT_ARGS=(-m "$COMMIT_MSG")

# Flat space-joined string for the log event. Includes the message
# arg — S06.3's grep targets known forbidden-flag tokens which will
# never appear in a legitimate commit message, so lossiness is fine.
COMMIT_ARGV_STR="${COMMIT_ARGS[*]}"

# Second-precision UTC timestamp. %3N (millisecond) is GNU-date
# specific and prints a literal "%3N" on macOS BSD date — use the
# portable second-precision form instead. context-schema.md's
# validation rule #5 accepts both precisions.
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

printf '%s\n' "{\"ts\":\"$TS\",\"pr\":${PR:-0},\"session_id\":\"$SESSION_ID\",\"iteration\":${ITERATION:-0},\"step\":\"06-commit-push\",\"event\":\"git_commit_argv\",\"data\":{\"argv\":\"$COMMIT_ARGV_STR\"}}" >> "$LOG"

# Invoke git with the exact same argv we just logged.
git commit "${COMMIT_ARGS[@]}"
```

`argv` is a flat space-joined string, not a JSON array — avoids
requiring `jq` for construction. The commit message ends up in the
string; S06.3's grep targets (`--no-verify`, `--no-gpg-sign`,
`-c commit.gpgsign=false`) should never appear in legitimate commit
content. If a future commit message must legitimately discuss those
flags (e.g., "document --no-verify behavior"), quote the argv-detection
regex with word boundaries in S06.3 and escape accordingly — not a
problem in practice for automated fix commits.

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
