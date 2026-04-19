# Loop step 02 — Fetch comments

Collect all PR comments from the platform into the unified schema. Downstream
steps treat all comments uniformly regardless of origin surface.

## Unified schema

All timestamps are stored as **Unix epoch integers** (seconds), not ISO-8601
strings. This avoids string-comparison bugs when mixing `date +%s` outputs
(state cursors) with API-returned timestamps, and makes Filter A arithmetic
trivial. Convert API timestamps at ingest using the portable two-command
pattern (GNU date / BSD date):

```bash
to_epoch() {
  date -d "$1" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%SZ" "$1" +%s
}
```

```
{
  id:           <str>,             // unique within its surface
  surface:      inline|issue|review|thread,
  author:       <str>,             // login or display name
  author_type:  User|Bot,
  created_at:   <int>,             // Unix epoch seconds (converted from ISO-8601)
  updated_at:   <int | null>,      // Unix epoch seconds, or null
  path:         <str | null>,      // for file-anchored comments
  line:         <int | null>,
  body:         <str>,
  thread_id:    <str | null>,      // for resolvable threads
  is_resolved:  <bool | null>
}
```

## Bounded fetch

To prevent `context.all_comments` from growing without bound on active PRs
(hundreds of bot comments per push), pass a `since` parameter at the API layer
rather than loading the full history and filtering in step 03.

Compute the fetch cursor from state (subtract 300 s to absorb clock skew):

```bash
NOW_EPOCH=$(date +%s)
FETCH_SINCE_EPOCH=${LAST_PUSH_EPOCH:-0}
# Use the max of the two cursors so we never miss comments
[ "${LAST_HANDLED_EPOCH:-0}" -gt "$FETCH_SINCE_EPOCH" ] && \
  FETCH_SINCE_EPOCH=${LAST_HANDLED_EPOCH}
# Subtract skew buffer; clamp to [0, now] to guard against unset/future values
FETCH_SINCE_EPOCH=$(( FETCH_SINCE_EPOCH - 300 ))
[ "$FETCH_SINCE_EPOCH" -lt 0 ] && FETCH_SINCE_EPOCH=0
[ "$FETCH_SINCE_EPOCH" -gt "$NOW_EPOCH" ] && FETCH_SINCE_EPOCH=$NOW_EPOCH
# Convert to ISO-8601 for the API `since` parameter
SINCE_ISO=$(date -u -d "@${FETCH_SINCE_EPOCH}" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
  || date -u -r "${FETCH_SINCE_EPOCH}" +%Y-%m-%dT%H:%M:%SZ)
```

On first iteration (no prior push), `LAST_PUSH_EPOCH` is the commit timestamp
of the PR-head commit (`git log -1 --format=%ct`).

## GitHub

Fetch all three surfaces in parallel, each with the `since` parameter. Use
the commands from `platform/github.md`:

1. Inline comments → `?since=${SINCE_ISO}` → Surface 1
2. Issue comments → `?since=${SINCE_ISO}` → Surface 2
3. Review submissions (with non-empty body; no `since` param on this endpoint
   — filter by `submitted_at` post-fetch) → Surface 3

Then fetch the GraphQL `reviewThreads` query to get `thread_id` and
`is_resolved` for each inline comment. Join the GraphQL results into the
Surface 1 records by matching `databaseId` with the REST-returned `id`.

## Azure DevOps

Single call: `az repos pr thread list`. Normalize one record per thread-comment
pair. For threads with multiple comments, emit one record per comment;
each record carries the same `thread_id` and `is_resolved`. Filter post-fetch
by `createdDate >= FETCH_SINCE_EPOCH`.

## Output

A flat list of comment records. Store in `context.all_comments` for step 03.
Do not filter here — step 03 applies both the "new since last push" filter
and the actionability filter.

## Caveats

- Bot-reviewer retries and double-posts are common. Keep duplicates in the
  list; step 03's triage de-duplicates by comment text similarity when
  necessary.
- `updated_at` may differ from `created_at` when a reviewer edits a comment.
  Treat the comment as "new" if either epoch value is after
  `context.last_push_timestamp` (also an epoch integer).
