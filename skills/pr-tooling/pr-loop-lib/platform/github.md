# Platform: GitHub

All loop-library steps call into this file when `context.platform == "github"`.

## Webhook activity subscription

Used by `pr-loop-lib/steps/01-wait-cycle.md` (subscribe) and
`pr-loop-lib/steps/11-final-report.md` (unsubscribe).

### Subscribe (step 01, Mode W)

```
mcp__github__subscribe_pr_activity(
  owner      = <owner>,
  repo       = <repo>,
  pullNumber = <pr_number>
)
```

Idempotent. Delivers `<github-webhook-activity>` messages into the
current conversation whenever a review comment, issue comment, review
submission, or CI check event occurs on the PR. The session does not
need to poll — events arrive in-band and trigger Mode E in step 01.

### Unsubscribe (step 11, before lock release)

```
mcp__github__unsubscribe_pr_activity(
  owner      = <owner>,
  repo       = <repo>,
  pullNumber = <pr_number>
)
```

Idempotent. Stops further webhook deliveries for this PR. Called once
the skill terminates so stale events do not arrive into a subsequent
unrelated session.

Use the "Owner / repo extraction" snippet below to populate `$OWNER`
and `$REPO` before calling either tool.

---

## Detection

```bash
remote=$(git remote get-url origin)
case "$remote" in
  *github.com*) platform=github ;;
  *dev.azure.com*|*visualstudio.com*) platform=azdo ;;
  *) platform=github ;;   # default fallback, with a warning
esac
```

## Operations

### Fetch inline review comments (Surface 1)

```bash
gh api "repos/{owner}/{repo}/pulls/${PR}/comments" --paginate --jq '[
  .[] | {
    id,
    surface: "inline",
    author: .user.login,
    author_type: .user.type,
    created_at,
    updated_at,
    path,
    line,
    body,
    pull_request_review_id
  }
]'
```

### Fetch top-level PR comments (Surface 2)

```bash
gh api "repos/{owner}/{repo}/issues/${PR}/comments" --paginate --jq '[
  .[] | {
    id,
    surface: "issue",
    author: .user.login,
    author_type: .user.type,
    created_at,
    updated_at,
    body
  }
]'
```

### Fetch review submissions (Surface 3)

```bash
gh api "repos/{owner}/{repo}/pulls/${PR}/reviews" --paginate --jq '[
  .[] | select(.body | length > 0) | {
    id,
    surface: "review",
    author: .user.login,
    author_type: .user.type,
    submitted_at,
    state,
    body
  }
]'
```

### Fetch thread IDs + resolved state (GraphQL)

Needed for the resolve mutation. Posts and replies use REST; resolution uses GraphQL.

Both connections (`reviewThreads` and each thread's `comments`) must be
paginated via `pageInfo { hasNextPage, endCursor }`. GitHub caps a single
page at 100 for both connections; the query below requests the maximum
(`first: 100` for threads, `first: 50` for comments — 50 is a safe default
under typical per-query cost limits, raise to 100 if you know the PRs
you're querying have many comments per thread). PRs with more threads or
any thread with more comments than the requested page size require
repeated queries until `hasNextPage` is false. Do not skip the loop; a
missing `thread_id` for a single inline comment silently breaks the
resolve step for that thread.

```bash
# First page: omit the cursor variable so $threadsCursor is null.
# (Passing an empty string is NOT valid — GraphQL rejects "" as a cursor.)
gh api graphql -f query='
query($owner: String!, $repo: String!, $pr: Int!, $threadsCursor: String) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      reviewThreads(first: 100, after: $threadsCursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          isResolved
          isOutdated
          comments(first: 50) {
            pageInfo { hasNextPage endCursor }
            nodes {
              id
              databaseId
              author { login }
              body
              path
              line
              createdAt
            }
          }
        }
      }
    }
  }
}
' -f owner="$OWNER" -f repo="$REPO" -F pr="$PR"

# Subsequent pages: pass the endCursor from the previous response:
#   -f threadsCursor="<endCursor from last reviewThreads.pageInfo>"
```

If any returned thread reports `comments.pageInfo.hasNextPage == true`,
re-query that single thread by node ID with a `comments(first: 50, after: $commentsCursor)`
sub-query until the per-thread pagination also completes. Merge the
resulting comment lists client-side.

### Reply to an inline thread (GraphQL mutation)

```bash
gh api graphql -f query='
mutation($threadId: ID!, $body: String!) {
  addPullRequestReviewThreadReply(input: {
    pullRequestReviewThreadId: $threadId,
    body: $body
  }) {
    comment { id }
  }
}
' -f threadId="$THREAD_ID" -f body="$REPLY_TEXT"
```

### Resolve a thread (GraphQL mutation)

```bash
gh api graphql -f query='
mutation($threadId: ID!) {
  resolveReviewThread(input: { threadId: $threadId }) {
    thread { isResolved }
  }
}
' -f threadId="$THREAD_ID"
```

### Post a top-level PR reply (Surfaces 2 + 3)

```bash
gh pr comment "$PR" --body "$REPLY_TEXT"
```

(There is no per-top-level-comment "resolve" API on GitHub. Posting a reply is
the only mechanism.)

### CI gate

```bash
gh pr checks "$PR" --watch --fail-fast=false
```

Blocks until all checks report final status. Returns non-zero on any failure.
Output is human-readable; parse with:

```bash
gh pr checks "$PR" --json name,state,link --jq '[.[] | {name, state, link}]'
```

### Re-run a failed check

```bash
gh run rerun "$RUN_ID"
```

(`RUN_ID` comes from the `link` field in the pr-checks JSON.)

### PR state / merge status

```bash
gh pr view "$PR" --json state,mergeStateStatus,headRefOid,baseRefName
```

### Create a PR

```bash
gh pr create --title "$TITLE" --body "$(cat /tmp/pr-body.md)" --base "$BASE"
```

## Owner / repo extraction

```bash
OWNER_REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
OWNER=${OWNER_REPO%%/*}
REPO=${OWNER_REPO##*/}
```

## PR number detection (from current branch)

```bash
PR=$(gh pr view --json number --jq .number 2>/dev/null || echo "")
```

Empty result means no PR for this branch — that is the normal state for
pr-autopilot first run.
