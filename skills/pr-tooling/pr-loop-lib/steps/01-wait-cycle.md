# Loop step 01 — Wait cycle (event-driven)

Subscribes to PR activity via the GitHub MCP webhook tool so that
reviewer-bot comments and CI events wake the loop immediately, rather
than relying on a blind timer. A `ScheduleWakeup` fallback fires after
10 minutes in case webhook delivery is delayed or unavailable.

## Entry modes

Determine the entry mode before doing anything else:

**Mode S — Skip** (`context.no_wait_first_iteration == true` AND
`context.iteration == 1`):
`pr-followup` sets this flag because the user knows comments have
already arrived. Jump straight to step 02. See "Mode S" below.

**Mode E — Event-driven** (a `<github-webhook-activity>` message is
present in the current conversation turn):
A webhook event has just arrived. Jump straight to step 02. See
"Mode E" below.

**Mode W — Wait** (none of the above):
Subscribe to PR activity, set the fallback wakeup, and yield. See
"Mode W" below.

---

## Mode S — Skip

Set `context.no_wait_first_iteration = false`. Write state.

Log a `wait_skipped` event:
```json
{"event": "wait_skipped", "data": {"iteration": 1, "reason": "no_wait_first_iteration"}}
```

Proceed to step 02.

**This is the only skip path.** The orchestrator MUST NOT skip the wait
because the repo has no CI, because prior PRs show no bot activity,
because the repo is personal or a fork, or for any other inferred
reason. Reviewer-bot latency is invisible until a comment lands. The
only legitimate bypass is the explicit `no_wait_first_iteration` flag.

---

## Mode E — Event-driven

A `<github-webhook-activity>` message has arrived. Extract the event
type from the message if discernible (e.g., `pull_request_review`,
`pull_request_review_comment`, `issue_comment`, `check_run`).

Log a `webhook_event_received` event:
```json
{"event": "webhook_event_received", "data": {
  "iteration": <context.iteration>,
  "event_type": "<type or 'unknown'>"
}}
```

Proceed to step 02.

---

## Mode W — Wait

### 1. Subscribe to PR activity

Call `mcp__github__subscribe_pr_activity` with:
- `owner` and `repo` from `context` (extracted from the remote URL at
  step 01-detect-context, or via `gh repo view --json nameWithOwner`)
- `pullNumber = context.pr_number`

This call is **idempotent** — safe on every iteration even if already
subscribed. Set `context.webhook_subscribed = true`. Write state.

Log a `webhook_subscribed` event:
```json
{"event": "webhook_subscribed", "data": {
  "iteration": <context.iteration>,
  "pr_number": <context.pr_number>
}}
```

### 2. Compute fallback delay

`fallback_seconds`:
- If `context.wait_override_minutes` is set:
  `fallback_seconds = max(60, wait_override_minutes * 60)`
  (60-second floor — prevents a misconfigured override from creating a
  tight poll loop, but no 10-minute floor: this is a fallback, not the
  primary wait mechanism)
- Else: `fallback_seconds = 600` (10 minutes)

### 3. Schedule fallback wakeup

```
ScheduleWakeup(
  delaySeconds = fallback_seconds,
  reason = "fallback poll for PR #<pr_number> (cycle <iteration>) — waiting for webhook event",
  prompt = <the verbatim invocation prompt that entered this skill>
)
```

The fallback fires if no webhook event arrives within `fallback_seconds`.
When it fires the skill re-enters; step 01 will be in Mode W again
with `context.wait_done_for_iteration == context.iteration` (set in
step 4 below), which signals "wakeup already issued for this iteration
→ proceed to step 02" (see "Wakeup re-entry" below).

### 4. Mark wait issued for this iteration

Set `context.wait_done_for_iteration = context.iteration`. Write state.

Log a `wait_cycle` event:
```json
{"event": "wait_cycle", "data": {
  "iteration": <context.iteration>,
  "mode": "webhook",
  "fallback_seconds": <fallback_seconds>
}}
```

Emit to the user:
```
Waiting for PR #<N> activity (iteration <N>).
Will wake on the next reviewer comment or CI event.
Fallback poll in <M> min if nothing arrives.
```

### 5. Yield

Stop generating output. The session now awaits either:
- A `<github-webhook-activity>` message → Mode E on next step 01 entry.
- The fallback `ScheduleWakeup` firing → re-entry (see below).

---

## Wakeup re-entry detection

When `ScheduleWakeup` fires the skill re-enters from the invocation
prompt. Step 01 is reached again. The entry mode is **not** Mode E
(no webhook event in this turn) and **not** Mode S (skip flag is
false). Before falling into Mode W again and issuing a duplicate
subscription + wakeup, check:

```
if context.wait_done_for_iteration == context.iteration:
    # fallback wakeup fired; the wait for this iteration is complete
    → proceed to step 02
```

Log a `wait_fallback_fired` event:
```json
{"event": "wait_fallback_fired", "data": {
  "iteration": <context.iteration>,
  "fallback_seconds": <fallback_seconds used>
}}
```

Then proceed to step 02.

---

## Inputs from context

| Field | Used for |
|---|---|
| `context.iteration` | Current iteration (1-indexed once loop starts) |
| `context.no_wait_first_iteration` | Mode S skip flag |
| `context.wait_override_minutes` | Fallback delay override |
| `context.pr_number` | PR to subscribe to |
| `context.wait_done_for_iteration` | Wakeup re-entry detection |
| `context.webhook_subscribed` | Informational; subscription is idempotent regardless |

---

## Why the 10-minute floor is gone

The former step used a hard 600-second `ScheduleWakeup` floor to give
reviewer bots a window to post follow-up findings. That floor was a
polling-era approximation: because the skill fetched on a fixed timer,
a shorter wait observably missed second-batch comments.

With webhook subscriptions the loop wakes on the actual event, not on
a timer. A first bot comment at 2 minutes wakes the loop, which
fetches all comments at that moment (including any that arrived in the
seconds before the fetch). If a second bot posts at 8 minutes, that
event triggers the next iteration. There is no race because step 02
always does a full fetch of all current comments — it is not
incremental.

The 10-minute fallback still ensures the loop does not hang forever if
webhook delivery fails. Operators who previously relied on `--wait N`
to extend the polling interval can use it to extend the fallback
timeout instead.

---

## Cache note

Delays > 300 s pay the Anthropic prompt-cache TTL cost. The 600 s
fallback is past that boundary. Accepted tradeoff — the skill is
optimizing for bot-response capture, not cache warmth.

---

## Exit

- Mode S and Mode E proceed to step 02 inline (no suspension).
- Mode W calls `ScheduleWakeup` and then stops. The loop continues
  at step 02 after either a webhook event or the fallback wakeup.
