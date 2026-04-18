# Platform: Azure DevOps

All loop-library steps call into this file when `context.platform == "azdo"`.

## Detection

Same as `github.md` but matching `dev.azure.com` or `visualstudio.com` in the
remote URL.

## Surface model

Azure DevOps does not split comments into three surfaces like GitHub.
Every comment is part of a **thread** on the PR. Each thread has a
status (`active`, `closed`, `fixed`, `wontFix`, `pending`) which is the
resolve-state equivalent.

## Operations

### Fetch all threads + comments

```bash
az repos pr thread list \
  --pull-request-id "$PR" \
  --output json
```

(Or via the AzDO MCP tool: `repo_list_pull_request_threads`.)

The response shape (simplified):
```json
[
  {
    "id": 123,
    "status": "active",
    "threadContext": { "filePath": "/src/foo.cs", "rightFileStart": { "line": 42 } },
    "comments": [
      {
        "id": 1,
        "author": { "uniqueName": "bot@mindbody.com", "displayName": "Copilot" },
        "content": "comment body",
        "publishedDate": "...",
        "commentType": "text"
      }
    ]
  }
]
```

Normalize to the unified schema:
```
{ id: $thread.id,
  surface: "thread",
  author: $comment.author.displayName,
  author_type: ($comment.author.isBot ? "Bot" : "User"),
  created_at: $comment.publishedDate,
  path: $thread.threadContext.filePath,
  line: $thread.threadContext.rightFileStart.line,
  body: $comment.content,
  thread_id: $thread.id,
  is_resolved: ($thread.status != "active" && $thread.status != "pending") }
```

### Reply to a thread

```bash
az repos pr thread comment add \
  --pull-request-id "$PR" \
  --thread-id "$THREAD_ID" \
  --content "$REPLY_TEXT"
```

(AzDO MCP equivalent: `repo_reply_to_comment`.)

### Resolve a thread

```bash
az repos pr thread update \
  --pull-request-id "$PR" \
  --thread-id "$THREAD_ID" \
  --status closed
```

(AzDO MCP equivalent: `repo_update_pull_request_thread`.)

### CI gate

AzDO CI runs on pipelines. Poll the latest run per pipeline associated with
the PR branch:

```bash
BRANCH=$(git rev-parse --abbrev-ref HEAD)
az pipelines runs list \
  --branch "$BRANCH" \
  --status completed \
  --top 50 \
  --output json
```

(MCP: `pipelines_list_runs`.)

Collapse to latest run per `definition.id`. Red check = any latest-run
`result` != `succeeded` (values: `succeeded`, `failed`, `canceled`,
`partiallySucceeded`).

### Re-run a pipeline

```bash
az pipelines runs create \
  --pipeline-id "$PIPELINE_ID" \
  --branch "$BRANCH"
```

(MCP: `pipelines_run_pipeline`.)

### PR state

```bash
az repos pr show --id "$PR" --output json
```

Check `.status` for `active` vs `completed` (merged) vs `abandoned`.

### Create a PR

```bash
az repos pr create \
  --title "$TITLE" \
  --description "$(cat /tmp/pr-body.md)" \
  --source-branch "$BRANCH" \
  --target-branch "$BASE"
```

(MCP: `repo_create_pull_request`.)

## PR number detection (from current branch)

```bash
BRANCH=$(git rev-parse --abbrev-ref HEAD)
PR=$(az repos pr list --source-branch "$BRANCH" --status active --output json \
     | jq -r '.[0].pullRequestId // empty')
```

## Organization / project / repo discovery

AzDO commands need `--organization`, `--project`, and `--repository`. The
`az` CLI's default config (from `az devops configure --defaults`) is
preferred; the orchestrator reads `git remote get-url origin` to extract
them as a fallback:

```bash
# Remote looks like: https://dev.azure.com/{org}/{project}/_git/{repo}
remote=$(git remote get-url origin)
ORG=$(echo "$remote" | sed -E 's|https://dev\.azure\.com/([^/]+)/.*|\1|')
PROJECT=$(echo "$remote" | sed -E 's|https://dev\.azure\.com/[^/]+/([^/]+)/.*|\1|')
REPO=$(echo "$remote" | sed -E 's|.*/_git/([^/]+).*|\1|')
```
