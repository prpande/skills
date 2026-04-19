# Loop step 04 — Dispatch fixers

Spawn parallel subagents to address each actionable item from step 03.
Conflict-avoidance and clustering rules apply.

## Cluster-analysis gate

Gate signals (either fires the gate):
1. `len(context.actionable) >= 3`
2. `context.all_comments` contains resolved threads alongside unresolved
   (cross-round signal — indicates this is not the first review pass).

If neither fires, skip clustering and dispatch each actionable item as an
individual unit.

If the gate fires:
1. Assign each actionable item one category from:
   `error-handling, validation, type-safety, naming, performance,
    testing, security, documentation, style, architecture, other`.
2. Group items where `same_category AND (same_file OR same_directory_subtree)`.
3. For each group with 2+ items, build a `<cluster-brief>` block (see
   `references/fixer-prompt.md` cluster extension).
4. Items not in any 2+ group remain individual units.

## Conflict avoidance

Build a file-overlap graph across all dispatch units (clusters + individuals):
- Nodes: dispatch units
- Edges: units that touch at least one common file

Non-overlapping groups dispatch in parallel. Overlapping groups serialize.
Batch size within a parallel group: 4.

## Dispatch mechanics

For each unit:
1. Read `references/prompt-injection-defenses.md` (once, cached for all units).
2. Read `references/fixer-prompt.md`.
3. Concatenate: defenses text + fixer template (defenses first).
4. Substitute placeholders: `{{OWNER}}`, `{{REPO}}`, `{{PR_NUMBER}}`,
   `{{PR_TITLE}}`, `{{BASE_BRANCH}}`, `{{HEAD_SHA}}`, `{{SURFACE_TYPE}}`,
   `{{FILE_PATH}}`, `{{LINE_NUMBER}}`, `{{AUTHOR_LOGIN}}`, `{{AUTHOR_TYPE}}`,
   `{{CREATED_AT}}`, `{{COMMENT_BODY_VERBATIM}}`, `{{FEEDBACK_ID}}`.
5. For cluster units, additionally substitute the cluster-brief XML block.
6. Spawn an agent via the host platform's agent-dispatch mechanism (on
   Claude Code: `Agent` tool with `subagent_type: "general-purpose"`).

## Agent return handling

Each agent returns a JSON object per the fixer prompt's "Return format".
Collect all returns into `context.agent_returns`.

Validate each return:
- `verdict` is in the allowed set; otherwise coerce to `needs-human` and
  log a warning.
- `files_changed` paths exist and are inside the repo; reject absolute paths
  outside the repo root.
- `reply_text` is non-empty when verdict is not `not-addressing` of the
  `suspicious` flavor (those have canned replies from step 03).

## Fixer-output verification (mandatory)

Every fixer return with verdict `fixed` or `fixed-differently` is
verified by a secondary Haiku subagent before the return is accepted.
Defends against confidently-wrong reviewer feedback being applied
blindly.

### Procedure

For each fixer return where `verdict ∈ {fixed, fixed-differently}`:

1. Extract the diff of just the files this fixer changed:
   ```bash
   git diff HEAD -- <files_changed>
   ```
2. Read `pr-loop-lib/references/fixer-verifier-prompt.md`.
3. Generate a per-call **nonce** and verify it doesn't collide with any
   untrusted content:
   ```bash
   NONCE=$(printf '%08x' $((RANDOM * RANDOM)))
   ```
   `RANDOM * RANDOM` gives ~30 bits of entropy from Bash builtins only
   — sufficient for non-cryptographic delimiter uniqueness. Before
   interpolating, verify that no slot body contains the literal string
   `_${NONCE}`. If it does, regenerate the nonce once; if the second
   nonce also collides, log a `verifier_nonce_collision` event with
   `{slot, body_sample}` and abort this verifier call (treat the
   return as if verifier errored — escalate the fixer to
   `needs-human`).
4. Render the template by substituting (every untrusted slot is wrapped
   in a **nonce-delimited** `<UNTRUSTED_*_${NONCE}>` block — see
   `references/fixer-verifier-prompt.md`):
   - `{{NONCE}}` → the 8-hex-char nonce from step 3
   - `{{FEEDBACK_BODY_VERBATIM}}` → the original comment body (the one
     this fixer was dispatched to address). Resolve the actionable
     item by matching `fixer_return.feedback_id` to each entry's
     `.id` in `context.actionable` (treat `actionable` as a list;
     optionally prebuild a `feedback_id → record` map at dispatch
     time). Use the matched record's `.body`.
   - `{{FIXER_VERDICT}}` → `fixer_return.verdict`
   - `{{FIXER_REASON}}` → `fixer_return.reason`
   - `{{FIXER_DIFF}}` → the diff from step 1
5. Log a `subagent_dispatch` event with `role: "fixer-verifier"`,
   `model: "haiku"`, prompt first 200 chars, `feedback_id:
   <fixer_return.feedback_id>`, `timeout_s: 60`.
6. Dispatch via the Agent tool with `subagent_type: "general-purpose"`.
   (Claude Code does not currently have a way to enforce Haiku-only
   dispatch per subagent; the prompt itself is designed to be handled
   by a cheaper model.)
7. Parse the JSON response. Expected shape:
   `{judgement: "addresses|partial|not-addresses|feedback-wrong", reason: "..."}`
8. Log a `subagent_return` event + a `verifier_judgement` event with
   before/after verdicts.
9. Apply the policy ladder (below).

### Policy ladder

| `judgement` | Action |
|---|---|
| `addresses` | Keep `fixer_return` as-is. Proceed. |
| `partial` | Demote `fixer_return.verdict` to `needs-human`. Append verifier's reason to `fixer_return.reason`. Keep the diff in the working tree (partial fix may be better than nothing). Thread stays unresolved. |
| `not-addresses` | Demote to `needs-human`. Roll back the fixer's file changes: `git checkout -- <files_changed>`. Remove those files from `context.files_changed_this_iteration`. Clear `fixer_return.files_changed = []` so invariant S04.4 (union across returns) still holds. Append verifier's reason to `fixer_return.reason`. |
| `feedback-wrong` | ONLY permitted when `fixer_return.verdict` was `fixed-differently`. If the fixer's verdict was `fixed`, the verifier cannot escalate to this (per the prompt); if it somehow returns `feedback-wrong` anyway, demote to `not-addresses` instead. Action: demote fixer's verdict to `not-addressing`, roll back files (and clear `fixer_return.files_changed = []`), set `fixer_return.reply_text` to: `> [quoted relevant sentence]\n\nNot addressing: a proposed fix was attempted and verified against the feedback; verification determined the feedback appears factually incorrect about the current code. Evidence: <verifier's reason>. Not making the change.` |

### Rollback scope

`git checkout -- <files>` is scoped strictly to files in
`fixer_return.files_changed`. Never touch files from earlier
iterations. If the fixer's changes were interleaved with another
parallel fixer's changes on the same file — which the conflict-
avoidance graph normally prevents but edge cases may slip through —
see "Overlap re-verify" below.

### Overlap re-verify

The conflict-avoidance graph usually prevents two parallel fixers from
touching the same file, but edge cases exist (e.g., the graph was built
from declared files but an agent modified an extra file). When a
rollback in the policy ladder removes fixer A's changes from a file F,
any surviving fixer B whose `files_changed` also lists F is now in a
possibly-broken state: B's original diff was computed against a base
that included A's changes, and B's claim that F is "fixed" may no
longer hold after A's rollback.

Procedure, run after **every** rollback in the policy ladder (steps
`not-addresses` and `feedback-wrong`):

```
1. Compute the overlap set:
     overlap_set = { survivor in agent_returns :
                       survivor.verdict in {fixed, fixed-differently}
                       AND survivor.files_changed ∩ rolled_back.files_changed ≠ ∅ }

2. For each survivor in overlap_set, for each file F in the overlap:

   a. Examine the CURRENT working-tree diff for F:
        current_diff_F = git diff HEAD -- F

   b. If current_diff_F is empty (survivor's change was entirely
      redundant with the rolled-back change, and the rollback wiped
      both):
        - Log a fixer_reverify event with new_verdict: "skipped-empty-diff".
        - Cascade-rollback: demote survivor to needs-human; clear
          survivor.files_changed of the overlap files; remove those
          files from context.files_changed_this_iteration; DO NOT
          re-dispatch the verifier (there is no diff to verify).

   c. Else (current_diff_F is non-empty):
        - Re-dispatch the verifier with the SAME prompt template but
          the current diff — follow the full "Fixer-output
          verification" procedure (including a fresh nonce per
          re-verify call).
        - Log a fixer_reverify event with
          { survivor_id: survivor.feedback_id,
            rolled_back_id: rolled_back.feedback_id,
            overlap_files: [F, ...],
            new_verdict: <the re-verify judgement> }.
        - Apply the policy ladder to the re-verify judgement:
            - addresses              → keep survivor as-is
            - partial / not-addresses → cascade-rollback (same action
                                         as the initial rollback would
                                         have taken)
            - feedback-wrong         → cascade-rollback
        - If the verifier errors (timeout, malformed return), escalate
          survivor to needs-human with termination_reason set to
          "user-intervention-needed" if this terminates the loop.

3. Update state after overlap re-verify completes: persist the
   revised agent_returns, files_changed_this_iteration, and
   verifier_judgements.

4. Invariant S04.7 (invariants.md) is checked at step end: no
   survivor's files_changed contains a file that was also in a
   rolled-back fixer's files_changed unless a fixer_reverify event
   exists for that survivor with the overlap file listed.
```

Overlap re-verify is idempotent: if a later rollback produces another
overlap with the same survivor, re-run step 2 for the new intersection.
One `fixer_reverify` event per (survivor, rolled_back) pair.

### State update

After processing all fixer returns:
- Persist updated `context.agent_returns` (with demoted verdicts).
- Persist `context.files_changed_this_iteration` (with rolled-back
  files removed).
- Persist `context.verifier_judgements` (one entry per verified
  return).

### Invariants

Per `pr-loop-lib/references/invariants.md`:
- **S04.3** — every return with an original verdict in `{fixed,
  fixed-differently}` must have a corresponding entry in
  `context.verifier_judgements`. Check this at step end; halt on
  violation.
- **S04.7** — after the policy ladder resolves, no surviving fixer's
  `files_changed` contains an entry that was also in a rolled-back
  fixer's `files_changed` unless a `fixer_reverify` log event for
  that survivor exists this step with the overlapping files listed in
  `overlap_files`. Enforced by the "Overlap re-verify" procedure above.

### Skip conditions

- Return verdicts `replied`, `not-addressing`, `needs-human` → no
  verification runs. These already declined to change code.
- Return with `fixer_return.suspicious == true` → no verification runs.
  `suspicious` is a boolean flag on the return, not a verdict value;
  suspicious returns carry a canned `not-addressing` verdict plus the
  flag.
- Return with `files_changed: []` despite verdict `fixed`: log an
  `invariant_fail` and demote to `needs-human` (the fixer claimed a
  fix but produced no diff — bug).

## `needs-human` handling

Any agent returning `needs-human` — whether directly, via policy-ladder
demotion, or via overlap re-verify cascade-rollback:

- Its `reply_text` is posted in step 07 but the thread is NOT resolved.
- Mark the item in `context.needs_human_items` for the final report.
- If the presence of `needs-human` items ultimately terminates the loop
  (step 08 reaches quiescence with `len(context.needs_human_items) > 0`
  and nothing else to do), set
  `context.termination_reason = "user-intervention-needed"` so the
  final report distinguishes this from the normal quiescent exit
  (where `termination_reason` would otherwise be unset or `ci-green`
  after the CI gate). See `context-schema.md` for the full
  `termination_reason` enum — only values listed there are valid. Step
  11 reads this field to render an accurate termination reason to the
  operator.

## Output

- `context.agent_returns` — all returned JSON objects
- `context.files_changed_this_iteration` — union of `files_changed` across
  all agents
- `context.needs_human_items` — subset requiring user decision
