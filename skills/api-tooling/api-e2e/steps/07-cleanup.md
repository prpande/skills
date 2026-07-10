# Phase 7 — Cleanup & close-out

Runs before the report's final delivery so its output sections are real.

## Teardown

- Delete every fixture enumerated in the `## Fixture ledger` section of
  `{scratchpad}/api-e2e/run-context.md`. Verify each deletion **by
  observation** — re-read or enumerate the object and confirm it is gone
  or cancelled — never by trusting the delete's status code. Where the API
  soft-deletes, query with include-inactive flags to see the truth.
- Restore user-designated mutables to their interviewed state if the user
  asked for restoration.
- Re-read a sample of no-touch objects (from no-touch.md, including
  collection-level counts) and confirm they are untouched.
- Enumerate every unavoidable leftover into the report's residual-state
  section — exactly, with ids and final positions.

## Durable learnings (optional, per doctrine)

- **Local memory write:** if the run produced durable learnings (a fixture
  recipe, a platform quirk), offer to save them to the user's LOCAL
  per-user memory with provenance (date, run context). Scrub personally
  identifying fixture fields first, using the same rule phase 6 applies to
  the report. Never write run state to any repo.
- **Skill-text PR proposal:** if the run discovered a durable METHOD
  improvement (a better derivation technique, a new invariant category, a
  failure-triage pattern), draft the skill-text diff and present it to the
  user for approval. The skill never self-writes its own text.

## Gate

Cleanup verified by observation; residual-state and cleanup-verification
sections handed to phase 6; any method-improvement proposal presented.
The RUN is complete only when phase 6 then delivers the approved report —
delivery is phase 6's gate, not this phase's.
