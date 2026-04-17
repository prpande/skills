# Loop step 08 — Quiescence check

Decide whether to start another iteration or exit to the CI gate.

## Exit conditions (any one triggers exit)

1. **Zero actionable items** in this iteration's step 03 output
   (`context.actionable == [] AND context.suspicious_items == []`).
2. **No code changed** this iteration: all verdicts are in
   `{replied, not-addressing, needs-human}`. Re-entering the loop cannot
   progress — another fetch will see the same state.
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

Set `context.loop_exit_reason` to one of:
- `quiescent-zero-actionable`
- `quiescent-no-code-change`
- `iteration-cap`
- `runaway-detected`

Step 11 uses this in the final report.

## Routing

- If exit reason is `quiescent-zero-actionable` OR `quiescent-no-code-change`
  → proceed to step 09 (CI gate).
- If exit reason is `iteration-cap` OR `runaway-detected` → skip step 09
  and proceed directly to step 11 (final report). The user decides next
  steps; do not gate on CI because the user may intend to abandon the
  branch or investigate manually.
