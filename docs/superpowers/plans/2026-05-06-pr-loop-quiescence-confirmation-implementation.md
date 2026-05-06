# pr-loop-lib Quiescence-Confirmation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Halve the per-iteration wait in the shared PR comment loop (10 min → 5 min) and require two consecutive quiescent iterations before exiting, per the design at `docs/superpowers/specs/2026-05-06-pr-loop-quiescence-confirmation-design.md`.

**Architecture:** Edits to the shared `pr-loop-lib`. Two new context fields, one new log event, one rewritten enum value, and one revised routing block in step 08. The `pr-autopilot` and `pr-followup` SKILL.md files inherit the change automatically; their text-level wait/floor callouts get freshened so the docs match the code.

**Tech Stack:** Markdown (skill file format) + YAML frontmatter. No runtime code in this plan — every change is documentation that an LLM follows at skill-execution time. Validator: `python scripts/validate.py` (already in repo). No unit-test runner. Smoke test is operator-driven on a real PR after merge; not in this plan.

**Working directory:** `C:/src/skills-pr-loop-quiescence-confirmation` on branch `pratyush/pr-loop-quiescence-confirmation` (worktree of `main`).

**Repo layout changes** (all edits — no new files):
```
skills/pr-tooling/pr-loop-lib/
  references/context-schema.md         (EDIT, Task 1)
  references/log-format.md             (EDIT, Task 2)
  steps/01-wait-cycle.md               (EDIT, Task 3)
  steps/08-quiescence-check.md         (EDIT, Task 4)
skills/pr-tooling/pr-followup/
  SKILL.md                             (EDIT, Task 5)
skills/pr-tooling/pr-autopilot/
  SKILL.md                             (EDIT, Task 6)
```

**Per-task cadence:** edit the file, run `python scripts/validate.py`, commit. Task 7 is a final cross-file consistency sweep with grep predicates.

---

## Task 1: Add the new state fields and rewrite `loop_exit_reason` enum in `context-schema.md`

**Files:**
- Modify: `skills/pr-tooling/pr-loop-lib/references/context-schema.md`

This task locks the contracts that all other tasks depend on. Do it first.

- [ ] **Step 1: Add the two new fields under "Loop runtime state"**

Open `skills/pr-tooling/pr-loop-lib/references/context-schema.md`. Find the row:

```
| `sanity_check_passed` | object | default `{}` | `{ <iteration>: <bool> }` |
```

Insert TWO new rows immediately before it (so the new fields sit at the end of the loop-runtime block, right before `sanity_check_passed`):

```
| `consecutive_quiescent_iterations` | integer | default `0` | Incremented on each soft-quiescent iteration (`quiescent-zero-actionable` or `quiescent-no-code-change`). Reset to `0` on any non-quiescent iteration outcome. Read by step 08 to decide between routing back to step 01 (counter == 1) or onward to step 09 (counter >= 2). |
| `last_quiescence_reason` | enum or null | default `null` | The most recent soft-quiescent reason; one of `quiescent-zero-actionable` \| `quiescent-no-code-change`. Set on each soft-quiescent iteration (in lockstep with `consecutive_quiescent_iterations` increment). Cleared (set to `null`) when the counter resets. Carried for the report and for log readability. |
```

- [ ] **Step 2: Rewrite the `wait_override_minutes` row**

Find this row (it currently sits in the same "Loop runtime state" table):

```
| `wait_override_minutes` | integer or null | no | From `--wait N`. Interpreted as `max(10, N)` by `pr-loop-lib/steps/01-wait-cycle.md` — the 10-minute floor applies to the *effective* delay, not the raw user input. Values below 10 are accepted at parse time but clamped up in step 01 with a warning log event. |
```

Replace it with:

```
| `wait_override_minutes` | integer or null | no | From `--wait N`. Interpreted as `max(5, N)` by `pr-loop-lib/steps/01-wait-cycle.md` — the 5-minute floor applies to the *effective* delay, not the raw user input. Values below 5 are accepted at parse time but clamped up in step 01 with a warning log event. The floor's reduction from 10 to 5 minutes is paired with the two-consecutive-quiescent-iteration exit rule in step 08, which together preserve the original ~10-minute wall-clock window for late-arriving reviewer-bot comments. |
```

- [ ] **Step 3: Rewrite the `loop_exit_reason` row**

Find this row in the "Termination" table:

```
| `loop_exit_reason` | enum or null | no | `quiescent-zero-actionable` \| `quiescent-no-code-change` \| `iteration-cap` \| `runaway-detected` |
```

Replace it with:

```
| `loop_exit_reason` | enum or null | no | `quiescent-confirmed` \| `iteration-cap` \| `runaway-detected`. The two old soft-quiescent values (`quiescent-zero-actionable`, `quiescent-no-code-change`) were removed in 2026-05-06; they no longer cause a loop exit on their own — they are recorded on `last_quiescence_reason` (above) on the first quiescent iteration, and the loop continues. Only the second consecutive quiescent iteration writes `loop_exit_reason = quiescent-confirmed` and exits. State files written by older skill versions may contain the removed values; that is expected — schema validation runs at write time, not on every read. |
```

- [ ] **Step 4: Run the validator**

Run: `python scripts/validate.py`
Expected: exit 0, no diagnostics for `context-schema.md`.

- [ ] **Step 5: Commit**

```bash
git add skills/pr-tooling/pr-loop-lib/references/context-schema.md
git commit -m "feat(pr-loop-lib): add quiescence-confirmation state fields

Add consecutive_quiescent_iterations and last_quiescence_reason fields.
Rewrite loop_exit_reason enum: remove the two soft-quiescent values
(they now live on last_quiescence_reason) and add quiescent-confirmed.
Drop wait_override_minutes floor from 10 to 5 minutes."
```

---

## Task 2: Add the `quiescence_pending` event and update `wait_clamped` in `log-format.md`

**Files:**
- Modify: `skills/pr-tooling/pr-loop-lib/references/log-format.md`

- [ ] **Step 1: Update the `wait_clamped` row in the event taxonomy table**

Find this row (currently on or near line 77):

```
| `wait_clamped` | `{requested_minutes, effective_minutes, reason}` — emitted by `pr-loop-lib/steps/01-wait-cycle.md` when `context.wait_override_minutes` is less than the 10-minute floor and gets clamped up. `requested_minutes` is the raw user input, `effective_minutes` is always 10. `reason` is a short string explaining the floor (e.g., `"reviewer-bot response window"`). Informational only — the loop continues with the clamped value |
```

Replace it with:

```
| `wait_clamped` | `{requested_minutes, effective_minutes, reason}` — emitted by `pr-loop-lib/steps/01-wait-cycle.md` when `context.wait_override_minutes` is less than the 5-minute floor and gets clamped up. `requested_minutes` is the raw user input, `effective_minutes` is always 5. `reason` is a short string explaining the floor (e.g., `"reviewer-bot response window (paired with two-iteration quiescence-confirmation)"`). Informational only — the loop continues with the clamped value |
```

- [ ] **Step 2: Add the `quiescence_pending` row**

Insert this row immediately after the existing `quiescence` row (`| \`quiescence\` | \`{reason, loop_exit_reason, termination_reason}\` |`) so the two related events sit together:

```
| `quiescence_pending` | `{iteration, reason, next_wait_seconds}` — emitted by `pr-loop-lib/steps/08-quiescence-check.md` when the *first* of two consecutive soft-quiescent iterations completes. `reason` is one of `quiescent-zero-actionable` \| `quiescent-no-code-change`. `next_wait_seconds` is the wait length step 01 will use before the confirming iteration (300 by default; `context.wait_override_minutes * 60` if set). Informational; the loop routes back to step 01 instead of step 09. The next iteration that actually exits (whether confirmed quiescent or by cap/runaway) emits the existing `quiescence` event. |
```

- [ ] **Step 3: Run the validator**

Run: `python scripts/validate.py`
Expected: exit 0, no diagnostics for `log-format.md`.

- [ ] **Step 4: Commit**

```bash
git add skills/pr-tooling/pr-loop-lib/references/log-format.md
git commit -m "feat(pr-loop-lib): add quiescence_pending log event

Add quiescence_pending event for the first-of-two soft-quiescent
iteration case. Update wait_clamped's effective_minutes to 5."
```

---

## Task 3: Drop the wait floor and default to 5 minutes in `01-wait-cycle.md`

**Files:**
- Modify: `skills/pr-tooling/pr-loop-lib/steps/01-wait-cycle.md`

This task replaces every reference to 600 s / 10 min with 300 s / 5 min, and rewrites the rationale prose to reference the new two-leg protection. The "no assumption-based skip" prose remains intact; only the duration constants and the cross-references change.

- [ ] **Step 1: Rewrite the opening summary line**

Find the file's first paragraph:

```
Delays the next comment fetch to give reviewer bots time to post. Uses
`ScheduleWakeup` with a default delay of 600 seconds (10 minutes).
```

Replace with:

```
Delays the next comment fetch to give reviewer bots time to post. Uses
`ScheduleWakeup` with a default delay of 300 seconds (5 minutes). The
~10-minute total wall-clock protection against late-arriving reviewer-bot
comments is now provided by step 08's two-consecutive-quiescent-iteration
exit rule (5 + 5 ≈ the original 10-minute window) rather than a single
10-minute wait per iteration.
```

- [ ] **Step 2: Rewrite the "Minimum wait (floor)" section**

Find the section heading `## Minimum wait (floor)` and replace the entire section (heading + body up to but not including `## Inputs from context`) with:

```
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

```

- [ ] **Step 3: Rewrite the override calc and default**

Find this block in the "Behavior" section:

```
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
```

Replace with:

```
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
```

- [ ] **Step 4: Update the "Cache note" section**

Find:

```
## Cache note

Delays > 300s pay the Anthropic prompt-cache TTL cost. 600s (the
floor) is past that boundary. Accepted tradeoff — the skill is
optimizing for bot-response capture, not cache warmth.
```

Replace with:

```
## Cache note

The Anthropic prompt-cache TTL is 5 minutes. 300 s (the new floor)
sits exactly on that boundary; the cache miss penalty is paid roughly
once per wait. The total wall-clock per soft-quiescent confirmation
cycle (one wait + step 02–08 work + a second wait) is past the TTL
window. Accepted tradeoff — the skill is optimizing for bot-response
capture, not cache warmth. A 270-s wait would stay cache-warm but
would chip away at the late-comment protection without a meaningful
user benefit; not chosen.
```

- [ ] **Step 5: Update the "Manual orchestration" section**

Find:

```
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
```

Replace with:

```
Operators (including LLM orchestrators) running the skill by hand —
not via `ScheduleWakeup` — MUST still honor the 5-minute per-iteration
floor between fetches AND the two-consecutive-quiescent-iteration exit
rule in step 08. Budgeting less than 5 minutes of wall-clock between a
push and the next fetch — or skipping the confirmation iteration — is
a known footgun: reviewer bots can post with arbitrary latency within
that window. The two protections are paired, not independent.

**Required procedure:**
1. Record the start timestamp (UTC) before sleeping.
2. Sleep (or suspend via `ScheduleWakeup`) until at least 300 s have
   elapsed.
3. Verify elapsed time >= 300 s before invoking step 02.
4. Log a `wait_cycle` event with
   `{iteration, start_ts, end_ts, elapsed_seconds}`.

The elapsed-time check is the authoritative gate — a manual
`ScheduleWakeup` with `delaySeconds < 300` or a no-op sleep is a
skill violation regardless of how confident the operator is that
"nothing will arrive in that window."
```

- [ ] **Step 6: Update the inline rationale block (still inside "No assumption-based skip" / "Behavior")**

Find any remaining "10-minute" prose. Specifically, find:

```
The whole point of the
10-minute wait is to give them that window.
```

Replace with:

```
The whole point of the
two-leg 5-minute waits (paired with step 08's confirmation rule) is
to give them that window.
```

And find:

```
   true, skip the wait entirely. Set `no_wait_first_iteration = false`
   for subsequent iterations. (Rationale: `pr-followup` is invoked by
   the user *after* new comments are known to have arrived; no point
   waiting another 10 minutes. `--no-wait` on `pr-autopilot` is the
   equivalent user-driven bypass.) **This is the ONLY skip path. See
   "No assumption-based skip" above — no other condition skips the
   wait.**
```

Replace with:

```
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
```

- [ ] **Step 7: Verify no stale "600", "10 minute", or "10-minute" strings remain**

Run from the worktree root:

```bash
grep -nE '\b600\b|10[- ]minute|ten minute' skills/pr-tooling/pr-loop-lib/steps/01-wait-cycle.md
```

Expected: no output. If any line is reported, re-read that paragraph in context and update it to the new 300 s / 5-minute / two-leg story. (Hits inside fenced code blocks describing OLD behavior should be rewritten or deleted — the file should describe current behavior only.)

- [ ] **Step 8: Run the validator**

Run: `python scripts/validate.py`
Expected: exit 0, no diagnostics for `01-wait-cycle.md`.

- [ ] **Step 9: Commit**

```bash
git add skills/pr-tooling/pr-loop-lib/steps/01-wait-cycle.md
git commit -m "feat(pr-loop-lib): drop wait floor to 5 minutes

Default and floor: 600 s -> 300 s. Rewrite Minimum-wait, Cache-note,
and Manual-orchestration sections to reference the paired two-iteration
quiescence-confirmation rule that preserves the original 10-minute
wall-clock window for late-arriving reviewer-bot comments."
```

---

## Task 4: Add the confirmation-counter rule to `08-quiescence-check.md`

**Files:**
- Modify: `skills/pr-tooling/pr-loop-lib/steps/08-quiescence-check.md`

This task is the behavior change. It teaches step 08 to increment a counter on soft-quiescent iterations, route back to step 01 until the counter reaches 2, and only then exit to step 09 with the new `quiescent-confirmed` reason.

- [ ] **Step 1: Insert the confirmation-counter section**

Open `skills/pr-tooling/pr-loop-lib/steps/08-quiescence-check.md`. Find the heading:

```
## Exit conditions (any one triggers exit)
```

Replace it with:

```
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
```

- [ ] **Step 2: Rewrite the "Recording the exit reason" section**

Find:

```
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
```

Replace with:

```
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

`context.last_quiescence_reason` is the most recent soft-quiescent
reason; carried for the report. It is set on each soft-quiescent
iteration and cleared (set to `null`) on each non-quiescent iteration.
On a `quiescent-confirmed` exit, it reflects the second iteration's
reason.
```

- [ ] **Step 3: Rewrite the "Routing" section**

Note on the outer fence below: this step uses 4-backtick fences so the
inner pseudocode (triple-backtick) passes through unchanged. When you
paste the replacement content into `08-quiescence-check.md`, paste the
content BETWEEN the outer 4-backtick lines — including the inner
triple-backticks — verbatim.

Find:

````
## Routing

- If exit reason is `quiescent-zero-actionable` OR `quiescent-no-code-change`
  → proceed to step 09 (CI gate).
- If exit reason is `iteration-cap` OR `runaway-detected` → skip step 09
  and proceed directly to step 11 (final report). The user decides next
  steps; do not gate on CI because the user may intend to abandon the
  branch or investigate manually.
````

Replace with:

````
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
````

- [ ] **Step 4: Verify no stale wording remains**

Run from the worktree root:

```bash
grep -nE 'quiescent-zero-actionable|quiescent-no-code-change' skills/pr-tooling/pr-loop-lib/steps/08-quiescence-check.md
```

Expected: hits exist (the file still names these reasons in the Exit conditions list, the confirmation-rule section, the "Recording the exit reason" section, and the routing pseudocode). Sanity-check that EVERY hit is in one of these contexts:
- Naming the soft-quiescent reasons in the Exit conditions list (items 1 and 2).
- Naming the values written to `last_quiescence_reason`.
- Naming the values that trigger the counter increment.
- Naming valid `exit_reason` inputs to the routing pseudocode.

Specifically, NONE of the hits should describe these values being written to `loop_exit_reason` or causing a direct route to step 09. If any hit reads as "set `loop_exit_reason = quiescent-zero-actionable`" or "if `loop_exit_reason == quiescent-*` proceed to step 09," fix that paragraph — the schema removed those values from `loop_exit_reason`.

- [ ] **Step 5: Run the validator**

Run: `python scripts/validate.py`
Expected: exit 0, no diagnostics for `08-quiescence-check.md`.

- [ ] **Step 6: Commit**

```bash
git add skills/pr-tooling/pr-loop-lib/steps/08-quiescence-check.md
git commit -m "feat(pr-loop-lib): require two consecutive quiescent iterations

Soft-quiescent iterations (zero-actionable, no-code-change) now
increment context.consecutive_quiescent_iterations and route back to
step 01 instead of exiting. Only the second consecutive soft-quiescent
iteration writes loop_exit_reason = quiescent-confirmed and routes to
step 09. iteration-cap and runaway-detected bypass the rule and exit
immediately as before."
```

---

## Task 5: Update `pr-followup/SKILL.md` to reflect the new wait/floor/confirmation

**Files:**
- Modify: `skills/pr-tooling/pr-followup/SKILL.md`

Two prose touchpoints already identified by grep:

```
36:- `--wait <minutes>` — override loop wait delay. **Floor: 10 minutes.**
38:  the skill never waits less than 10 minutes between iterations (see
```

- [ ] **Step 1: Rewrite the `--wait` flag block**

Find:

```
- `--wait <minutes>` — override loop wait delay. **Floor: 10 minutes.**
  Values less than 10 are clamped up to 10 with a warning log event;
  the skill never waits less than 10 minutes between iterations (see
  `pr-loop-lib/steps/01-wait-cycle.md` "Minimum wait"). Applies to
  second-iteration-onwards even when `--no-wait` / the `pr-followup`
  default `no_wait_first_iteration = true` skipped the first wait.
```

Replace with:

```
- `--wait <minutes>` — override loop wait delay. **Floor: 5 minutes.**
  Values less than 5 are clamped up to 5 with a warning log event;
  the skill never waits less than 5 minutes between iterations (see
  `pr-loop-lib/steps/01-wait-cycle.md` "Minimum wait"). Applies to
  second-iteration-onwards even when `--no-wait` / the `pr-followup`
  default `no_wait_first_iteration = true` skipped the first wait.
  The 5-minute floor is paired with step 08's two-consecutive-quiescent-
  iteration exit rule, which together preserve the ~10-minute wall-clock
  window for late-arriving reviewer-bot comments — a quiet first
  iteration loops back through step 01 for another wait before the loop
  is allowed to exit.
```

- [ ] **Step 2: Run the validator**

Run: `python scripts/validate.py`
Expected: exit 0, no diagnostics for `pr-followup/SKILL.md`.

- [ ] **Step 3: Verify no stale "10 minute" or "10-minute" strings remain in this file**

Run from the worktree root:

```bash
grep -nE '10[- ]minute|ten minute|\b600\b' skills/pr-tooling/pr-followup/SKILL.md
```

Expected: no output. If anything reports, edit the paragraph in context.

- [ ] **Step 4: Commit**

```bash
git add skills/pr-tooling/pr-followup/SKILL.md
git commit -m "docs(pr-followup): update --wait floor to 5 minutes

Reflects the pr-loop-lib floor change. Also names the paired
two-iteration quiescence-confirmation rule so users understand
why a quiet first iteration doesn't immediately exit."
```

---

## Task 6: Update `pr-autopilot/SKILL.md` to reflect the new wait/floor/confirmation

**Files:**
- Modify: `skills/pr-tooling/pr-autopilot/SKILL.md`

Touchpoints already identified by grep:

```
39:- `--wait <minutes>` → override loop wait delay. **Floor: 10 minutes.**
41:  the skill never waits less than 10 minutes between iterations (see
42:  `pr-loop-lib/steps/01-wait-cycle.md` "Minimum wait"). The 10-minute
49:  the 10-minute floor.
115:  inspection.** The 10-minute `ScheduleWakeup` (or manual-sleep
```

- [ ] **Step 1: Rewrite the `--wait` flag block (and the related `--no-wait` line)**

Find:

```
- `--wait <minutes>` → override loop wait delay. **Floor: 10 minutes.**
  Values less than 10 are clamped up to 10 with a warning log event;
  the skill never waits less than 10 minutes between iterations (see
  `pr-loop-lib/steps/01-wait-cycle.md` "Minimum wait"). The 10-minute
  floor is a hard rule; reviewer bots can take up to ~10 min to post
  follow-up findings, and a shorter wait observably misses them.
- `--dry-run` → execute every step except `gh/az pr create`, push, and
  thread resolve mutations. Print what would happen.
- `--no-wait` → skip the **first** wait cycle only (useful when bots
  are known to have already posted). Subsequent iterations still honor
  the 10-minute floor.
```

Replace with:

```
- `--wait <minutes>` → override loop wait delay. **Floor: 5 minutes.**
  Values less than 5 are clamped up to 5 with a warning log event;
  the skill never waits less than 5 minutes between iterations (see
  `pr-loop-lib/steps/01-wait-cycle.md` "Minimum wait"). The 5-minute
  floor is paired with step 08's two-consecutive-quiescent-iteration
  exit rule; together they preserve the ~10-minute wall-clock window
  needed to capture late reviewer-bot findings while halving the
  time-to-react when bots DO post in the first window.
- `--dry-run` → execute every step except `gh/az pr create`, push, and
  thread resolve mutations. Print what would happen.
- `--no-wait` → skip the **first** wait cycle only (useful when bots
  are known to have already posted). Subsequent iterations still honor
  the 5-minute floor, AND the confirmation iteration that step 08 may
  route back through step 01 always waits — `--no-wait` cannot be used
  to skip the confirmation leg.
```

- [ ] **Step 2: Rewrite the "Hard rules" bullet about the wait**

Find:

```
- **Never skip or shorten the wait cycle on the basis of repo
  inspection.** The 10-minute `ScheduleWakeup` (or manual-sleep
  equivalent) between iterations is MANDATORY. It cannot be bypassed
  because the repo has no visible `.github/workflows/`, because
  prior PRs show no bot activity, because the repo is personal or a
  fork, because the only PR comment is the orchestrator's own
  `/code-review` post, or because the session is interactive.
  Reviewer latency — Copilot code review, org-level policies,
  SonarCloud, human reviewers — is invisible until a comment lands.
  The only legitimate bypasses are the explicit user flags
  `--no-wait` (on `pr-autopilot`) or the `no_wait_first_iteration`
  set by `pr-followup`. See `pr-loop-lib/steps/01-wait-cycle.md`
  "No assumption-based skip".
```

Replace with:

```
- **Never skip or shorten the wait cycle on the basis of repo
  inspection.** The 5-minute `ScheduleWakeup` (or manual-sleep
  equivalent) between iterations is MANDATORY, and the second wait
  cycle that step 08's confirmation rule routes through step 01 is
  ALSO mandatory. Neither can be bypassed because the repo has no
  visible `.github/workflows/`, because prior PRs show no bot
  activity, because the repo is personal or a fork, because the
  only PR comment is the orchestrator's own `/code-review` post,
  or because the session is interactive. Reviewer latency — Copilot
  code review, org-level policies, SonarCloud, human reviewers — is
  invisible until a comment lands. The only legitimate bypasses are
  the explicit user flags `--no-wait` (on `pr-autopilot`) or the
  `no_wait_first_iteration` set by `pr-followup`, both of which
  apply ONLY to iteration 1 — the confirmation iteration always
  waits. See `pr-loop-lib/steps/01-wait-cycle.md` "No assumption-based
  skip".
```

- [ ] **Step 3: Run the validator**

Run: `python scripts/validate.py`
Expected: exit 0, no diagnostics for `pr-autopilot/SKILL.md`.

- [ ] **Step 4: Verify no stale "10 minute", "10-minute", or "600" strings remain in this file**

Run from the worktree root:

```bash
grep -nE '10[- ]minute|ten minute|\b600\b' skills/pr-tooling/pr-autopilot/SKILL.md
```

Expected: no output. If anything reports, edit the paragraph in context.

- [ ] **Step 5: Commit**

```bash
git add skills/pr-tooling/pr-autopilot/SKILL.md
git commit -m "docs(pr-autopilot): update --wait floor to 5 minutes

Reflects the pr-loop-lib floor change. Hard-rules section now names
the confirmation-iteration wait as also mandatory; --no-wait still
only applies to iteration 1."
```

---

## Task 7: Final cross-file consistency sweep

**Files:**
- No edits expected (verification only). If issues are found, fix them in the appropriate file from the previous tasks and amend or add a follow-up commit.

This task catches drift between files — e.g., the schema names a field one way and step 08 names it another way, or a "300 s" survives in one place but "5 minutes" in another.

- [ ] **Step 1: Field-name consistency between schema and step 08**

Run from the worktree root:

```bash
grep -nE 'consecutive_quiescent_iterations|last_quiescence_reason|quiescent-confirmed' \
  skills/pr-tooling/pr-loop-lib/references/context-schema.md \
  skills/pr-tooling/pr-loop-lib/steps/08-quiescence-check.md \
  skills/pr-tooling/pr-loop-lib/references/log-format.md
```

Expected: all three identifiers (`consecutive_quiescent_iterations`, `last_quiescence_reason`, `quiescent-confirmed`) appear in BOTH `context-schema.md` AND `08-quiescence-check.md`. `quiescent-confirmed` should NOT appear in `log-format.md` (it lives on `loop_exit_reason`, surfaced via the existing `quiescence` event whose payload-keys are documented but whose enum values are documented in the schema). `quiescence_pending` should appear in `log-format.md` and `08-quiescence-check.md`.

If any identifier is named in only one file, fix the gap.

- [ ] **Step 2: Constant consistency across all touched files**

Run from the worktree root:

```bash
grep -rnE '\b300\b|5[- ]minute|five minute' \
  skills/pr-tooling/pr-loop-lib/steps/01-wait-cycle.md \
  skills/pr-tooling/pr-loop-lib/references/context-schema.md \
  skills/pr-tooling/pr-loop-lib/references/log-format.md \
  skills/pr-tooling/pr-followup/SKILL.md \
  skills/pr-tooling/pr-autopilot/SKILL.md
```

Expected: every file shows at least one hit. Spot-check that the "5 minutes" / "300 s" usage is consistent — no file should mix "5 minutes" (the new) with "10 minutes" (the old) for the same wait constant. (10-minute *wall-clock* references describing the paired two-leg total are valid and should remain.)

Run the inverse check:

```bash
grep -rnE '\b600\b|10[- ]minute|ten minute' \
  skills/pr-tooling/pr-loop-lib/steps/01-wait-cycle.md \
  skills/pr-tooling/pr-loop-lib/references/context-schema.md \
  skills/pr-tooling/pr-loop-lib/references/log-format.md \
  skills/pr-tooling/pr-followup/SKILL.md \
  skills/pr-tooling/pr-autopilot/SKILL.md
```

Expected: hits ONLY in contexts that describe the original incident (β smoke-test rationale) or the paired two-leg ~10-minute total wall-clock window. Each remaining hit should read like history or wall-clock-total context, never like "we wait 10 minutes per iteration." Fix any that read like the latter.

- [ ] **Step 3: Schema-enum consistency for `loop_exit_reason`**

Run from the worktree root:

```bash
grep -nE 'loop_exit_reason' \
  skills/pr-tooling/pr-loop-lib/references/context-schema.md \
  skills/pr-tooling/pr-loop-lib/references/invariants.md \
  skills/pr-tooling/pr-loop-lib/steps/08-quiescence-check.md \
  skills/pr-tooling/pr-loop-lib/steps/11-final-report.md
```

Expected: every value written to `loop_exit_reason` in step 08's pseudocode is one of `quiescent-confirmed`, `iteration-cap`, `runaway-detected`. `references/invariants.md` predicates S08.1 and S08.3 must enumerate (or reference) only those three values — a stale "4 enum values" or `{quiescent-*}` wildcard in invariants is the failure mode this PR's preflight caught. `11-final-report.md` should not name a `loop_exit_reason` value that was removed from the enum. (If step 11 references `loop_exit_reason` at all, sanity-check those mentions; the report's printed "Termination reason" is `termination_reason`, not `loop_exit_reason`, so no template change is expected — but the file may name the field in commentary.)

- [ ] **Step 4: Walk through the routing scenarios from the spec**

Open the spec at `docs/superpowers/specs/2026-05-06-pr-loop-quiescence-confirmation-design.md`. For EACH of the 7 test scenarios in its "Test scenarios" section, mentally trace the loop using only the prose in the modified step files (01 and 08) and the schema, and confirm:
- Counter increments and resets land where the spec expects.
- The exit reason that fires matches the spec's expected exit.
- The events emitted (`quiescence_pending`, `quiescence`, `wait_clamped` where applicable) match what the log-format documentation now describes.

This is a paper exercise — not a code run. If a scenario can't be traced cleanly through the docs, the docs are missing something; go back to the relevant task and tighten the prose.

- [ ] **Step 5: Run the full validator one more time**

Run from the worktree root: `python scripts/validate.py`
Expected: exit 0 across the entire repo (the validator scans more than just our touched files).

- [ ] **Step 6: Final summary commit (if any consistency fixes were needed)**

If Steps 1–4 turned up issues that were fixed in this task, commit them under the appropriate file's task heading via a single follow-up commit:

```bash
git add <touched files>
git commit -m "fix(pr-loop-lib): cross-file consistency sweep for quiescence-confirmation"
```

If no fixes were needed, this task ends with no additional commit.

- [ ] **Step 7: Push the branch and open a PR via `pr-autopilot`**

This is the operator's call, not part of this plan's automated steps. The intended invocation is:

```bash
git push -u origin pratyush/pr-loop-quiescence-confirmation
# Then, in a fresh Claude Code session at the worktree:
/pr-autopilot
```

The first PR run will exercise the new behavior end-to-end (5-min waits + two-leg confirmation). If `pr-autopilot` itself misbehaves under the new defaults, that surfaces immediately as part of normal review.
