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
- `ts` is UTC ISO-8601. Accept either **second precision**
  (`2026-04-18T07:44:32Z`) or **millisecond precision**
  (`2026-04-18T07:44:32.123Z`). Step 06's `git_commit_argv` emitter
  uses second precision for macOS portability (`date -u +%3N` is
  GNU-specific); other emit sites may use either. Parsers should
  accept both forms. Matches `context-schema.md` validation rule #5.
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
| `state_rename` | `{renames: [{from, to}, ...]}` — emitted once per state-rename batch (step 04 PR-create assigns the PR number and renames `branch-<slug>.{json,lock,log,review-summary.md}` → `pr-<PR>.*` in a single atomic-ish batch). The `renames` array lists every successfully-renamed artifact as a `{from, to}` pair. Prior revisions declared a single `{from, to}` shape; the batch shape is a superset (a single rename is an array of one) and readers should accept either for backwards compatibility. |
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
| `code_review_rescue_failed` | `{author, body_prefix}` — emitted by Filter B.5 Stage 1 in step 03 when a top-level self-authored comment (Stage 1 is already gated on `author == context.self_login`) fails the tolerant rescue regex BUT contains at least one `github.com/.../blob/<sha>/path#L<n>` finding-anchor URL — the positive heuristic that the body was likely drifted `/code-review` output rather than an ordinary self-reply. `body_prefix` is the first 200 chars of the body. (The α-era "author matches known-bots list" wording was unreachable inside Stage 1's self_login gate — a skill's self_login is by construction not a known-bot login.) |
| `triage_dedup_miss` | `{candidate_lead, closest_preflight_lead, author}` — emitted by Filter B.5 when a candidate does NOT dedup against any preflight finding AND the candidate's author is in the known-bots list AND `context.preflight_passes.merged` is non-empty. (Preflight findings have no `author` field — they come from our own Sonnet subagent — so the α-era "same author" condition was unfireable; the actual discriminator is "candidate is automated AND preflight had findings worth comparing against".) Both leads are the normalized-and-truncated lead-paragraph strings (not their hashes) so the miss is diagnosable |
| `verifier_nonce_collision` | `{slot, body_sample}` — emitted by the verifier prompt renderer when raw content in one of the untrusted slots contains the nonce literal. `slot` is `feedback` / `reason` / `diff`; `body_sample` is the first 200 chars of the offending input. First collision triggers nonce regeneration; a second collision aborts the verifier call |
| `fixer_nonce_collision` | `{}` — emitted by the fixer dispatch when the comment body contains the fixer nonce literal. Distinct from `verifier_nonce_collision` (which covers the verifier's three slots). First collision triggers nonce regeneration; a second collision escalates the dispatch unit to `needs-human` |
| `wait_clamped` | `{requested_minutes, effective_minutes, reason}` — emitted by `pr-loop-lib/steps/01-wait-cycle.md` when `context.wait_override_minutes` is less than the 10-minute floor and gets clamped up. `requested_minutes` is the raw user input, `effective_minutes` is always 10. `reason` is a short string explaining the floor (e.g., `"reviewer-bot response window"`). Informational only — the loop continues with the clamped value |
| `ui_deferred_touched_files` | `{feedback_id, files_changed}` — emitted by step 04's validation when a fixer return with `verdict == "ui-deferred"` arrived with a non-empty `files_changed`. The orchestrator rolls back and demotes the return to `needs-human`; this event is the audit trail for S04.8. |
| `ui_deferred_decision` | `{feedback_id, decision}` — emitted by step 11's UI-deferred approval phase, one per item, `decision ∈ {apply, reject, skip}`. `apply` triggers a re-dispatch through step 04 with `UI_DEFERRAL_OVERRIDE=true`. |
| `ui_deferred_prompt_skipped` | `{reason, count}` — emitted by step 11 when the approval prompt could not run (e.g., non-interactive host). `count` is `len(context.ui_deferred_items)` at the time the prompt would have fired. |

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
  # Atomic rotation: mv the live log first (POSIX rename is atomic —
  # after mv, any new printf appends open a fresh inode at $LOG, so no
  # records are lost). Then compress the moved copy. If gzip fails,
  # the records are still in $LOG.prev.$$ — warn and leave it for the
  # operator rather than silently discarding them.
  mv "$LOG" "$LOG.prev.$$"
  if gzip -c "$LOG.prev.$$" > "$LOG.1.gz.tmp.$$" \
       && mv "$LOG.1.gz.tmp.$$" "$LOG.1.gz"; then
    rm -f "$LOG.prev.$$"
  else
    echo "log rotation compression failed; prior log preserved as ${LOG}.prev.$$" >&2
    rm -f "$LOG.1.gz.tmp.$$"
    # Do NOT restore $LOG.prev.$$ to $LOG — a new $LOG may already
    # have started accumulating records. Operator must merge manually.
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
