# Loop step 02 — Fetch comments

Collect all PR comments from the platform into the unified schema. Downstream
steps treat all comments uniformly regardless of origin surface.

## Unified schema

```
{
  id:          <str>,              // unique within its surface
  surface:     inline|issue|review|thread,
  author:      <str>,               // login or display name
  author_type: User|Bot,
  created_at:  <ISO-8601>,
  updated_at:  <ISO-8601 | null>,
  path:        <str | null>,        // for file-anchored comments
  line:        <int | null>,
  body:        <str>,
  thread_id:   <str | null>,        // for resolvable threads
  is_resolved: <bool | null>
}
```

## GitHub

Fetch all three surfaces in parallel. Use the commands from
`platform/github.md`:

1. Inline comments → Surface 1
2. Issue comments → Surface 2
3. Review submissions (with non-empty body) → Surface 3

Then fetch the GraphQL `reviewThreads` query to get `thread_id` and
`is_resolved` for each inline comment. Join the GraphQL results into the
Surface 1 records by matching `databaseId` with the REST-returned `id`.

## Azure DevOps

Single call: `az repos pr thread list`. Normalize one record per thread-comment
pair. For threads with multiple comments, emit one record per comment;
each record carries the same `thread_id` and `is_resolved`.

## Output

A flat list of comment records. Store in `context.all_comments` for step 03.
Do not filter here — step 03 applies both the "new since last push" filter
and the actionability filter.

## Caveats

- Bot-reviewer retries and double-posts are common. Keep duplicates in the
  list; step 03's triage de-duplicates by comment text similarity when
  necessary.
- `updated_at` may differ from `created_at` when a reviewer edits a comment.
  Treat the comment as "new" if either timestamp is after
  `context.last_push_timestamp`.
