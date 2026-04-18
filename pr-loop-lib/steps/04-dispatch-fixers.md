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

## `needs-human` handling

Any agent returning `needs-human`:
- Its `reply_text` is posted in step 07 but the thread is NOT resolved.
- Mark the item in `context.needs_human_items` for the final report.

## Output

- `context.agent_returns` — all returned JSON objects
- `context.files_changed_this_iteration` — union of `files_changed` across
  all agents
- `context.needs_human_items` — subset requiring user decision
