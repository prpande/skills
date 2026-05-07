# Loop step 01 — Wait cycle

Delays the next comment fetch to give reviewer bots time to post. Uses
`ScheduleWakeup` with a default delay of 300 seconds (5 minutes). The
~10-minute total wall-clock protection against late-arriving reviewer-bot
comments is now provided by step 08's two-consecutive-quiescent-iteration
exit rule (5 + 5 ≈ the original 10-minute window) rather than a single
10-minute wait per iteration.

## Minimum wait (floor)

**Hard rule: `delay_seconds` must be >= 300.** Reviewer bots (Copilot,
SonarCloud, mergewatch, `/code-review` after-action rounds) routinely
post follow-up findings 2–10 minutes after an initial review. The 5-minute
per-iteration floor is paired with step 08's "two consecutive quiescent
iterations" exit rule: a quiet first iteration loops back through this step
for another 5-minute wait before the loop is allowed to exit. The two legs
together preserve the original 10-minute wall-clock window the previous
single-leg 10-minute floor was designed for. `--wait N` where `N < 5` is
clamped up to 5; a `wait_clamped` warning event is logged but the loop
proceeds with the clamped value rather than failing.

This floor and the paired confirmation rule originated as a β addition,
motivated by a real incident during the β smoke-test run: a manual
0-minute "wait" between iterations missed a second batch of Copilot
findings that arrived 12 minutes after the first. The original mitigation
was a single 10-minute wait. The 2026-05-06 revision split that wait into
two 5-minute legs (one per iteration), giving the loop the same coverage
of the late-comment window while halving the time-to-react when bots DO
post in the first window.

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
two-leg 5-minute waits (paired with step 08's confirmation rule) is
to give them that window.

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
   waiting another 5 minutes on iteration 1. `--no-wait` on `pr-autopilot`
   is the equivalent user-driven bypass.) **This is the ONLY skip path,
   and it applies ONLY to iteration 1 — the confirmation iteration that
   step 08 may route back through this step always waits, regardless of
   `no_wait_first_iteration` (which is reset to `false` after iteration 1).
   See "No assumption-based skip" above — no other condition skips the
   wait.**
2. Otherwise, compute `delay_seconds`:
   - If `context.wait_override_minutes` is set: `delay_seconds =
     max(300, wait_override_minutes * 60)`. If the clamp fires
     (user asked for less than 5 minutes), emit a `wait_clamped`
     log event so the operator sees that the floor kicked in:
     ```json
     {"event": "wait_clamped", "data": {
       "requested_minutes": <N>,
       "effective_minutes": 5,
       "reason": "reviewer-bot response window (paired with two-iteration quiescence-confirmation)"
     }}
     ```
     Do not error out — the clamp is a feature, not a failure.
   - Else use 300 (5 minutes).
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

The Anthropic prompt-cache TTL is 5 minutes. 300 s (the new floor)
sits exactly on that boundary; the cache miss penalty is paid roughly
once per wait. The total wall-clock per soft-quiescent confirmation
cycle (one wait + step 02–08 work + a second wait) is past the TTL
window. Accepted tradeoff — the skill is optimizing for bot-response
capture, not cache warmth. A 270-s wait would stay cache-warm but
would chip away at the late-comment protection without a meaningful
user benefit; not chosen.

## Manual orchestration

Operators (including LLM orchestrators) running the skill by hand —
not via `ScheduleWakeup` — MUST still honor the 5-minute per-iteration
floor between fetches AND the two-consecutive-quiescent-iteration exit
rule in step 08. Budgeting less than 5 minutes of wall-clock between a
push and the next fetch — or skipping the confirmation iteration — is
a known footgun: reviewer bots can post with arbitrary latency within
that window. The two protections are paired, not independent.

**Required procedure:**
1. Compute the same `delay_seconds` the `ScheduleWakeup` path uses (see
   the "Behavior" section above): `max(300, (context.wait_override_minutes
   or 5) * 60)`. This honors `--wait N` for `N > 5` (e.g., `--wait 60` →
   3600 s) while still applying the 300 s floor when the user passed a
   sub-floor value or no override at all. Manual runs MUST use the same
   `delay_seconds` as the automated path, otherwise manual and
   `ScheduleWakeup`-driven runs would behave differently.
2. Record the start timestamp (UTC) before sleeping.
3. Sleep (or suspend via `ScheduleWakeup`) until at least `delay_seconds`
   have elapsed.
4. Verify elapsed time >= `delay_seconds` before invoking step 02.
5. Log a `wait_cycle` event with
   `{iteration, start_ts, end_ts, elapsed_seconds}`.

The elapsed-time check is the authoritative gate — a manual
`ScheduleWakeup` with `delaySeconds < delay_seconds` or a no-op sleep is
a skill violation regardless of how confident the operator is that
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
