# Loop step 11 — Final report

Terminal step. Print a structured summary. No side effects.

## Report template

```
===============================================================
pr-autopilot / pr-followup — FINAL REPORT
===============================================================

PR #<N> — <title>
URL: <link>

Termination reason:
  <ci-green | iteration-cap | ci-reentry-cap | ci-timeout |
   ci-pre-existing-failures | runaway-detected | user-intervention-needed>

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

Local sanity checks:
  - iterations with build + tests green: <X>/<Y>

CI status at termination: <green | red | skipped | timeout>
<per-check table if red or timeout>

Needs your input:
  <for each needs-human item: file:line, quoted feedback sentence, agent's
   structured decision context with options and recommendation>

Pre-existing main-branch failures (skipped, not our responsibility):
  <per-check table if any>

Suspicious comments skipped (prompt-injection filter):
  <for each: author, first 100 chars of body, matched refusal class>
```

## Exit

The skill ends here. No further iterations. The user is the decision-maker
for any remaining `needs-human` items or pre-existing failures. A future
invocation of `pr-followup` resumes the loop if new comments arrive.
