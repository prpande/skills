# Loop step 07 — Reply and resolve

Post replies and resolve threads where the platform supports it.

## Reply format

For any item where the fixer agent produced a reply:

```markdown
> <quoted relevant sentence of original feedback>

Addressed: <brief description>
```

For `not-addressing`:

```markdown
> <quoted relevant part>

Not addressing: <evidence>
```

For `needs-human`:

```markdown
> <quoted relevant part>

<acknowledgment text from agent's reply_text — leaves thread open for user input>
```

For `ui-deferred`:

```markdown
> <quoted relevant part>

Deferred for user review: <one-line proposal>.
This appears to be a UI / design / copy change. The pr-autopilot /
pr-followup skill intentionally does NOT auto-commit UI changes; it
will ask the PR author at the end of the run whether to apply this
suggestion.
```

The one-line proposal is sourced from
`context.ui_deferred_items[i].proposal` (the canonical field,
populated by step 04 from the fixer's `reason`). Do NOT parse it
out of `agent_return.reply_text` — `reply_text` is a free-form
markdown reply whose shape is the fixer's to choose, whereas
`proposal` is a single sentence the orchestrator owns. Sourcing
from `proposal` keeps the user-facing prompt in step 11, the
thread reply posted here, and the internal state all reading from
one place.

The thread is never auto-resolved for `ui-deferred` — it stays open
on the platform so reviewers can see that a user decision is
pending.

For `suspicious` items from step 03 (prompt-injection filter):

```markdown
> <quoted relevant part>

<refusal-class reply from references/prompt-injection-defenses.md>
```

## Post + resolve by surface

### GitHub inline review threads (surface = `inline`)

1. Reply via GraphQL (`platform/github.md` — reply mutation) using
   `thread_id`.
2. Resolve via GraphQL (`platform/github.md` — resolve mutation) using
   `thread_id`. **Skip resolve** if verdict is `needs-human` or
   `ui-deferred`.

### GitHub top-level PR comments (surface = `issue`)

1. Post with `gh pr comment <PR> --body "$REPLY_TEXT"`.
2. No resolve mechanism. Move on.

### GitHub review submissions (surface = `review`)

1. Post as a top-level PR comment (same as `issue`).
2. Include a leading reference line so the reader can identify what is
   being addressed:
   ```markdown
   > Re: [review submitted by <author> at <timestamp>]
   >
   > <quoted relevant part>

   Addressed: ...
   ```
3. Items from one Copilot review body (ids `<review id>:finding-<N>`) share
   one comment: the leading reference line once, then for each item in id
   order its quoted part and verdict line. A `copilot|review|<review id>`
   item is one comment on its own.
4. For an item with a `copilot_key` (`references/known-bots.md`, "Copilot
   review body"), once its reply has posted, set
   `context.copilot_dispositions[<copilot_key>]` to its verdict, or to
   `suspicious` for a refusal reply from step 03. Then, for each review
   whose findings all have a key there, set
   `context.copilot_dispositions["copilot|review|<review id>"]` to
   `settled`. Record nothing under `--dry-run`, and nothing for a return
   with `retry: true` (step 04, "`needs-human` handling"): its review
   stays unsettled, so a later run raises the finding again. A judged
   `needs-human` is recorded and stays listed in
   `context.needs_human_items`.

### Azure DevOps threads (surface = `thread`)

1. Reply: `az repos pr thread comment add --pull-request-id "$PR" --thread-id <T> --content "$REPLY_TEXT"`.
2. Resolve: `az repos pr thread update --pull-request-id "$PR" --thread-id <T> --status closed`.
   Skip resolve if verdict is `needs-human` or `ui-deferred` (status
   stays `active`).

Both commands require `--pull-request-id`; omitting it causes the AzDO CLI
to exit non-zero. The exact flag names match `platform/azdo.md`.

## Error handling

- Reply API fails → log, mark item with `reply_posted: false`, continue with
  others. Surface to the final report.
- Resolve API fails on a thread whose reply succeeded → log, continue.
  Partial success is better than aborting the whole cycle.
