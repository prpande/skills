# State protocol

Describes how the LLM reads, writes, and locks the per-PR state file.
No runtime library involved — every operation is a shell command or
Read/Write tool call.

## Durability primitives

Three shell-level primitives underpin every state operation in this
protocol. They are specified once here and cited by name in the sections
below.

**Primitive A — Directory-as-lock (atomic create-or-fail).** Lock
acquisition uses `mkdir` on a lock *directory*, not a file. `mkdir` is
an atomic create-or-fail primitive on Linux, macOS, and Windows git-bash
— no external tools required. The lock directory's existence IS the
lock; session_id and lease timestamp live as files inside. The lock
path literal stays `.pr-autopilot/pr-<PR>.lock` (and
`.pr-autopilot/branch-<slug>.lock` before the PR number is assigned);
only the entry type changes from file to directory.

**Primitive B — Reversible slug encoding (percent-escape `%` and
`/`).** Branch slugs for pre-PR-number state/lock/log filenames use
percent-encoding of `%` (first) then `/`:

```bash
slug=$(printf '%s' "$branch" | sed -e 's/%/%25/g' -e 's|/|%2F|g')
```

This is reversible and collision-free: `feature/a-b` → `feature%2Fa-b`,
`feature-a/b` → `feature-a%2Fb`, where the old `/`→`-` scheme produced
the same string `feature-a-b` for both and corrupted state. The order
matters: `%` must be escaped before `/` or a subsequent pass on `/` →
`%2F` would re-encode the freshly-produced `%25`.

**Primitive C — Atomic state writes (tmp + mv).** State files are
written via a temp-then-rename dance in Bash, not via the Write tool:

```bash
printf '%s' "$payload" > "$state.tmp.$$" && mv "$state.tmp.$$" "$state"
```

On POSIX filesystems (ext4, APFS) `rename(2)` is atomic when source and
destination share a filesystem; placing the temp file next to the target
guarantees that. On native Windows / NTFS, `mv` over an existing
destination is not strictly atomic (the OS performs delete-then-rename)
— document this as a known limitation. A missing state file on the next
step entry is recoverable via the log-replay rule ("Reading state"
below).

Do NOT use the Write tool directly on the state file — it does not
guarantee atomic replacement across platforms.

**Migration from α.** Any pre-β artifacts left in `.pr-autopilot/` — flat
`.lock` files (β makes them directories) or state filenames using the
old `/`→`-` slug — may be safely deleted before β acquires. β ships
before any production α run, so no in-flight migration logic is
shipped. If a flat `.lock` file blocks a fresh β acquire, delete it.

**Filesystem assumption.** Primitives A and C assume the repo lives on
a local filesystem that honors POSIX rename/mkdir semantics. Network
filesystems (NFS, SMB) may not, and can subtly break both atomic
`mkdir` and atomic `rename`. Scope-note: running pr-autopilot from a
working tree on a network mount is out of scope; document to operators
that a local working tree is required.

## Paths

Given `context.repo_root` (from `git rev-parse --show-toplevel`) and
`context.pr_number` (integer):

- Directory: `<repo_root>/.pr-autopilot/`
- State file: `<repo_root>/.pr-autopilot/pr-<PR>.json`
- Lock file: `<repo_root>/.pr-autopilot/pr-<PR>.lock`
- Log file: `<repo_root>/.pr-autopilot/pr-<PR>.log`

If `pr_number` is not yet known (pre step 04), use a temporary path
keyed by the current branch:
- State file: `<repo_root>/.pr-autopilot/branch-<branch-slug>.json`
  where `branch-slug` is computed by reversible percent-encoding
  (Primitive B in the "Durability primitives" section above).
- After step 04 assigns `pr_number`, rename the files to the `pr-<PR>.*`
  naming and update the lock file contents.

## First-run setup

When a step first needs to write state:
1. Ensure the directory exists:
   ```bash
   mkdir -p "<repo_root>/.pr-autopilot"
   ```
2. Check if `.pr-autopilot/` is already in `.gitignore`. If not, append
   it:
   ```bash
   if ! grep -qxF '.pr-autopilot/' "<repo_root>/.gitignore" 2>/dev/null; then
     printf '\n# pr-autopilot ephemeral state (not versioned)\n.pr-autopilot/\n' >> "<repo_root>/.gitignore"
   fi
   ```
3. Generate `session_id` if not already in context:
   ```bash
   SESSION_ID=$(python -c "import uuid; print(uuid.uuid4())" 2>/dev/null \
                || uuidgen 2>/dev/null \
                || cat /proc/sys/kernel/random/uuid 2>/dev/null \
                || echo "$(date +%s)-$$")
   ```
   Pick the first succeeding command. Fall back to timestamp-plus-PID if
   none available.

## Lock directory structure

The lock path (`pr-<PR>.lock` or `branch-<slug>.lock`) is a **directory**
(Primitive A). Inside it:

```
<lock_dir>/
  session     # one line: the holding session_id (UUID string)
  lease       # one line: the most recent lease refresh as Unix epoch seconds
```

Both files are plain text. Epoch seconds (not ISO-8601) are used for
`lease` because numeric subtraction for stale-age computation requires
no parsing.

## Acquiring the lock

Lock acquisition is a single atomic `mkdir` (Primitive A). Read-then-
write is never used: it would have a TOCTOU race between the read and
the write.

```
1. lock_dir = "<repo_root>/.pr-autopilot/pr-<PR>.lock"  (or
   "<repo_root>/.pr-autopilot/branch-<slug>.lock" pre-PR-assignment)

2. Attempt atomic create:
     if mkdir "$lock_dir" 2>/dev/null; then
       printf '%s\n' "$SESSION_ID"      > "$lock_dir/session"
       printf '%s\n' "$(date +%s)"      > "$lock_dir/lease"
       # acquired
     else
       # directory already exists; fall through to step 3
     fi

3. If acquire succeeded: log `lock_acquired` with session_id. Proceed.

4. If acquire failed (directory exists):
   - Read "$lock_dir/session" → held_session_id
   - Read "$lock_dir/lease"   → held_lease_epoch
   - If held_session_id == context.session_id:
     - This is our own resumed session. Refresh lease (see "Refreshing
       the lock"). Optionally log `lock_lease_refreshed` on first
       refresh per step to reduce noise. Proceed.
   - Else compute age_minutes = (current_epoch - held_lease_epoch) / 60.
     - If age_minutes > 30:
       - Treat as stale. Reclaim by overwriting both files in place:
           printf '%s\n' "$SESSION_ID"  > "$lock_dir/session"
           printf '%s\n' "$(date +%s)"  > "$lock_dir/lease"
       - Log `lock_stale_reclaimed` event with old session_id and age.
       - **Also update `state.session_id` in the state file to the
         new `context.session_id`** and log a `state_write` event
         with `changed_keys: ["session_id"]`. Without this, global
         invariant G1 (state.session_id == lock.session_id) fires on
         the next write.
       - Proceed.
     - Else (fresh lock, different session):
       - Halt with message:
         ```
         HALT: another pr-autopilot session is active on this PR.
         lock directory: <lock_dir>
         holding session_id: <other_session_id>
         lease age: <minutes> min
         Either wait for it to complete, or `rm -rf <lock_dir>` if you
         know the holder is dead.
         ```
```

## Refreshing the lock

Every state write refreshes the lease. At the start of any step-end
state update:

```
1. Verify the lock directory exists AND its "session" file matches
   context.session_id. If not, halt with "lock was reclaimed by
   another session". (Should not happen if the acquire logic is
   followed, but guards against races.)
2. Overwrite "$lock_dir/lease" with the current Unix epoch seconds
   (same session_id, new lease):
     printf '%s\n' "$(date +%s)" > "$lock_dir/lease"
```

The `session` file is never overwritten during refresh — only during
reclaim. This preserves an audit trail of who originally acquired.

## Releasing the lock

Step 11 (final report) releases the lock as its last action:

```bash
rm -rf "<repo_root>/.pr-autopilot/pr-<PR>.lock"
```

Log `lock_released` event.

If step 11 is never reached (crash, user abort), the lock goes stale
and the next invocation reclaims it after 30 min per the acquire logic.

## Reading state

```
1. Read <repo_root>/.pr-autopilot/pr-<PR>.json via Read tool.
2. Parse as JSON.
3. Validate every top-level key matches context-schema.md:
   - Known key: OK.
   - Unknown key: log `invariant_fail`, halt.
4. Load into context.
```

On first entry (no state file yet), write a minimal initial state:
```json
{
  "session_id": "<uuid>",
  "host_platform": "<detected>",
  "platform": "<detected>",
  "repo_root": "<path>",
  ...etc. all required fields from step 01 detection
}
```

**State-file loss (NTFS).** If a crash strikes between `mv`'s delete
and rename on NTFS, the state file may be missing on next step entry.
Log replay is NOT a recovery path: `state_write` events record
`changed_keys` only (no values — see `log-format.md`), so the log is a
change-audit, not a state snapshot. A missing state file is treated as
an unrecoverable crash: the skill halts on next step entry with a
clear diagnostic instructing the user to delete `.pr-autopilot/`
artifacts and re-invoke. The operator re-runs; the skill starts fresh.
This is an accepted limitation of the zero-dependency constraint and
is vanishingly rare outside mid-OS-crash scenarios.

## Writing state

State writes use the atomic tmp+mv primitive (Primitive C). The Write
tool is NOT used for state files — it does not guarantee atomic
replacement across platforms.

Protocol:
```
1. Refresh the lock (per "Refreshing the lock" above).
2. Compute the updated state dict (take current context dict, apply
   changes).
3. Validate the full dict against context-schema.md. Any violation =
   halt with `invariant_fail`.
4. Serialize to JSON (2-space indent, UTF-8, LF newlines) into a
   shell variable, e.g. `$payload`.
5. Atomic write via Bash:
     printf '%s' "$payload" > "$state.tmp.$$" && mv "$state.tmp.$$" "$state"
   On POSIX this is atomic. On NTFS it is the best portable
   approximation (delete-then-rename). See Primitive C caveat.
6. Log `state_write` event listing changed keys.
```

## Temporary pre-PR-number state

Before step 04 assigns `pr_number`:
- State file is at `<repo_root>/.pr-autopilot/branch-<branch-slug>.json`
- Lock directory is at `<repo_root>/.pr-autopilot/branch-<branch-slug>.lock` (see "Lock directory structure")
- Log file is at `<repo_root>/.pr-autopilot/branch-<branch-slug>.log`
- Review-summary file (β) is at `<repo_root>/.pr-autopilot/branch-<branch-slug>-review-summary.md` (see `pr-autopilot/steps/02-preflight-review.md` "Review-summary artifact")

After step 04's `gh pr create` succeeds and the PR number is assigned:

```bash
cd "<repo_root>/.pr-autopilot"

# Pre-flight: fail fast if any destination already exists (residual
# from a prior crashed session on the same PR number). Doing a partial
# rename mid-batch would leave state/log/lock in inconsistent states.
for dest in "pr-<PR>.json" "pr-<PR>.lock" "pr-<PR>.log" "pr-<PR>-review-summary.md"; do
  if [ -e "$dest" ]; then
    echo "HALT state_rename: destination '$dest' already exists."
    echo "Residual from a previous crashed session? Investigate and"
    echo "delete manually before re-invoking."
    exit 1
  fi
done

mv "branch-<slug>.json"               "pr-<PR>.json"
mv "branch-<slug>.lock"               "pr-<PR>.lock"          # directory mv; git-bash handles atomically when target is absent
mv "branch-<slug>.log"                "pr-<PR>.log"
if [ -f "branch-<slug>-review-summary.md" ]; then
  mv "branch-<slug>-review-summary.md" "pr-<PR>-review-summary.md"
fi

# Update the $LOG environment variable in-memory for subsequent log
# writes (including the state_rename event itself). Failing to do this
# will append the state_rename record to the now-nonexistent old path.
LOG="<repo_root>/.pr-autopilot/pr-<PR>.log"
```

Update `pr_number` and `internal_review_summary_path` fields inside
the state file after the rename. Log a `state_rename` event to the
newly-pointed `$LOG` listing every renamed artifact (old → new pairs).

## Host-platform detection (called from step 01)

Run these commands in order; first hit determines `host_platform`:

```bash
# Claude Code: $CLAUDE_CODE or the `claude` binary in PATH
if [ -n "$CLAUDE_CODE" ] || command -v claude >/dev/null 2>&1; then
  HOST="claude-code"
# Codex: $CODEX or `codex` binary
elif [ -n "$CODEX" ] || command -v codex >/dev/null 2>&1; then
  HOST="codex"
# Gemini CLI: `gemini` binary
elif command -v gemini >/dev/null 2>&1; then
  HOST="gemini"
else
  HOST="other"
fi
```

The first environment variable check is the preferred signal (host
platforms set these). The binary-in-PATH check is a fallback for
sessions that don't propagate env vars.

## Self-login detection (called from step 01)

```bash
# GitHub
if [ "$platform" = "github" ]; then
  SELF_LOGIN=$(gh api user --jq .login 2>/dev/null)
# AzDO
elif [ "$platform" = "azdo" ]; then
  SELF_LOGIN=$(az account show --query user.name -o tsv 2>/dev/null)
fi
```

If the command fails (auth missing), halt with a clear diagnostic
pointing the user to `gh auth login` / `az login`.
