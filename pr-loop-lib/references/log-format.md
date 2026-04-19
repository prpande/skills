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
| `comments_fetched` | `{surface_counts: {inline, issue, review, thread}, total}` — `thread` is the AzDO surface; GitHub runs will have `thread: 0` |
| `triage_result` | `{actionable, suspicious, filtered_self, filtered_known_bot, filtered_pre_push}` |
| `triage_dedup_hit` | `{feedback_id, preflight_match_id, source}` — `source` is `"triage"` when the dedup came from iter-1 Filter B.5 on a real PR comment (feedback_id references `context.actionable[].id`) or `"code-review"` when step 04g internal dispatch deduped a synthetic `/code-review` finding (feedback_id is the synthetic `code-review:finding-N`, registered in `context.internal_review_findings[].fixer_feedback_id`). Consumers look up `feedback_id` in the array indicated by `source`. |
| `cluster_gate_fired` | `{items, clusters_formed}` |
| `subagent_dispatch` | `{role, model, prompt_first_200_chars, feedback_id?, timeout_s}` |
| `subagent_return` | `{role, feedback_id?, verdict, files_changed, reason_first_200_chars, duration_ms}` |
| `verifier_judgement` | `{feedback_id, fixer_verdict_before, fixer_verdict_after, judgement, reason_first_200_chars}` |
| `local_verify` | `{iteration, passed, failed_cmd?, retry_attempted, rolled_back}` |
| `commit_pushed` | `{sha, files, message_first_line}` |
| `reply_posted` | `{feedback_id, thread_id?, surface, resolved}` |
| `quiescence` | `{reason, loop_exit_reason, termination_reason}` |
| `ci_result` | `{check_name, state, link}` |
| `code_review_invoked` | `{host, skill, invoked_at}` when a review skill is mapped and dispatched, OR `{host, skipped: true}` when no skill is mapped for this host (`skill`/`invoked_at` are omitted in the skipped variant) |
| `invariant_fail` | `{step, invariant, observed, expected}` |
| `error` | `{stage, error_type, message}` |
| `git_commit_argv` | `{argv}` — flat space-joined string of `git commit` arguments; emitted by step 06 immediately before the commit runs. Lossy for args that contain spaces; the predicate S06.3 only cares about flag presence (`--no-verify`, `--no-gpg-sign`, `-c commit.gpgsign=false`), so lossiness is acceptable |
| `fixer_reverify` | `{survivor_id, rolled_back_id, overlap_files, new_verdict}` — emitted by step 04's policy ladder after a rollback, for each surviving fixer whose `files_changed` intersect the rolled-back fixer's `files_changed`. `new_verdict` is the re-verified **verifier judgement** — one of `addresses`, `partial`, `not-addresses`, `feedback-wrong`, plus the two bookkeeping values `skipped-empty-diff` (survivor's diff wiped by the rollback; no verifier call made) and `error` (verifier errored out). Matches the verifier judgement enum plus the two bookkeeping extensions — not the fixer-verdict enum. |
| `code_review_rescue_failed` | `{author, body_prefix}` — emitted by Filter B.5 in step 03 when a top-level comment whose author matches the known-bots list fails the tolerant rescue regex; `body_prefix` is the first 200 chars of the body |
| `triage_dedup_miss` | `{candidate_lead, closest_preflight_lead, author}` — emitted by Filter B.5 when a candidate does NOT dedup against any preflight finding but its author matches a preflight-finding author. Both leads are the normalized-and-truncated lead-paragraph strings (not their hashes) so the miss is diagnosable |
| `verifier_nonce_collision` | `{slot, body_sample}` — emitted by the verifier prompt renderer when raw content in one of the untrusted slots contains the nonce literal. `slot` is `feedback` / `reason` / `diff`; `body_sample` is the first 200 chars of the offending input. First collision triggers nonce regeneration; a second collision aborts the verifier call |

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
  # Order matters: rename the compressed backup to its final name BEFORE
  # truncating the live log. If gzip or mv fails, the live log is
  # preserved rather than truncated against a missing backup.
  if gzip -k "$LOG" && mv "$LOG.gz" "$LOG.1.gz"; then
    : > "$LOG"
  else
    echo "log rotation failed; live log preserved" >&2
    rm -f "$LOG.gz"  # clean up any orphaned intermediate
  fi
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
