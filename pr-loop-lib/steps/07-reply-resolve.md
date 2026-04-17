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
   `thread_id`. **Skip resolve** if verdict is `needs-human`.

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

### Azure DevOps threads (surface = `thread`)

1. Reply: `az repos pr thread comment add --thread-id <T> --content "$REPLY_TEXT"`.
2. Resolve: `az repos pr thread update --thread-id <T> --status closed`.
   Skip resolve if verdict is `needs-human` (status stays `active`).

## Error handling

- Reply API fails → log, mark item with `reply_posted: false`, continue with
  others. Surface to the final report.
- Resolve API fails on a thread whose reply succeeded → log, continue.
  Partial success is better than aborting the whole cycle.
