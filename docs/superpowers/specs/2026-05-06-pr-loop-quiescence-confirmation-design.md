# pr-loop-lib — Quiescence-confirmation design

Date: 2026-05-06
Author: Pratyush Pande
Skills affected: `pr-tooling/pr-autopilot`, `pr-tooling/pr-followup`, `pr-tooling/pr-loop-lib`

## Goal

Cut per-iteration wait time in the shared PR comment loop in half (10 min → 5 min) without losing the protection against late-arriving reviewer-bot comments. The protection is preserved by requiring **two consecutive quiescent iterations** before exiting the comment loop, instead of one.

## Motivation

Today the loop waits 600 s (10 min) between iterations and exits the moment a single iteration is quiescent (no actionable items, or items found but no code changed). The 10-min wait was added during the β smoke-test after Copilot was observed posting a second batch of findings ~12 min after the first; a 0-min wait missed them.

The 10-min wait makes the loop slow to react when bots DO post in the first window — the user pays the full 10 min even if Copilot's first comment lands at minute 1. By halving the wait and requiring confirmation, the loop reacts in 5 min when there's something to react to, while still spanning ~10 min of total wall-clock before declaring quiescence.

| Scenario | Today | Proposed |
|---|---|---|
| Bot posts during first wait window | Caught at 10 min | Caught at 5 min |
| Bot posts 12 min after prior iteration (the original incident) | Caught | Caught (during second leg) |
| PR is genuinely quiet | Exit at 10 min | Exit at 10 min (5 + 5) |

## Non-goals

- No change to iteration cap behavior, runaway-detection, or CI re-entry.
- No new user-facing flags. The behavior is the new default.
- No configurable N for "N consecutive quiescent iterations." Two is the spec; if a future need surfaces a knob, add it then.
- No `--no-confirm` escape hatch. Same reasoning.

## Design

### Behavior

Applies to the shared `pr-loop-lib` and therefore to both `pr-autopilot` and `pr-followup`.

1. **Default per-iteration wait**: 600 s → **300 s (5 min)**.
2. **`--wait N` clamp floor**: 600 s → **300 s**. `--wait N` with `N < 5` is clamped up to 5 with a `wait_clamped` log event (now `effective_minutes: 5`).
3. **Quiescence requires confirmation.** Step 08's two soft-quiescent reasons (`quiescent-zero-actionable`, `quiescent-no-code-change`) no longer route to step 09 directly:
   - First soft-quiescent iteration → increment a counter, emit a `quiescence_pending` log event, route back to step 01 (wait, then re-fetch).
   - Second consecutive soft-quiescent iteration (either reason counts; mixed sequence is fine) → exit to step 09 with a new `loop_exit_reason = quiescent-confirmed`. The `quiescence` log event still fires at exit.
   - Any non-quiescent iteration (actionable items dispatched, code pushed) resets the counter to 0.
   - `iteration-cap` and `runaway-detected` exit immediately as today; the confirmation rule does not apply to them. If the iteration cap is hit on what would have been a confirmation iteration, the exit reason is `iteration-cap`, not `quiescent-confirmed` — never claim a confirmation that did not happen.
4. **`no_wait_first_iteration` semantics are unchanged.** It only ever skips iteration 1's wait. The confirmation iteration always waits — that wait IS the late-comment protection. Without it, "two consecutive quiescent iterations" degenerates into two back-to-back fetches with no time for new comments to land.

### State changes

Two new fields in `context-schema.md`:

| Field | Type | Required | Description |
|---|---|---|---|
| `consecutive_quiescent_iterations` | integer | default `0` | Incremented on each soft-quiescent iteration; reset to 0 on any non-quiescent outcome. Read by step 08 to decide between routing back to step 01 (counter == 1) or onward to step 09 (counter >= 2). |
| `last_quiescence_reason` | enum or null | default `null` | The most recent soft-quiescent reason — one of `quiescent-zero-actionable`, `quiescent-no-code-change`. Carried for the report and for log readability. Cleared (set to `null`) when the counter resets. |

`loop_exit_reason` enum is **rewritten**, not extended:

- Today's allowed values: `quiescent-zero-actionable | quiescent-no-code-change | iteration-cap | runaway-detected`.
- New allowed values: `quiescent-confirmed | iteration-cap | runaway-detected`.

The two old soft-quiescent values are **removed** from `loop_exit_reason` because, under the new design, they never cause a loop exit on their own — they are recorded on `last_quiescence_reason` instead, on the first quiescent iteration, and the loop continues. Only the second consecutive quiescent iteration writes `loop_exit_reason = quiescent-confirmed` and exits.

State files written by older versions of the skill may contain the removed values; that is expected — the schema validation is applied at write time, not on every read.

### Log events

- New event `quiescence_pending`, emitted by step 08 when the first quiescent iteration completes:
  ```json
  {
    "event": "quiescence_pending",
    "data": {
      "iteration": 3,
      "reason": "quiescent-zero-actionable",
      "next_wait_seconds": 300
    }
  }
  ```
- Existing `quiescence` event continues to fire only when the loop actually exits — payload unchanged in shape, but `loop_exit_reason` will now read `quiescent-confirmed` for the soft-quiescent exit path.
- Existing `wait_clamped` event: `effective_minutes` becomes 5; the prose in the event description (in `log-format.md`) updates to reference the new floor.

### Routing summary (step 08)

```
if exit_reason in {iteration-cap, runaway-detected}:
    set loop_exit_reason; set termination_reason; exit to step 11
elif exit_reason in {quiescent-zero-actionable, quiescent-no-code-change}:
    consecutive_quiescent_iterations += 1
    last_quiescence_reason = exit_reason
    if consecutive_quiescent_iterations >= 2:
        loop_exit_reason = quiescent-confirmed
        emit quiescence event
        exit to step 09 (CI gate)
    else:
        emit quiescence_pending event
        route back to step 01 (next iteration)
else:
    # non-quiescent: actionable items dispatched, code pushed
    consecutive_quiescent_iterations = 0
    last_quiescence_reason = null
    route back to step 01 (next iteration)
```

### Files touched

- `skills/pr-tooling/pr-loop-lib/steps/01-wait-cycle.md` — replace 600 s default and floor with 300 s; rewrite the "Minimum wait" section to explain the new two-leg protection (5 + 5 ≈ original 10-min window). The "no assumption-based skip" prose is unchanged. The cache-note paragraph is updated: 300 s is exactly at the prompt-cache TTL boundary, but per-cycle total wall-clock (one wait + step 02-08 work + a second wait when confirmation is needed) is still past the TTL window, so the existing accepted-tradeoff stance is preserved.
- `skills/pr-tooling/pr-loop-lib/steps/08-quiescence-check.md` — add the confirmation-counter rule, the new routing logic, and the `quiescent-confirmed` exit reason. Document explicitly that `iteration-cap` and `runaway-detected` bypass the rule.
- `skills/pr-tooling/pr-loop-lib/references/context-schema.md` — add the two new fields under "Loop runtime state"; extend the `loop_exit_reason` enum with `quiescent-confirmed`; rewrite the `wait_override_minutes` row to reference the 5-minute floor.
- `skills/pr-tooling/pr-loop-lib/references/log-format.md` — add the `quiescence_pending` row to the event taxonomy; update the `wait_clamped` row's `effective_minutes` from `10` to `5` and its prose description.
- `skills/pr-tooling/pr-followup/SKILL.md` — update the `--wait` flag description (floor 5, default 5); update the "default 10" prose; mention that quiescence now requires a confirming iteration so users understand why a quiet first iteration doesn't immediately exit.
- `skills/pr-tooling/pr-autopilot/SKILL.md` — same updates: the `--wait` flag block, the "Hard rules" section's reference to the 10-minute wait, and any other 10-min/600-s callouts. The implementation should grep the file for the strings `10 minute`, `10-minute`, `600`, and re-evaluate each hit.
- `skills/pr-tooling/pr-loop-lib/steps/11-final-report.md` — no template change. The report's "Termination reason" enum is `termination_reason`, not `loop_exit_reason`, so `quiescent-confirmed` does not surface in the printed termination line. Step 09/10 still set `termination_reason` (`ci-green`/`ci-timeout`/`ci-pre-existing-failures`/`ci-reentry-cap`) afterward. If the report should mention the number of confirming iterations, that is a follow-up; not in scope here.
- `skills/pr-tooling/pr-loop-lib/references/invariants.md` — rewrite S08.1 to enumerate the 3-value enum (`quiescent-confirmed`, `iteration-cap`, `runaway-detected`) explicitly instead of the now-stale "4 enum values" wording, and replace S08.3's `{quiescent-*}` wildcard with the literal `quiescent-confirmed` since the wildcard would otherwise match removed enum members. Touched in this PR.

### Edge cases

- **Quiet → noisy → quiet**: Iteration N quiescent (counter=1). Iteration N+1 finds new actionable items, dispatches fixers, pushes code (counter resets to 0). Iteration N+2 quiescent (counter=1). The loop must NOT exit at N+2 — it requires another consecutive quiet iteration. Confirmed by the routing logic above.
- **Iteration cap on the confirmation iteration**: User cap is 5; iteration 4 is quiescent (counter=1); iteration 5 begins, hits the cap before completing. The cap exit fires; `loop_exit_reason = iteration-cap`, NOT `quiescent-confirmed`. The user is told the loop ran out of iterations; they decide whether to re-run.
- **`pr-followup --no-wait` + first iteration quiescent**: Iteration 1 fetches immediately (no wait). It comes back quiescent (counter=1). Step 01 still runs the full 5-min wait before iteration 2. `no_wait_first_iteration` was already false-set after iteration 1 by the existing logic, so this falls out for free.
- **Long custom wait (`--wait 60`)**: Both legs wait 60 min each. ~2 hours total per quiescence confirmation. Documented in step 01 as an explicit consequence of the user override; not changed.
- **Suspicious-only iterations and `ui-deferred`-only iterations**: Today these advance `last_handled_timestamp` and exit via `quiescent-zero-actionable` / `quiescent-no-code-change` respectively. They continue to do so under the new design — they hit one of the two soft-quiescent paths and so count toward the confirmation counter. Spec calls this out explicitly so no one has to re-derive it from step 08's existing prose.

### What does NOT change

- Iteration cap default (10), per-comment-loop-entry semantics, CI re-entry counter (max 3).
- Runaway detection's own internal "2 consecutive cycles" check (a separate concept — same comment ID addressed but reappearing). Independent of the new counter.
- `last_handled_timestamp` cursor advancement for suspicious / `ui-deferred` paths.
- `last_push_timestamp` advancement.
- Lock + state-file protocol.
- CI gate routing semantics post-confirmation (still step 09 → optionally step 10).
- The "no assumption-based skip" prose in step 01 — none of the rationales it forbids become more permissible under the new design.

## Test scenarios

To be expanded in the implementation plan, but the spec asserts the following must be covered:

1. Genuinely quiet PR: two iterations, total ~10 min wait, exits with `quiescent-confirmed`.
2. Late-bot scenario: iteration 1 quiet at minute 5; bot posts at minute 7; iteration 2 picks it up, addresses it, pushes; iteration 3 quiet; iteration 4 quiet; exits with `quiescent-confirmed`. Counter resets correctly between iterations 1 and 2 and again increments cleanly across 3 and 4.
3. Iteration cap on confirmation iteration: cap=5, iterations 1–4 produce work, iteration 5 is the first quiescent → cap fires → exit with `iteration-cap`. (Edge case: counter reaches 1 but never 2.)
4. `pr-followup --no-wait` + immediately quiescent first iteration: iteration 1 fetches immediately and is quiescent; iteration 2 waits the full 5 min, also quiescent; exits with `quiescent-confirmed`.
5. Mixed soft-quiescent reasons: iteration N exits `quiescent-zero-actionable` (counter=1), iteration N+1 exits `quiescent-no-code-change` (counter=2) → exits with `quiescent-confirmed`. Confirms "either reason counts."
6. `--wait 3` (under floor): clamped to 5; `wait_clamped` event fires; loop proceeds normally with two 5-min legs.
7. `runaway-detected` exit: ignores the counter; exits immediately. The runaway predicate (a comment addressed in 2 consecutive cycles that re-appears in `actionable`) implies the prior two cycles were non-quiescent and reset the counter to 0, so at the moment runaway fires `consecutive_quiescent_iterations` is 0 — the test asserts the counter and `last_quiescence_reason` are left untouched on runaway exit (visible in the report) and that `loop_exit_reason = runaway-detected` is recorded regardless of any prior-state values.

## Open questions

None at spec-write time. All structural questions were resolved during brainstorming.

## Out of scope (explicitly deferred)

- Adjusting `quiescence_pending` to surface in the final report. The log event is sufficient for now; if operators ask for a "confirmed after N iterations" line in the report, do it in a follow-up.
- Per-skill overrides (e.g., let `pr-followup` use a 3-min wait while `pr-autopilot` keeps 10 min). The shared library is the only knob.
- Optimizing for the prompt-cache TTL boundary (a 270-s wait would stay cache-warm). The spec keeps the user-facing "5 min" semantics; the existing accepted-tradeoff stance on cache cost is preserved.
