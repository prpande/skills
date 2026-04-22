# Loop step 01 — Wait cycle

Delays the next comment fetch to give reviewer bots time to post. Uses
`ScheduleWakeup` with a default delay of 600 seconds (10 minutes).

## Minimum wait (floor)

**Hard rule: `delay_seconds` must be >= 600.** Reviewer bots (Copilot,
SonarCloud, mergewatch, `/code-review` after-action rounds) routinely
post follow-up findings 2–10 minutes after an initial review. A shorter
wait observably misses the second batch — the skill races its own push
against the bots' response window. `--wait N` where `N < 10` is clamped
up to 10; a warning is logged but the loop proceeds with the clamped
value rather than failing.

This floor is a β addition (Section 5-adjacent) motivated by a real
incident during the β smoke-test run: a manual 0-minute "wait" between
iterations missed a second batch of Copilot findings that arrived 12
minutes after the first. The floor prevents that race mechanically.

## Inputs from context

- `context.iteration` — current iteration number (1-indexed)
- `context.no_wait_first_iteration` — bool, set by `pr-followup`
- `context.wait_override_minutes` — optional int from `--wait N` argument
- `context.pr_number`

## Behavior

1. If `context.iteration == 1` AND `context.no_wait_first_iteration` is
   true, skip the wait entirely. Set `no_wait_first_iteration = false`
   for subsequent iterations. (Rationale: `pr-followup` is invoked by
   the user *after* new comments are known to have arrived; no point
   waiting another 10 minutes.)
2. Otherwise, compute `delay_seconds`:
   - If `context.wait_override_minutes` is set: `delay_seconds =
     max(600, wait_override_minutes * 60)`. If the clamp fires
     (user asked for less than 10 minutes), emit a `wait_clamped`
     log event so the operator sees that the floor kicked in:
     ```json
     {"event": "wait_clamped", "data": {
       "requested_minutes": <N>,
       "effective_minutes": 10,
       "reason": "reviewer-bot response window"
     }}
     ```
     Do not error out — the clamp is a feature, not a failure.
   - Else use 600 (10 minutes).
3. Call `ScheduleWakeup`:
   ```
   ScheduleWakeup(
     delaySeconds = delay_seconds,
     reason = f"waiting for reviewer activity on PR #{context.pr_number} (cycle {context.iteration})",
     prompt = <the verbatim invocation prompt that entered this skill>
   )
   ```
   The invocation prompt is passed back so when the wakeup fires, the
   skill re-enters at the next step (02-fetch-comments).

## Cache note

Delays > 300s pay the Anthropic prompt-cache TTL cost. 600s (the
floor) is past that boundary. Accepted tradeoff — the skill is
optimizing for bot-response capture, not cache warmth.

## Manual orchestration

Operators running the skill by hand (not via `ScheduleWakeup`) MUST
still honor the 10-minute floor between fetches. Budgeting less than
10 minutes of wall-clock between a push and the next fetch is a known
footgun — reviewer bots can post with arbitrary latency within that
window. Document the start timestamp before sleeping and verify
elapsed time >= 600s before invoking step 02.

## Exit

The step does not "return" — `ScheduleWakeup` suspends the session.
The loop continues at step 02 after the wakeup fires.
