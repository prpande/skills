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
# it to BOTH arrays so the log and the commit stay in sync.
# Forbidden by orchestrator hard rule (do NOT add): --no-verify,
# --no-gpg-sign, -c commit.gpgsign=false.
COMMIT_ARGS=(-m "$COMMIT_MSG")           # real argv for git
COMMIT_ARGV_FLAGS=(-m "<commit-message>") # flag tokens only for the log

# Flat space-joined string for the log event — FLAGS ONLY, not the
# message. Rationale: a real commit message can contain newlines,
# quotes, backslashes, and other JSON-breaking characters that would
# corrupt the JSON-lines log. S06.3 only grep-checks for forbidden
# flag tokens, so dropping the message content is lossless for the
# predicate's purpose and keeps the log parseable.
COMMIT_ARGV_STR_RAW="${COMMIT_ARGV_FLAGS[*]}"

# JSON-escape the argv string before interpolation. Even though the
# current COMMIT_ARGV_FLAGS values are safe ASCII, defensive escaping
# keeps the JSON-lines log valid if a future flag ever introduces a
# `"` or `\` (e.g., `--author='Foo "Bar"'`). Order matters: escape
# backslashes first so the subsequent quote-escape's inserted
# backslashes don't get doubled.
COMMIT_ARGV_STR=$(printf '%s' "$COMMIT_ARGV_STR_RAW" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g')

# Second-precision UTC timestamp. %3N (millisecond) is GNU-date
# specific and prints a literal "%3N" on macOS BSD date — use the
# portable second-precision form. log-format.md's `ts` rule accepts
# both second- and millisecond-precision.
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

printf '%s\n' "{\"ts\":\"$TS\",\"pr\":${PR:-0},\"session_id\":\"$SESSION_ID\",\"iteration\":${ITERATION:-0},\"step\":\"06-commit-push\",\"event\":\"git_commit_argv\",\"data\":{\"argv\":\"$COMMIT_ARGV_STR\"}}" >> "$LOG"

# Invoke git with the REAL argv (COMMIT_ARGS), not the logging variant.
git commit "${COMMIT_ARGS[@]}"
```

`argv` in the log is a flat space-joined string of **flag tokens
only** (the message is replaced with the placeholder
`<commit-message>`). This keeps the JSON well-formed regardless of
what the commit message contains. S06.3's grep targets (`--no-verify`,
`--no-gpg-sign`, `-c commit.gpgsign=false`) appear only in argv flag
tokens — never as message content — so the predicate is preserved.

This event fires once per `git commit` invocation in this step. If
this step retries a commit, emit a fresh event per retry.

## Push

```bash
git push origin HEAD
```

Explicit `origin HEAD` is required. Bare `git push` depends on `push.default`
config: with `push.default=matching` (Git 1.x default) it pushes ALL matching
local branches; with `push.default=nothing` it fails silently. `git push origin
HEAD` is safe regardless of configuration and does not require the tracking
upstream to be set (which may not be true when `pr-followup` re-enters without
going through step 04's `git push -u origin <branch>`).

No `--force`. No `--no-verify`.

## Update context

After successful push:
```bash
context.last_push_timestamp = $(git log -1 --format=%ct)  # Unix epoch seconds
context.last_push_sha = $(git rev-parse HEAD)
```

`%ct` gives the committer timestamp as a Unix epoch integer — the same format
step 02 stores for comment timestamps. Filter A in step 03 compares all
timestamps numerically (epoch integers); never store ISO-8601 strings here.
