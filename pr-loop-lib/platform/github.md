# Platform: GitHub

All loop-library steps call into this file when `context.platform == "github"`.

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

```bash
gh api graphql -f query='
query($owner: String!, $repo: String!, $pr: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
          isOutdated
          comments(first: 50) {
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
```

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
