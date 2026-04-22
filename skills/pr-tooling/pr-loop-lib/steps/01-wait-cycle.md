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

## No assumption-based skip

**The wait is MANDATORY on every iteration unless an explicit flag set
by the user or by `pr-followup` says otherwise.** The only two skip
paths are:
- `context.no_wait_first_iteration == true` (set by `pr-followup`, or
  by the user's `--no-wait` flag on `pr-autopilot`), AND
- `context.iteration == 1`.

No other condition — no matter how persuasive — justifies shortening
or skipping the wait. In particular, the orchestrator **MUST NOT**
skip the wait because:

- The repo has no `.github/workflows/` directory or no visible CI.
- Prior PRs on the repo show no reviewer-bot activity.
- The repo is personal, a fork, a sandbox, or "looks bot-free".
- The only current comment on the PR is the orchestrator's own
  `/code-review` post.
- The session is interactive and the user "is sitting right there".
- The loop "obviously has nothing to do" — triage would be
  degenerate.

These signals are **not reliable evidence of the absence of async
reviewers.** GitHub Copilot code review, org-level review policies,
SonarCloud, CodeQL, mergewatch, and human reviewers all operate
server-side or out-of-band; their activity is invisible from the
repo tree until a comment actually lands. The whole point of the
10-minute wait is to give them that window.

If the orchestrator catches itself constructing a rationale like
"this repo doesn't have bots, so I'll skip the wait" — that is the
exact failure mode the floor prevents. Do the wait.

The only correct way to bypass the wait is for the *user* to invoke
`pr-followup` (which sets the flag because the user knows comments
have arrived) or to pass `--no-wait` to `pr-autopilot` explicitly.
Neither can be inferred from repo inspection.

## Behavior

1. If `context.iteration == 1` AND `context.no_wait_first_iteration` is
   true, skip the wait entirely. Set `no_wait_first_iteration = false`
   for subsequent iterations. (Rationale: `pr-followup` is invoked by
   the user *after* new comments are known to have arrived; no point
   waiting another 10 minutes. `--no-wait` on `pr-autopilot` is the
   equivalent user-driven bypass.) **This is the ONLY skip path. See
   "No assumption-based skip" above — no other condition skips the
   wait.**
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

Operators (including LLM orchestrators) running the skill by hand —
not via `ScheduleWakeup` — MUST still honor the 10-minute floor
between fetches. Budgeting less than 10 minutes of wall-clock between
a push and the next fetch is a known footgun: reviewer bots can post
with arbitrary latency within that window.

**Required procedure:**
1. Record the start timestamp (UTC) before sleeping.
2. Sleep (or suspend via `ScheduleWakeup`) until at least 600 s have
   elapsed.
3. Verify elapsed time >= 600 s before invoking step 02.
4. Log a `wait_cycle` event with
   `{iteration, start_ts, end_ts, elapsed_seconds}`.

The elapsed-time check is the authoritative gate — a manual
`ScheduleWakeup` with `delaySeconds < 600` or a no-op sleep is a
skill violation regardless of how confident the operator is that
"nothing will arrive in that window."

**Never rationalize skipping the wait on grounds like "no CI
workflows visible", "personal repo", "no prior bot activity on this
repo", or "the only comment is my own code review."** Reviewer
latency is unknowable from the repo tree. If the user wants a
shorter cycle, the correct interface is `pr-followup` or
`pr-autopilot --no-wait` — both of which are explicit user consent,
not orchestrator inference.

## Exit

The step does not "return" — `ScheduleWakeup` suspends the session.
The loop continues at step 02 after the wakeup fires.
