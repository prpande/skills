# Loop step 01 — Wait cycle

Delays the next comment fetch to give reviewer bots time to post. Uses
`ScheduleWakeup` with a default delay of 600 seconds (10 minutes).

## Inputs from context

- `context.iteration` — current iteration number (1-indexed)
- `context.no_wait_first_iteration` — bool, set by `pr-followup`
- `context.wait_override_minutes` — optional int from `--wait N` argument
- `context.pr_number`

## Behavior

1. If `context.iteration == 1` AND `context.no_wait_first_iteration` is
   true, skip the wait entirely. Set `no_wait_first_iteration = false` for
   subsequent iterations.
2. Otherwise, compute `delay_seconds`:
   - If `context.wait_override_minutes` is set, use that * 60.
   - Else use 600 (10 minutes).
3. Call `ScheduleWakeup`:
   ```
   ScheduleWakeup(
     delaySeconds = delay_seconds,
     reason = f"waiting for reviewer activity on PR #{context.pr_number} (cycle {context.iteration})",
     prompt = <the verbatim invocation prompt that entered this skill>
   )
   ```
   The invocation prompt is passed back so when the wakeup fires, the skill
   re-enters at the next step (02-fetch-comments).

## Cache note

Delays > 300s pay the Anthropic prompt-cache TTL cost. 600s is past that
boundary. Accepted tradeoff — the skill is optimizing for bot-response
capture, not cache warmth.

## Exit

The step does not "return" — `ScheduleWakeup` suspends the session. The
loop continues at step 02 after the wakeup fires.
