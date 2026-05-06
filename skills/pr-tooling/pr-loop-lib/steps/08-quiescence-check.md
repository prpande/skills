# Loop step 08 — Quiescence check

Decide whether to start another iteration or exit to the CI gate.

## Quiescence confirmation rule

Soft-quiescent iterations (`quiescent-zero-actionable` and
`quiescent-no-code-change`, items 1 and 2 in the Exit conditions list
below) DO NOT exit the loop on their own. They increment a counter,
emit a `quiescence_pending` log event, and route back to step 01 for
another iteration. Only when **two consecutive** soft-quiescent
iterations have occurred does the loop exit to step 09 with
`loop_exit_reason = quiescent-confirmed`.

The counter lives in `context.consecutive_quiescent_iterations`
(default 0). Per `references/context-schema.md`:
- Soft-quiescent iteration: `consecutive_quiescent_iterations += 1`,
  `last_quiescence_reason = <the soft-quiescent reason>`. Either of the
  two soft-quiescent reasons counts toward the same counter — a mixed
  sequence (`quiescent-zero-actionable` then `quiescent-no-code-change`,
  or vice versa) is two consecutive quiescent iterations.
- Non-quiescent iteration (actionable items dispatched, code pushed):
  `consecutive_quiescent_iterations = 0`,
  `last_quiescence_reason = null`.
- `iteration-cap` and `runaway-detected` (items 3 and 4) **bypass the
  rule entirely** and exit immediately. If the iteration cap is hit on
  what would have been a confirmation iteration, the exit reason is
  `iteration-cap`, NOT `quiescent-confirmed` — never claim a
  confirmation that did not happen. The counter and
  `last_quiescence_reason` are left as they are (visible in the state
  file for the report).

The confirmation iteration always waits — `pr-followup`'s
`no_wait_first_iteration` is reset to `false` after iteration 1 by step
01, so this falls out of the existing flow without a special case.

## Exit conditions (any one triggers exit, subject to the confirmation rule above)

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

The confirmation counter is also scoped per comment-loop entry. CI
re-entry from step 10 MUST reset
`context.consecutive_quiescent_iterations = 0` and
`context.last_quiescence_reason = null` alongside the iteration counter.
Without this, a counter value carried over from the previous loop entry
(e.g., 1 from a soft-quiescent iteration that preceded the
`quiescent-confirmed` exit) would let a single quiescent iteration in
the new entry trip a premature `quiescent-confirmed` exit. Step 10's
re-entry preamble is the canonical reset site.

## Recording the exit reason

`context.loop_exit_reason` is one of `quiescent-confirmed`,
`iteration-cap`, or `runaway-detected` (per the schema rewrite in
2026-05-06). It is set ONLY on actual loop exit:

- First soft-quiescent iteration (counter goes 0 → 1): do NOT set
  `loop_exit_reason`; do set `last_quiescence_reason` to the
  soft-quiescent reason; emit `quiescence_pending`; route back to
  step 01.
- Second consecutive soft-quiescent iteration (counter goes 1 → 2):
  set `loop_exit_reason = "quiescent-confirmed"`; emit the existing
  `quiescence` event; route to step 09. Leave `termination_reason`
  unset — step 09 will populate it (`ci-green` / `ci-timeout`) or
  step 10 will (`ci-pre-existing-failures` / `ci-reentry-cap`).
- `iteration-cap`: set `loop_exit_reason = "iteration-cap"` and
  `termination_reason = "iteration-cap"`.
- `runaway-detected`: set `loop_exit_reason = "runaway-detected"` and
  `termination_reason = "runaway-detected"`.

The `quiescence` log event (per `references/log-format.md`) fires on
**every** loop exit, including `iteration-cap` and `runaway-detected` —
see the routing pseudocode below for the exact emit shape. The first
soft-quiescent iteration emits the separate `quiescence_pending` event
instead and does NOT emit `quiescence`, because no exit occurs.

`context.last_quiescence_reason` is the most recent soft-quiescent
reason; carried for the report. It is set on each soft-quiescent
iteration and cleared (set to `null`) on each non-quiescent iteration.
On a `quiescent-confirmed` exit, it reflects the second iteration's
reason.

## Routing

Pseudocode (operator may follow the conditional ladder directly):

```
exit_reason = <one of: quiescent-zero-actionable | quiescent-no-code-change | iteration-cap | runaway-detected | none>

if exit_reason in {iteration-cap, runaway-detected}:
    set context.loop_exit_reason = exit_reason
    set context.termination_reason = exit_reason
    emit quiescence event {reason: exit_reason, loop_exit_reason: exit_reason, termination_reason: exit_reason}
    proceed to step 11 (final report)

elif exit_reason in {quiescent-zero-actionable, quiescent-no-code-change}:
    context.consecutive_quiescent_iterations += 1
    context.last_quiescence_reason = exit_reason
    if context.consecutive_quiescent_iterations >= 2:
        context.loop_exit_reason = "quiescent-confirmed"
        emit quiescence event {reason: exit_reason, loop_exit_reason: "quiescent-confirmed", termination_reason: null}
        proceed to step 09 (CI gate)
    else:
        emit quiescence_pending event {iteration: context.iteration, reason: exit_reason, next_wait_seconds: <300 or context.wait_override_minutes*60>}
        route back to step 01 (next iteration)

else:
    # non-quiescent iteration: items dispatched and pushed; loop continues normally
    context.consecutive_quiescent_iterations = 0
    context.last_quiescence_reason = null
    route back to step 01 (next iteration)
```

`iteration-cap` and `runaway-detected` skip step 09 and go directly to
step 11 — the user decides next steps; do not gate on CI because the
user may intend to abandon the branch or investigate manually.
`quiescent-confirmed` proceeds through the CI gate as before.
