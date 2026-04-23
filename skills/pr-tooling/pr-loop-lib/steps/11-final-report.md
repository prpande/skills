# Loop step 11 — Final report

Terminal step. Print a structured summary and — if there are UI /
design suggestions deferred during the loop — prompt the user for
per-item approval before releasing the advisory lock. Approved items
are re-dispatched through step 04 (scoped) and step 06 (commit +
push); nothing else in the loop's state is mutated.

## Report template

```
===============================================================
pr-autopilot / pr-followup — FINAL REPORT
===============================================================

PR #<N> — <title>
URL: <link>

Termination reason:
  <ci-green | ci-red | iteration-cap | ci-reentry-cap | ci-timeout |
   ci-pre-existing-failures | runaway-detected | ci-skipped |
   user-intervention-needed>

Iterations run:   <count> (cap: <user-supplied or default 10>)
CI re-entries:    <count>/3
Total commits:    <count>

Comments addressed (<total>):
  - fixed:            <n>
  - fixed-differently:<n>
  - replied:          <n>
  - not-addressing:   <n>
  - needs-human:      <n>  (threads remain open for user input)
  - ui-deferred:      <n>  (UI / design / copy — awaiting your approval below)
  - suspicious:       <n>  (prompt-injection filter fired)

Verifier judgements (<total>):
  - addresses:        <n>
  - partial:          <n>  (demoted to needs-human)
  - not-addresses:    <n>  (rolled back, demoted to needs-human)
  - feedback-wrong:   <n>  (rolled back, polite decline reply posted)

Local sanity checks:
  - iterations with build + tests green: <X>/<Y>

CI status at termination: <green | red | skipped | timeout>
<per-check table if red or timeout>

Internal review summary (local, not on PR):
  <repo-root>/.pr-autopilot/pr-<N>-review-summary.md

  Preflight (Pass 2):
    - Critical:   <n> fixed
    - Important:  <n> fixed
    - Minor:      <n> captured locally (NOT surfaced on PR)

  /code-review (post-open, captured — not posted):
    - Invoked:                    <true | false>
    - Raw findings:               <n>
    - Dedup vs preflight:         <n>
    - Fixed by internal dispatch: <n>
    - Fixed-differently:          <n>
    - Deferred (feedback-wrong):  <n>
    - Deferred (needs-human):     <n>

Needs your input:
  <for each needs-human item: file:line, quoted feedback sentence,
   agent's reason>

UI / design suggestions deferred to you (<total>):
  <for each ui_deferred_items entry: file:line, author, quoted
   feedback body (first 200 chars), fixer's one-line proposal
   (from .proposal). Thread URL if platform supports thread-linking.>

  You will be asked to approve, reject, or skip each item below. The
  skill does NOT auto-commit UI / design / copy changes — those are
  always a user decision.

Pre-existing main-branch failures (skipped, not our responsibility):
  <per-check table if any>

Suspicious comments skipped (prompt-injection filter):
  <for each: author, first 100 chars of body, matched refusal class>

Audit trail:
  log: <repo-root>/.pr-autopilot/pr-<N>.log
  state: <repo-root>/.pr-autopilot/pr-<N>.json
  review summary: <repo-root>/.pr-autopilot/pr-<N>-review-summary.md
```

The counts under "Internal review summary" are computed from
`context.internal_review_findings`, grouped by `source` and `status`.
The full detail (per-finding file:line, description, fixer/verifier
outcome) lives in the review-summary file on disk — step 11 only
prints counts to keep the terminal output scannable.

## UI-deferred user-approval phase

Runs after the report is printed, BEFORE lock release. Skipped
entirely when `context.ui_deferred_items` is empty.

### Prompting

For each entry in `context.ui_deferred_items`, ask the user via the
host's question mechanism (on Claude Code: `AskUserQuestion`) with
three options:

- **Apply fix and commit** — dispatch a fresh fixer for this item and
  push the resulting change.
- **Reject (post a polite decline)** — post a follow-up reply on the
  thread noting the suggestion was considered and declined; do not
  edit code.
- **Skip (leave thread open)** — take no further action; the PR
  author will handle it manually later.

Present the item's `path:line` (when known), author, the first 200
characters of the quoted feedback `body`, and the fixer's `proposal`
as context in the question body so the user can decide without
scrolling back through the report.

Batch prompting is acceptable for up to 4 items in a single
`AskUserQuestion` call (one question per item). For more than 4
items, loop with one question at a time. Do not group distinct
suggestions into a single multi-select — each item gets its own
three-way decision so the user is never forced to approve a bundle.

### Re-dispatch (for approved items only)

Collect every item the user marked **Apply fix and commit**. If the
list is non-empty:

1. Build a synthetic `context.actionable` containing only the
   approved items (preserve their original `id`, `surface`, `path`,
   `line`, `body`, `thread_id`). Do NOT overwrite the prior run's
   `actionable`; write to a scoped field
   `context.ui_deferred_actionable` instead.
2. Enter `pr-loop-lib/steps/04-dispatch-fixers.md` with the scoped
   list as its input. The fixer prompt's "UI / design deferral"
   guidance still applies, but the user's explicit approval is now
   part of the reason the fixer should proceed with a concrete
   change; the orchestrator passes a flag
   `ui_deferral_override: true` through the fixer prompt's PR
   context block (new placeholder `{{UI_DEFERRAL_OVERRIDE}}`) so
   the fixer treats the verdict space as `fixed` /
   `fixed-differently` / `replied` / `not-addressing` /
   `needs-human` only — `ui-deferred` is not a valid return in the
   override path.
3. Run `pr-loop-lib/steps/04.5-local-verify.md` then
   `pr-loop-lib/steps/06-commit-push.md` for the resulting diff.
   Skip steps 07 and 08 — the user has already decided; no
   quiescence check is needed.
4. Post a single follow-up reply per resolved thread summarizing the
   approved change (reuses step 07's reply format; thread IS
   resolved on success because the user explicitly approved).

### Reject path

For each item the user marked **Reject**:

1. Post a reply on the thread:
   ```markdown
   > <quoted feedback body, first 200 chars>

   Considered — the PR author has decided not to apply this UI
   change in this PR. Leaving the thread for further discussion if
   needed.
   ```
2. Do NOT resolve the thread — the user rejected the code change,
   not the conversation.

### Skip path

Take no action beyond what step 07 already did (the "deferred for
user review" reply is already on the thread). The thread stays open.

### Failure handling

If `AskUserQuestion` is unavailable (non-interactive host, batch CI
run), log a `ui_deferred_prompt_skipped` event with
`{reason: "no-interactive-host", count}` and fall through to lock
release. The ui-deferred items remain visible in the report and the
state file; a subsequent `pr-followup` invocation can re-prompt.

## Lock release

As the last action before the report is printed:
```bash
rm -rf "<repo-root>/.pr-autopilot/pr-<N>.lock"
```
Log a `lock_released` event. `rm -rf` is required because the lock
path is a **directory** under Primitive A of `state-protocol.md` —
`rm -f` on a directory fails ("Is a directory") and would leave S11.2
violated. The next `pr-autopilot` run would then find the dir still
present: since the lease inside wasn't refreshed (this session just
exited), within ~30 minutes it would **HALT at step 01's acquire**
with a "another session is active" diagnostic (session_id matches,
but lease is not being refreshed by anyone); after 30 minutes
stale-reclaim kicks in. Either way, next runs are blocked or delayed,
which is why `rm -rf` is mandatory here.

## Invariants

Per `pr-loop-lib/references/invariants.md`:
- S11.1: `termination_reason` is set.
- S11.2: Lock file no longer exists after this step.
- S11.3: If `context.ui_deferred_items` is non-empty at step entry,
  either a `ui_deferred_prompt_skipped` log event OR one
  `ui_deferred_decision` event per item (with `decision ∈ {apply,
  reject, skip}`) is present by step end.

## Exit

The skill ends here. State file and log remain on disk under
`.pr-autopilot/` for the user's reference. A future `pr-followup`
invocation will reuse the state file (or the user can delete the
whole `.pr-autopilot/` directory to reset).
