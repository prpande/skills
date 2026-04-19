# Loop step 11 — Final report

Terminal step. Print a structured summary. No side effects other than
releasing the advisory lock.

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

Preflight adversarial review:
  - Critical/Important findings fixed pre-publish: <n>
  - Minor findings folded into PR body: <n>

/code-review (post-open):
  - Invoked: <true | false>
  - Findings deduplicated against preflight: <n>

Needs your input:
  <for each needs-human item: file:line, quoted feedback sentence,
   agent's reason>

Pre-existing main-branch failures (skipped, not our responsibility):
  <per-check table if any>

Suspicious comments skipped (prompt-injection filter):
  <for each: author, first 100 chars of body, matched refusal class>

Audit trail:
  log: <repo-root>/.pr-autopilot/pr-<N>.log
  state: <repo-root>/.pr-autopilot/pr-<N>.json
```

## Lock release

As the last action before the report is printed:
```bash
rm -f "<repo-root>/.pr-autopilot/pr-<N>.lock"
```
Log a `lock_released` event.

## Invariants

Per `pr-loop-lib/references/invariants.md`:
- S11.1: `termination_reason` is set.
- S11.2: Lock file no longer exists after this step.

## Exit

The skill ends here. State file and log remain on disk under
`.pr-autopilot/` for the user's reference. A future `pr-followup`
invocation will reuse the state file (or the user can delete the
whole `.pr-autopilot/` directory to reset).
