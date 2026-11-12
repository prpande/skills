# Loop step 04 — Dispatch fixers

Spawn parallel subagents to address each actionable item from step 03.
Conflict-avoidance and clustering rules apply.

## Worktree root

The caller may pass the worktree root: the absolute path of the repository
the fixes are made in. `{{WORKTREE_ROOT}}` is that path. When the caller
passes none it is the absolute path of the current working directory, which
is how this step always ran. Read every `git` command in this step as
`git -C {{WORKTREE_ROOT}} ...`, and resolve every path a fixer returns in
`files_changed` against the root.

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

Units that share no file may run at the same time. Units that share a
file run one after another.

## Rolling dispatch

Hosts cap how many subagents one session runs at once, and the cap
counts this step's fixers and verifiers together. Keep at most 5 of them
running (fewer when the host's cap is lower):

1. Put every unit in a queue, in triage order.
2. Whenever a slot is free, start a waiting verifier first. With no
   verifier waiting, start the first queued unit that shares no file
   with a unit still running or still being verified. A unit whose base
   could not be recorded is not started.
3. When a fixer returns, its slot is free: its verifier is the next
   dispatch.
4. A dispatch the host refuses because of its cap goes back to the front
   of its queue and is tried again when the next subagent returns. A
   refusal is never a failed fixer.

The step ends when the queue is empty and every return is verified.

## Unit base

Immediately before dispatching a unit, record its base: a **snapshot
tree** of the whole working tree, written without a commit, a ref, or a
change to the real index:

```bash
idx="$(git rev-parse --absolute-git-dir)/pr-loop-snapshot-index"
rm -f "$idx" "$idx.lock"
GIT_INDEX_FILE="$idx" git read-tree HEAD &&
  GIT_INDEX_FILE="$idx" git add -A && GIT_INDEX_FILE="$idx" git write-tree
echo "exit=$?"; rm -f "$idx"
```

It prints a tree id then `exit=0`. The tree holds every tracked file as
it is on disk and every untracked file git does not ignore, so
uncommitted and untracked work (the normal state under `--dry-run`) is
in the base. Ignored files are not in it.

An empty id or a non-zero exit is a failure: take the snapshot once
more. On a second failure do not dispatch the unit; record each of its
items `needs-human` with reason "could not record a base", and log
`error {stage: "unit-base"}`. Never fall back to `HEAD`.

Store in `context.unit_bases` one entry per item, keyed by the item's
`feedback_id`: `{base, unit, order}`. `unit` is the unit's id: the
item's own `feedback_id` for a single item, and for a cluster
`cluster-<feedback_id of its first item>`; every member of a cluster
gets an entry with the same `base`, `unit` and `order`. `order` is the
1-based dispatch sequence number in this run of the step. Set
`context.unit_bases` to `{}` when this step starts. The **wave base** is
the `base` with `order` 1.

The base is what the unit's diff and its rollback are measured against,
so an earlier unit's accepted fix in the same file, and any uncommitted
work already in the tree, is neither shown to the verifier as this
unit's change nor lost in a rollback.

## Rollback

One procedure, used by every rollback in this step, in
`04.5-local-verify.md` and in pr-autopilot's pre-open fix round, with
or without `--dry-run`. A caller may put its own rollback in place of
the verifier-ladder one; pr-watch does (its fix path's "Roll back"
section). The procedure takes a base tree and a list of normalised
files ("Agent return handling"). For each file:

1. The base holds it (`git cat-file -e <base>:<file>` succeeds):
   `git restore --source=<base> --worktree -- <file>`.
2. The base does not hold it and git ignores it
   (`git check-ignore -q -- <file>` exits 0): it existed before and git
   cannot restore it. Leave it, set the return's verdict to
   `needs-human`, and add "could not undo the edit to <file>" to its
   `reason`. An ignored file is never deleted.
3. The base does not hold it and the index tracks it
   (`git ls-files --error-unmatch -- <file>` succeeds): the path or the
   base is wrong. Leave it, set `needs-human`, same reason. A tracked
   file is never deleted by a rollback.
4. Otherwise the fixer created it: delete it, and log
   `rollback_deleted {feedback_id, file}`.

Never `git reset`, `git clean`, `git checkout -- <file>` or
`git stash pop`; never touch a file outside the list or a change from
an earlier iteration.

Who calls it with what:
- A verifier-ladder rollback (`not-addresses`, `feedback-wrong`) and the
  `ui-deferred` guard: the item's own `files_changed`, against its
  unit's base. In a cluster unit, a file that an accepted sibling item
  (`fixed`/`fixed-differently`, verifier `addresses`, or not yet
  verified) also lists is NOT restored: leave it, set the rejected item
  to `needs-human` with reason "its edit shares <file> with an accepted
  fix and was not rolled back". Verify every item of a cluster before
  rolling any of them back, so "accepted sibling" is known.
- `04.5-local-verify.md`'s second-failure rollback: every file in
  that step's file list, against the wave base. One
  base covers the whole wave, so no order between units matters and
  files only the retry subagent edited are covered.
- pr-autopilot's pre-open fix round uses the same two, with or without
  `--dry-run`.

When a rolled-back file also holds another unit's edit, see "Overlap
re-verify".

## Dispatch mechanics

For each unit:
1. Read `references/prompt-injection-defenses.md` (once, cached for all units).
2. Read `references/fixer-prompt.md`.
3. Generate a per-dispatch **fixer nonce** (8 hex chars) and verify it does not
   appear in the comment body before interpolating. Uses the same mechanism as
   the verifier nonce (see "Fixer-output verification" below):
   ```bash
   FIXER_NONCE=$(printf '%08x' $(( (RANDOM << 15) | RANDOM )))
   case "$COMMENT_BODY_VERBATIM" in
     *"_${FIXER_NONCE}"*)
       FIXER_NONCE=$(printf '%08x' $(( (RANDOM << 15) | RANDOM )))
       case "$COMMENT_BODY_VERBATIM" in
         *"_${FIXER_NONCE}"*) log fixer_nonce_collision; FIXER_NONCE=""; ;;
       esac ;;
   esac
   [ -z "$FIXER_NONCE" ] && escalate_to_needs_human && continue
   ```
4. Concatenate: defenses text + fixer template (defenses first). Substitute
   `{{FIXER_NONCE}}` throughout both texts with the generated nonce.
5. Substitute remaining placeholders: `{{OWNER}}`, `{{REPO}}`, `{{PR_NUMBER}}`,
   `{{PR_TITLE}}`, `{{BASE_BRANCH}}`, `{{HEAD_SHA}}`, `{{SURFACE_TYPE}}`,
   `{{FILE_PATH}}`, `{{LINE_NUMBER}}`, `{{AUTHOR_LOGIN}}`, `{{AUTHOR_TYPE}}`,
   `{{CREATED_AT}}`, `{{COMMENT_BODY_VERBATIM}}`, `{{FEEDBACK_ID}}`,
   `{{UI_DEFERRAL_OVERRIDE}}`, `{{WORKTREE_ROOT}}`. `{{UI_DEFERRAL_OVERRIDE}}` is the
   literal string `false` during the normal loop and `true` only when
   step 11's UI-deferred approval phase re-enters this step for items
   the user explicitly approved.
6. For cluster units, additionally substitute the cluster-brief XML block.
7. Record the unit base ("Unit base"), then spawn an agent via the host
   platform's agent-dispatch mechanism. On Claude Code: the `Agent`
   tool with `subagent_type: "pr-fixer"` and `model: "sonnet"`, both
   passed explicitly; an omitted model inherits the session's. Where
   the `pr-fixer` agent type is not installed, use
   `subagent_type: "general-purpose"` with the same model. The `Agent`
   tool takes no timeout, so none is passed or logged.

A fixer does not build or test (`references/fixer-prompt.md`).
`04.5-local-verify.md` verifies once, after every unit has returned and
been verified.

## Agent return handling

Each agent returns a JSON object per the fixer prompt's "Return format".
Collect all returns into `context.agent_returns`.

Validate each return:
- `verdict` is in the allowed set; otherwise coerce to `needs-human` and
  log a warning.
- `files_changed` paths exist under `{{WORKTREE_ROOT}}` and are inside it;
  reject absolute paths outside the worktree root. Before anything else
  reads them, rewrite each entry to the file's repo-relative path with
  forward slashes and the exact case git or the disk uses
  (`git ls-files --full-name -- <path>` for a tracked file; otherwise
  the path relative to the worktree root). An entry that resolves
  outside the worktree root is rejected as above. Every later step
  (diff, rollback, invariants, staging) uses the normalised path.
- `reply_text` is non-empty when verdict is not `not-addressing` of the
  `suspicious` flavor (those have canned replies from step 03).
- **`ui-deferred` guard:** if `verdict == "ui-deferred"` AND
  `files_changed` is non-empty, the fixer violated the contract in
  `references/fixer-prompt.md` ("UI / design deferral"). Treat this as
  an invariant fail: log `ui_deferred_touched_files` with
  `{feedback_id, files_changed}`, roll back ("Rollback"), clear
  `files_changed = []`, and
  demote the return to `needs-human` with reason
  "fixer returned ui-deferred but edited files; rolled back". Do NOT
  collect into `context.ui_deferred_items` in this case — the fixer's
  judgement is no longer trusted for this item.

## Fixer-output verification (mandatory)

Every fixer return with verdict `fixed` or `fixed-differently` is
verified by a secondary Haiku subagent before the return is accepted.
Defends against confidently-wrong reviewer feedback being applied
blindly.

### Procedure

For each fixer return where `verdict ∈ {fixed, fixed-differently}`:

1. Extract this unit's own diff, measured from its base ("Unit base"):
   ```bash
   git diff <base> -- <files_changed>
   ```
   for files the index tracks. For a file the index does not track,
   compare the base's copy with the file on disk: `git show
   <base>:<file>` (empty when the base does not hold it) against the
   file, with `git diff --no-index`. So an untracked file the user
   already had shows only the fixer's change.
   A cluster unit fixes several items with one diff. Its verifier is
   dispatched once per item, each time with that diff and a sibling
   list: for every other item the unit handled, its `feedback_id` and
   the first line of its comment body cut to 120 characters
   (`{{SIBLING_ITEMS}}`). The sibling list is untrusted. For a unit
   with one item the sibling list is `none`.
2. Read `pr-loop-lib/references/fixer-verifier-prompt.md`.
3. Generate a per-call **nonce** and verify it doesn't collide with any
   untrusted content (the feedback, the reason, the diff and the
   sibling list):
   ```bash
   NONCE=$(printf '%08x' $(( (RANDOM << 15) | RANDOM )))
   ```
   OR-ing two 15-bit `RANDOM` values after a 15-bit left-shift gives
   30 bits of uniformly distributed entropy using Bash builtins only.
   Before
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
   - `{{SIBLING_ITEMS}}` → the sibling list from step 1, rendered inside
     its own `<UNTRUSTED_SIBLINGS_${NONCE}>` block
   - `{{WORKTREE_ROOT}}` → the worktree root
5. Log a `subagent_dispatch` event with `role: "fixer-verifier"`,
   `model: "haiku"`, prompt first 200 chars, `feedback_id:
   <fixer_return.feedback_id>`.
6. Dispatch via the Agent tool with `subagent_type: "fix-verifier"` and
   `model: "haiku"`, both passed explicitly
   (`subagent_type: "general-purpose"` with the same model where the
   `fix-verifier` agent type is not installed). It runs under the
   "Rolling dispatch" cap.
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
| `not-addresses` | Demote to `needs-human`. Roll back the fixer's file changes ("Rollback"). Remove from `context.files_changed_this_iteration` only the rolled-back files that no other return with verdict `fixed` or `fixed-differently` still lists. Clear `fixer_return.files_changed = []` so invariant S04.4 (union across returns) still holds. Append verifier's reason to `fixer_return.reason`. |
| `feedback-wrong` | ONLY permitted when `fixer_return.verdict` was `fixed-differently`. If the fixer's verdict was `fixed`, the verifier cannot escalate to this (per the prompt); if it somehow returns `feedback-wrong` anyway, demote to `not-addresses` instead. Action: demote fixer's verdict to `not-addressing`, roll back files, remove from `context.files_changed_this_iteration` only the rolled-back files that no other return with verdict `fixed` or `fixed-differently` still lists, clear `fixer_return.files_changed = []`, set `fixer_return.reply_text` to: `> [quoted relevant sentence]\n\nNot addressing: a proposed fix was attempted and verified against the feedback; verification determined the feedback appears factually incorrect about the current code. Evidence: <verifier's reason>. Not making the change.` |

### Overlap re-verify

The conflict-avoidance graph usually prevents two parallel fixers from
touching the same file, but edge cases exist (e.g., the graph was built
from declared files but an agent modified an extra file). When a
rollback in the policy ladder restores a file F for rolled-back unit A,
any surviving return B in another unit that also lists F may have lost
its edit to F.

Procedure, run after **every** rollback in the policy ladder (steps
`not-addresses` and `feedback-wrong`):

```
1. Compute the overlap set:
     overlap_set = { survivor in agent_returns :
                       survivor.verdict in {fixed, fixed-differently}
                       AND survivor is in another unit than rolled_back
                       AND survivor.files_changed ∩ rolled_back.files_changed ≠ ∅ }

2. For each survivor B in overlap_set, for each file F in the overlap:

   a. B's order is lower than A's and B had returned before A was
      dispatched (the normal serialized case): A's base already holds
      B's fix and the restore kept it.
        - Log a fixer_reverify event with new_verdict: "kept-in-base".
        - No verifier is dispatched.

   b. Otherwise (the two ran at the same time, or B ran later: an
      overlap the graph did not see): B's edit to F cannot be told
      from A's.
        - Restore F to the base with the lower order of the two.
        - Demote B to needs-human with reason "shared <F> with a
          rolled-back fix"; remove F from B's files_changed and from
          context.files_changed_this_iteration unless another accepted
          return lists it.
        - Log a fixer_reverify event with new_verdict:
          "demoted-overlap".

   Each event is
        { survivor_id: survivor.feedback_id,
          rolled_back_id: rolled_back.feedback_id,
          overlap_files: [F, ...],
          new_verdict: <"kept-in-base" | "demoted-overlap"> }.

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
  files removed, except those another return with verdict `fixed` or
  `fixed-differently` still lists).
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

- Return verdicts `replied`, `not-addressing`, `needs-human`,
  `ui-deferred` → no verification runs. These already declined to
  change code (or deferred the change to the user).
- Return with `fixer_return.suspicious == true` → no verification runs.
  `suspicious` is a boolean flag on the return, not a verdict value;
  suspicious returns carry a canned `not-addressing` verdict plus the
  flag.
- Return with `files_changed: []` despite verdict `fixed`: log an
  `invariant_fail` and demote to `needs-human` (the fixer claimed a
  fix but produced no diff — bug).

## `ui-deferred` handling

Any agent returning `ui-deferred` (after the empty-`files_changed`
guard above passes):

- Its `reply_text` is posted in step 07 but the thread is NOT
  resolved. Step 07 uses the `ui-deferred` reply template.
- Append an entry to `context.ui_deferred_items` with
  `{feedback_id, thread_id?, path?, line?, author, body, proposal,
    reply_text}`, where `proposal` is the fixer's one-line description
  (from `fixer_return.reason`). Step 11 reads this list to prompt the
  user for approval at the end of the run.
- No verifier call, no sanity check entry, and no contribution to
  `context.files_changed_this_iteration` — `ui-deferred` never edits
  code during the loop.

Deferred items do NOT block quiescence. Step 07 posts a self-login
reply on the thread, but that alone does NOT cause Filter A to drop
the original reviewer comment on the next fetch — Filter A's
self-login pre-filter only drops the reply itself; the original
comment is still eligible for re-triage via the "new-since"
timestamp check. The mechanism that actually suppresses re-triage
is step 08 advancing `context.last_handled_timestamp = now` on
ui-deferred-present quiescent exits (see
`steps/08-quiescence-check.md` exit condition #2). The thread
remains open on the platform; the cursor advance keeps the loop
from re-dispatching the same item.

## `needs-human` handling

Any agent returning `needs-human` — whether directly, via policy-ladder
demotion, or via an overlap re-verify demotion:

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
- `context.ui_deferred_items` — subset deferred for end-of-run user
  approval (UI / design / copy changes). Not dispatched for auto-fix
  during the loop; step 11 prompts the user and, if approved, re-runs
  step 04 scoped to the approved items.
