# Loop step 08 — Quiescence check

Decide whether to start another iteration or exit to the CI gate.

## Exit conditions (any one triggers exit)

1. **Zero actionable items** in this iteration's step 03 output
   (`context.actionable == []`). Suspicious items do not block exit —
   they get refusal replies posted by step 07 once per cycle and nothing
   else the loop can do advances them. If we kept looping on suspicious-only
   iterations without a push, `last_push_timestamp` would not advance and
   the same suspicious items would re-enter the queue forever. Instead,
   after step 07 posts the refusal replies, advance a secondary cursor
   `context.last_handled_timestamp = now` so filter A's "new-since" gate
   applies to suspicious items too, and treat this iteration as quiescent.
2. **No code changed** this iteration: all verdicts are in
   `{replied, not-addressing, needs-human, ui-deferred}`. Re-entering
   the loop cannot progress — another fetch will see the same state.
   When this path exits AND the iteration's `context.agent_returns`
   contains at least one entry with `verdict == "ui-deferred"`,
   advance `context.last_handled_timestamp = now` (same mechanism as
   the suspicious-only exit above). Filter A's pre-filter drops the
   self-login reply step 07 posted, so the gate that actually
   suppresses the original reviewer comment on the next fetch is the
   "new-since" timestamp check, not the presence of a self-login
   reply. Without this cursor advance, a subsequent `pr-followup`
   run would re-triage the same reviewer comment, the fixer would
   return `ui-deferred` again, and the user would be prompted twice
   for the same item. `needs-human` iterations do not get the same
   advance — they deliberately re-surface on the next run so the
   user sees the still-open question in `pr-followup`'s report.
3. **Iteration cap reached**:
   - `context.user_iteration_cap` if set → cap at that value.
   - Else 10 (default).
4. **Runaway detected**: the same comment ID has been addressed (verdict
   `fixed` or `fixed-differently`) in 2 consecutive cycles but keeps
   re-appearing in `context.actionable`. Likely a bot bug; surface and exit.

## Cap scope

The iteration cap is **per comment-loop entry**. When step 10 (CI failure
classify) triggers a re-entry, the iteration counter resets to 1. The CI
re-entry counter (max 3, tracked separately in `context.ci_reentry_count`)
is the outer runaway bound.

## Recording the exit reason

Set BOTH fields so the final report has a single authoritative source:

- `context.loop_exit_reason` — the fine-grained loop-level reason (one of
  `quiescent-zero-actionable`, `quiescent-no-code-change`, `iteration-cap`,
  `runaway-detected`).
- `context.termination_reason` — the top-level termination label used by
  step 11. When step 08 exits directly (cap / runaway), set this too so
  the report is never missing the field:
  - `loop_exit_reason == quiescent-*` → leave `termination_reason`
    unset; step 09 will populate it (`ci-green` / `ci-timeout`) or step 10
    will (`ci-pre-existing-failures` / `ci-reentry-cap`).
  - `loop_exit_reason == iteration-cap` → set
    `termination_reason = "iteration-cap"`.
  - `loop_exit_reason == runaway-detected` → set
    `termination_reason = "runaway-detected"`.

## Routing

- If exit reason is `quiescent-zero-actionable` OR `quiescent-no-code-change`
  → proceed to step 09 (CI gate).
- If exit reason is `iteration-cap` OR `runaway-detected` → skip step 09
  and proceed directly to step 11 (final report). The user decides next
  steps; do not gate on CI because the user may intend to abandon the
  branch or investigate manually.
