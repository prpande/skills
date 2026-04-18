# Log format

JSON-lines, one event per line. Appended via shell `printf '%s\n' ... >>`
— no library required.

## File location

`<repo_root>/.pr-autopilot/pr-<PR>.log` (or `branch-<slug>.log` before
`pr_number` is assigned; renamed by the state-protocol at PR-create time).

## Record shape

Every record has these top-level keys:

```json
{
  "ts": "2026-04-18T07:44:32.123Z",
  "pr": 1,
  "session_id": "uuid-string",
  "iteration": 0,
  "step": "01-detect-context",
  "event": "skill_start",
  "data": { /* event-specific payload */ }
}
```

Rules:
- `ts` is UTC ISO-8601 with millisecond precision.
- `pr` is the PR number (integer). Use `0` before step 04 assigns it.
- `iteration` is `0` for steps outside the comment loop (preflight,
  step 04, final report). Iterations increment starting at 1 inside
  the loop.
- `step` names the step file (e.g., `03-triage`, not the full path).
- `event` is the discriminator — one of the values in the table below.
- `data` contents depend on `event`.

## Event taxonomy

| `event` | `data` payload |
|---|---|
| `skill_start` | `{args, cap, wait_override, host}` |
| `skill_end` | `{termination_reason, iterations, commits, fixes_applied}` |
| `step_start` | `{step_name}` |
| `step_end` | `{step_name, duration_ms?}` |
| `state_write` | `{changed_keys: [...]}` |
| `state_rename` | `{from, to}` |
| `lock_acquired` | `{session_id}` |
| `lock_released` | `{session_id}` |
| `lock_stale_reclaimed` | `{old_session_id, age_minutes}` |
| `lock_lease_refreshed` | `{session_id}` |
| `comments_fetched` | `{surface_counts: {inline, issue, review}, total}` |
| `triage_result` | `{actionable, suspicious, filtered_self, filtered_known_bot, filtered_pre_push}` |
| `triage_dedup_hit` | `{feedback_id, preflight_match_id}` |
| `cluster_gate_fired` | `{items, clusters_formed}` |
| `subagent_dispatch` | `{role, model, prompt_first_200_chars, feedback_id?, timeout_s}` |
| `subagent_return` | `{role, feedback_id?, verdict, files_changed, reason_first_200_chars, duration_ms}` |
| `verifier_judgement` | `{feedback_id, fixer_verdict_before, fixer_verdict_after, judgement, reason_first_200_chars}` |
| `local_verify` | `{iteration, passed, failed_cmd?, retry_attempted, rolled_back}` |
| `commit_pushed` | `{sha, files, message_first_line}` |
| `reply_posted` | `{feedback_id, thread_id?, surface, resolved}` |
| `quiescence` | `{reason, loop_exit_reason, termination_reason}` |
| `ci_result` | `{check_name, state, link}` |
| `code_review_invoked` | `{host, skill, invoked_at}` |
| `invariant_fail` | `{step, invariant, observed, expected}` |
| `error` | `{stage, error_type, message}` |

## Truncation

- `prompt_first_200_chars` and `reason_first_200_chars` fields are the
  first 200 characters of the text, plus `...` if truncated. The full
  text is NOT stored — debugging full prompts requires re-running with
  verbose mode (a future enhancement, not in scope here).

## Appending an event

```bash
printf '%s\n' '{
  "ts": "2026-04-18T07:44:32.123Z",
  "pr": 1,
  "session_id": "...",
  "iteration": 0,
  "step": "02-preflight-review",
  "event": "subagent_dispatch",
  "data": {
    "role": "adversarial-reviewer",
    "model": "sonnet",
    "prompt_first_200_chars": "You are a senior engineer conducting a skeptical...",
    "timeout_s": 180
  }
}' >> "<repo_root>/.pr-autopilot/pr-<PR>.log"
```

In practice, the LLM writes the JSON as one line (no embedded newlines
in `data`) to keep the file strictly JSON-lines.

## Rotation

The log grows across the skill run. Rotation is triggered when the
file exceeds 10 MB (check via `wc -c < "<path>"`):

```bash
LOG="<repo_root>/.pr-autopilot/pr-<PR>.log"
if [ -f "$LOG" ] && [ "$(wc -c < "$LOG")" -gt 10485760 ]; then
  gzip -k "$LOG"
  mv "$LOG.gz" "$LOG.1.gz"
  : > "$LOG"
fi
```

Keep one compressed backup (`.log.1.gz`); older backups are removed.

## Retrieving events

Users who want to inspect the log can use:

```bash
# Tail live:
tail -f "<repo_root>/.pr-autopilot/pr-<PR>.log"

# Events of a specific type:
grep '"event": "subagent_return"' "<repo_root>/.pr-autopilot/pr-<PR>.log"

# Events for a specific feedback:
grep '"feedback_id": "3104534371"' "<repo_root>/.pr-autopilot/pr-<PR>.log"
```

No parser script is provided. `jq` works if the user has it installed:
```bash
jq -c 'select(.event == "verifier_judgement")' "<repo_root>/.pr-autopilot/pr-<PR>.log"
```
