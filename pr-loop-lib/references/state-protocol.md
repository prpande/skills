# State protocol

Describes how the LLM reads, writes, and locks the per-PR state file.
No runtime library involved — every operation is a shell command or
Read/Write tool call.

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
  where `branch-slug` replaces `/` with `-`.
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

## Lock file format

Plain JSON, two required fields:

```json
{
  "session_id": "uuid-string",
  "acquired_at": "2026-04-18T07:44:32Z"
}
```

## Acquiring the lock

```
1. Read the lock file (via Read tool) if it exists.
2. If it does NOT exist:
   - Write a new lock file with context.session_id and current UTC
     ISO-8601 timestamp. Use the Write tool (atomic).
   - Log `lock_acquired` event.
   - Proceed.
3. If it exists:
   - Parse JSON.
   - If lock.session_id == context.session_id:
     - Refresh lease: overwrite with a new acquired_at timestamp.
     - Log `lock_lease_refreshed` event. (Optional — only log on first
       refresh per step to reduce noise.)
     - Proceed.
   - Compute age: current UTC minus lock.acquired_at (in minutes).
   - If age > 30 min:
     - Treat as stale. Overwrite with new session's lock.
     - Log `lock_stale_reclaimed` event with old session_id + age.
     - **Also update `state.session_id` in the state file to the new
       `context.session_id`** and log a `state_write` event with
       `changed_keys: ["session_id"]`. Without this, global invariant
       G1 (state.session_id == lock.session_id) fires on the next
       write.
     - Proceed.
   - Otherwise (fresh lock, different session):
     - Halt with message:
       ```
       HALT: another pr-autopilot session is active on this PR.
       lock file: <path>
       holding session_id: <other_session_id>
       acquired_at: <timestamp>  (age: <minutes> min)
       Either wait for it to complete, or delete the lock file if you
       know the holder is dead.
       ```
```

## Refreshing the lock

Every state write refreshes the lease. At the start of any step-end
state update:
```
1. Read the lock file.
2. Verify session_id matches context.session_id. If not, halt with
   "lock was reclaimed by another session". (Should not happen if the
   acquire logic is followed, but guards against races.)
3. Overwrite the lock file with the SAME session_id and a NEW
   acquired_at timestamp (current UTC).
```

## Releasing the lock

Step 11 (final report) releases the lock as its last action:
```bash
rm -f "<repo_root>/.pr-autopilot/pr-<PR>.lock"
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

## Writing state

State writes are atomic because the Write tool replaces the file
atomically (it writes to a temp and renames). No partial state after
a crash.

Protocol:
```
1. Refresh the lock (per "Refreshing the lock" above).
2. Compute the updated state dict (take current context dict, apply
   changes).
3. Validate the full dict against context-schema.md. Any violation =
   halt with `invariant_fail`.
4. Serialize to JSON (2-space indent, UTF-8, LF newlines).
5. Write to the state file via the Write tool.
6. Log `state_write` event listing changed keys.
```

## Temporary pre-PR-number state

Before step 04 assigns `pr_number`:
- State file is at `<repo_root>/.pr-autopilot/branch-<branch-slug>.json`
- Lock file is at `<repo_root>/.pr-autopilot/branch-<branch-slug>.lock`
- Log file is at `<repo_root>/.pr-autopilot/branch-<branch-slug>.log`

After step 04's `gh pr create` succeeds and the PR number is assigned:
```bash
cd "<repo_root>/.pr-autopilot"
mv "branch-<slug>.json" "pr-<PR>.json"
mv "branch-<slug>.lock" "pr-<PR>.lock"
mv "branch-<slug>.log"  "pr-<PR>.log"
```

Update `pr_number` field inside the state file after the rename.
Log a `state_rename` event.

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
