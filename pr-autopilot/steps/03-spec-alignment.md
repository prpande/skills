# Step 03 — Spec / plan alignment

Reconcile the diff against intent documents (specs, plans, tasks). Fix
drift. Block the PR when a required requirement is provably missing and
not auto-fixable.

## Skip conditions

- `context.spec_candidates` is empty → skip this step entirely.

## Match specs to the current work

Run the spec-candidate ranking from step 01. Keep candidates where:
- `mtime_days <= 30`, AND
- `keyword_overlap > 0` with the branch name, AND
- the spec file mentions at least one file or module in the diff.

If multiple match, use the highest-ranked. If the highest-ranked is older
than 7 days, ask the user: "Which spec does this PR implement? (list)".

If none match, log `"no spec alignment performed — no matching candidate"`
and skip to step 04.

## Drift classification

For each matched spec, compare against the diff:

| Drift type | Detection | Handling |
|---|---|---|
| Missing required | Spec contains a "must", "shall", or checked `tasks.md` item whose described file/behavior is not present in the diff | See "Missing-required handling" below |
| Additive code | Diff adds a file or symbol not mentioned in the spec | Update spec prose to add a brief description |
| Renamed / refactored | Spec names a file/symbol that doesn't exist in the diff but a similarly-named one does | Update spec with the new name |
| Contradictory | Spec says "return 400" but diff returns 200 | Check conversation history (see below); auto-update spec if user directed, else flag |
| Over-delivered | Diff implements spec's items plus additional unrelated behavior | Flag for user decision |

## Missing-required handling (C with fallback to B)

For each missing-required drift:

1. Assess auto-fixability:
   - **Small**: the required change affects a single file.
   - **Clear**: the spec gives a concrete behavior (input → output, or
     explicit code snippet), not a vague directive.
   - **Single-concern**: not tangled with multiple other unresolved drifts.

2. If **all three** criteria are met → auto-implement:
   - Dispatch a fixer subagent (loop lib `04-dispatch-fixers.md` mechanics)
     with the spec excerpt as the directive and the target file path.
   - After the fixer returns, re-run `04.5-local-verify.md`.
   - If the build/tests pass, the drift is resolved; continue.
   - If they fail twice, fall back to the diagnostic path (next bullet).

3. Otherwise → write a diagnostic block to `stderr`-equivalent
   (structured output back to the user) and exit the skill cleanly:

   ```
   HALT — spec-alignment drift requires manual resolution.

   Spec: <relative path>
   Line: <N>
   Expected: <brief description of the required behavior>
   Expected file: <path from spec>
   Diff evidence: <summary of what the diff DOES do in that area, if anything>

   Resolve by:
     - Implementing the missing behavior, OR
     - Updating the spec if the requirement is obsolete or superseded, OR
     - Splitting this PR into a scoped subset of the spec and marking the
       remainder as a follow-up.

   Re-invoke pr-autopilot when resolved.
   ```

   Do not open the PR.

## Conversation-history check (contradictory / over-delivered drift)

Scan the current Claude Code session for user-directed deviations. Trigger
phrases (case insensitive):

- "change to", "actually let's", "instead", "don't do", "drop the",
  "update the spec", "override", "skip the", "the spec is wrong",
  "we're going with".

If any match appears in the user's messages AND the context of the message
aligns with the drift, update the spec silently to reflect the code. Else
escalate to the user via the final report.

If the session has no relevant conversation context (e.g., the skill was
invoked in a fresh session without the implementation history), skip the
scan and apply the source-of-truth heuristic below directly.

## Source-of-truth heuristic (no conversation evidence)

- Required (must / shall / checked tasks.md) → spec wins. Treat missing
  code as Missing-required drift.
- Additive / refactor → code wins. Update spec prose.
- Contradictory behavior → flag; do NOT guess. Write the drift to
  `context.blocked_drifts` and HALT before step 04.

## Output

- `context.spec_updates` — list of `{spec_file, diff_summary}` applied,
  for inclusion in the PR commit.
- `context.blocked_drifts` — any that triggered HALT (step 04 does not run
  if this is non-empty).
- `context.spec_alignment_notes` — short bullet list describing silent
  auto-updates, for inclusion in PR body.
