# Loop step 01 — Wait cycle (event-driven)

On GitHub, subscribes to PR activity via the GitHub MCP webhook tool so
that reviewer-bot comments and CI events wake the loop immediately. A
`ScheduleWakeup` fallback fires after 10 minutes in case webhook
delivery is delayed or unavailable. On AzDO, falls back to a pure
`ScheduleWakeup` polling wait with the original 10-minute reviewer-bot
floor (AzDO has no equivalent webhook tool).

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
Subscribe (GitHub) or schedule a polling wakeup (AzDO), then yield.
See "Mode W" below.

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

Behavior depends on `context.platform`. Both paths set
`context.wait_done_for_iteration` and issue a `ScheduleWakeup` as a
fallback; the difference is whether a webhook subscription is also
established.

> **`wait_done_for_iteration` note:** Mode W sets this field to
> `context.iteration` before yielding. It is never explicitly reset
> between iterations — it is simply overwritten by the next Mode W
> entry. Mode E does not touch it, so after a webhook wake on
> iteration N the field still holds N. When iteration N+1 enters
> Mode W, it overwrites the field with N+1. The invariant is:
> `wait_done_for_iteration == context.iteration` if and only if a
> wakeup has been issued for the **current** iteration.

---

### GitHub path (`context.platform == "github"`)

#### Step 1 — Subscribe to PR activity

Extract `owner` and `repo` for the current repository:

```
- Prefer `gh repo view --json nameWithOwner` and split the returned
  `owner/repo` string on `/`.
- If that is unavailable, parse the Git remote URL
  (`git remote get-url origin`) to determine them.
```

Call `mcp__github__subscribe_pr_activity` with the extracted `owner`,
`repo`, and `pullNumber = context.pr_number`.

This call is **idempotent** — safe on every iteration even if already
subscribed.

**On success:** Set `context.webhook_subscribed = true`. Write state.
Log a `webhook_subscribed` event:
```json
{"event": "webhook_subscribed", "data": {
  "iteration": <context.iteration>,
  "pr_number": <context.pr_number>
}}
```

**On failure** (network error, tool unavailable, permission error):
Log a `webhook_subscribe_failed` event:
```json
{"event": "webhook_subscribe_failed", "data": {
  "iteration": <context.iteration>,
  "pr_number": <context.pr_number>
}}
```
Leave `context.webhook_subscribed = false`. Continue to steps 2–5 —
the fallback wakeup becomes the primary wait mechanism for this
iteration.

#### Step 2 — Compute fallback delay

`fallback_seconds`:
- If `context.wait_override_minutes` is set:
  `fallback_seconds = max(60, wait_override_minutes * 60)`
  If the clamp fires (user asked for less than 1 minute), emit a
  `wait_clamped` log event:
  ```json
  {"event": "wait_clamped", "data": {
    "requested_minutes": <N>,
    "effective_minutes": 1,
    "reason": "minimum fallback interval (webhook-primary path)"
  }}
  ```
- Else: `fallback_seconds = 600` (10 minutes)

The 1-minute floor prevents a misconfigured `--wait` from creating a
tight poll loop. Note: in environments where webhook delivery is
unavailable (e.g., self-hosted runners behind strict network policies),
the fallback becomes the primary mechanism and very short `--wait`
values will cause rapid polling. A minimum of 5 minutes is recommended
when operating without webhook support.

#### Step 3 — Schedule fallback wakeup

```
ScheduleWakeup(
  delaySeconds = fallback_seconds,
  reason = "fallback poll for PR #<pr_number> (cycle <iteration>) — waiting for webhook event",
  prompt = <the verbatim invocation prompt that entered this skill>
)
```

#### Step 4 — Mark wait issued + log

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

#### Step 5 — Yield

Stop generating output. The session now awaits either:
- A `<github-webhook-activity>` message → Mode E on next step 01 entry.
- The fallback `ScheduleWakeup` firing → re-entry (see "Wakeup
  re-entry detection" below).

---

### AzDO path (`context.platform == "azdo"`)

No webhook MCP tool is available. Use a pure `ScheduleWakeup` with
the original 10-minute reviewer-bot floor.

#### Step 1 — Compute delay

`delay_seconds`:
- If `context.wait_override_minutes` is set:
  `delay_seconds = max(600, wait_override_minutes * 60)`
  If the clamp fires (user asked for less than 10 minutes), emit a
  `wait_clamped` log event:
  ```json
  {"event": "wait_clamped", "data": {
    "requested_minutes": <N>,
    "effective_minutes": 10,
    "reason": "reviewer-bot response window (AzDO polling path)"
  }}
  ```
- Else: `delay_seconds = 600` (10 minutes)

The 10-minute floor on AzDO is a hard rule: reviewer bots can post
follow-up findings 2–10 minutes after an initial review. A shorter
wait observably misses the second batch.

#### Step 2 — Schedule wakeup

```
ScheduleWakeup(
  delaySeconds = delay_seconds,
  reason = "polling wait for PR #<pr_number> (cycle <iteration>)",
  prompt = <the verbatim invocation prompt that entered this skill>
)
```

#### Step 3 — Mark wait issued + log

Set `context.wait_done_for_iteration = context.iteration`. Write state.

Log a `wait_cycle` event:
```json
{"event": "wait_cycle", "data": {
  "iteration": <context.iteration>,
  "mode": "azdo-poll",
  "delay_seconds": <delay_seconds>
}}
```

#### Step 4 — Yield

Stop generating output. The session resumes at step 02 after the
wakeup fires (see "Wakeup re-entry detection" below).

---

## Wakeup re-entry detection

When `ScheduleWakeup` fires the skill re-enters from the invocation
prompt. Step 01 is reached again. The entry mode is **not** Mode E
(no webhook event in this turn) and **not** Mode S (skip flag is
false). Before falling into Mode W again and issuing a duplicate
subscription + wakeup, check:

```
if context.wait_done_for_iteration == context.iteration:
    # fallback/polling wakeup fired; the wait for this iteration is complete
    → proceed to step 02
```

Re-derive `fallback_seconds` (or `delay_seconds` on AzDO) using the
same formula as Mode W step 2 for the current platform — the value is
deterministic from `context.wait_override_minutes` and
`context.platform`. Then log a `wait_fallback_fired` event:
```json
{"event": "wait_fallback_fired", "data": {
  "iteration": <context.iteration>,
  "delay_seconds": <re-derived value>
}}
```

Then proceed to step 02.

---

## Inputs from context

| Field | Used for |
|---|---|
| `context.platform` | Selects GitHub webhook path vs. AzDO polling path |
| `context.iteration` | Current iteration (1-indexed once loop starts) |
| `context.no_wait_first_iteration` | Mode S skip flag |
| `context.wait_override_minutes` | Fallback/polling delay override |
| `context.pr_number` | PR to subscribe to (GitHub path) |
| `context.wait_done_for_iteration` | Wakeup re-entry detection |
| `context.webhook_subscribed` | Informational; subscription is idempotent regardless |

---

## Why the 10-minute floor is gone (GitHub only)

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

The AzDO path retains the 10-minute floor unchanged since it remains
a polling-only mechanism.

---

## Cache note

Delays > 300 s pay the Anthropic prompt-cache TTL cost. The 600 s
fallback / floor is past that boundary. Accepted tradeoff — the skill
is optimizing for bot-response capture, not cache warmth.

---

## Exit

- Mode S and Mode E proceed to step 02 inline (no suspension).
- Mode W calls `ScheduleWakeup` and then stops. The loop continues
  at step 02 after either a webhook event (GitHub) or the wakeup timer.
