# Context schema

Single source of truth for every `context.*` field referenced across the
skill. Every step file reads this before reading or writing state; every
state write must use values that match the schema.

The state file lives at `<repo-root>/.pr-autopilot/pr-<PR>.json`. Its top
level keys match the field names below. Unknown keys MUST NOT be written.
Required fields are marked as such.

## Identity / environment

| Field | Type | Required | Allowed values / description |
|---|---|---|---|
| `session_id` | string (UUID) | yes | Generated once at skill entry; constant across ScheduleWakeup wakes |
| `host_platform` | enum | yes | `claude-code` \| `codex` \| `gemini` \| `other` |
| `platform` | enum | yes | `github` \| `azdo` |
| `repo_root` | string (absolute path) | yes | From `git rev-parse --show-toplevel` |
| `base` | string | yes | Base branch (e.g., `main`) |
| `branch` | string | yes | Current branch |
| `head_sha` | string (hex) | yes | `git rev-parse HEAD` |
| `base_sha` | string (hex) | yes | `git merge-base $base HEAD` |
| `pr_number` | integer or null | no | Set by step 01 if PR exists, else after step 04 |
| `pr_url` | string or null | no | PR URL, set after create |
| `template_path` | string or null | no | Repo's PR-template path, if found |
| `self_login` | string or null | yes after step 01 | Invoking user's login (from `gh api user --jq .login`) |
| `uncommitted` | array of strings | default `[]` | `git status --porcelain` paths |
| `spec_candidates` | array of strings | default `[]` | Globbed spec/plan file paths |

## Preflight (step 02) output

| Field | Type | Required | Description |
|---|---|---|---|
| `what_was_built` | string or null | no | Inferred intent summary |
| `preflight_minor_findings` | array of objects | default `[]` | Minor findings folded into PR body |
| `preflight_passes` | object | default `{}` | `{pass2_raw: [...], merged: [...]}` |
| `spec_updates` | array of objects | default `[]` | Spec file edits made by step 03 |
| `blocked_drifts` | array of objects | default `[]` | Drifts that caused HALT before PR open |
| `spec_alignment_notes` | array of strings | default `[]` | Human-readable notes for PR body |

## Loop runtime state

| Field | Type | Required | Description |
|---|---|---|---|
| `iteration` | integer | default `0` | Current loop iteration (1-indexed once loop starts) |
| `user_iteration_cap` | integer | default `10` | Cap from skill argument |
| `no_wait_first_iteration` | boolean | default `false` | Set by pr-followup |
| `wait_override_minutes` | integer or null | no | From `--wait N` |
| `last_push_timestamp` | string (ISO-8601) or null | no | Committer timestamp of most recent push |
| `last_handled_timestamp` | string (ISO-8601) or null | no | Set by step 08 after suspicious-only iterations |
| `last_push_sha` | string (hex) or null | no | HEAD SHA after most recent push |
| `all_comments` | array of objects | default `[]` | From step 02 (loop); per CommentRecord schema below |
| `actionable` | array of objects | default `[]` | Step 03 output for dispatch |
| `suspicious_items` | array of objects | default `[]` | Step 03 output for refusal replies |
| `agent_returns` | array of objects | default `[]` | Step 04 fixer returns (per AgentReturn schema) |
| `verifier_judgements` | array of objects | default `[]` | Step 04 verifier outputs, one per verified fixer return |
| `files_changed_this_iteration` | array of strings | default `[]` | Union of fixer file changes |
| `needs_human_items` | array of objects | default `[]` | Items flagged for user attention |
| `sanity_check_passed` | object | default `{}` | `{ <iteration>: <bool> }` |

## CI gate

| Field | Type | Required | Description |
|---|---|---|---|
| `ci_results` | array of objects | default `[]` | Per-check `{name, state, link, raw_state, extra}` |
| `ci_reentry_count` | integer | default `0` | Max 3 |

## Termination

| Field | Type | Required | Description |
|---|---|---|---|
| `loop_exit_reason` | enum or null | no | `quiescent-zero-actionable` \| `quiescent-no-code-change` \| `iteration-cap` \| `runaway-detected` |
| `termination_reason` | enum or null | no | `ci-green` \| `ci-red` \| `ci-skipped` \| `ci-timeout` \| `ci-reentry-cap` \| `ci-pre-existing-failures` \| `iteration-cap` \| `runaway-detected` \| `user-intervention-needed` |
| `code_review_invoked` | boolean | default `false` | True after `/code-review` fires |
| `code_review_invoked_at` | string (ISO-8601) or null | no | When `/code-review` was dispatched |

## Nested schemas

### CommentRecord (used in `all_comments`, `actionable`, `suspicious_items`)

```json
{
  "id": "string (unique within surface)",
  "surface": "inline | issue | review | thread",
  "author": "string (login or display name)",
  "author_type": "User | Bot",
  "created_at": "ISO-8601 string",
  "updated_at": "ISO-8601 string or null",
  "path": "string or null",
  "line": "integer or null",
  "body": "string",
  "thread_id": "string or null",
  "is_resolved": "boolean or null"
}
```

### AgentReturn (used in `agent_returns`)

```json
{
  "verdict": "fixed | fixed-differently | replied | not-addressing | needs-human",
  "feedback_id": "string",
  "feedback_type": "inline | issue | review | thread",
  "reply_text": "string (markdown)",
  "files_changed": "array of strings (relative paths)",
  "reason": "string (one sentence)",
  "suspicious": "boolean (default false)",
  "cluster_assessment": "string or null"
}
```

### VerifierJudgement (used in `verifier_judgements`)

```json
{
  "feedback_id": "string",
  "fixer_verdict_before": "fixed | fixed-differently",
  "fixer_verdict_after": "fixed | fixed-differently | replied | not-addressing | needs-human",
  "judgement": "addresses | partial | not-addresses | feedback-wrong",
  "reason": "string",
  "dispatched_at": "ISO-8601 string"
}
```

## Validation rules (applied by the LLM on every write)

1. Every field value must match the Type column.
2. Every enum value must be in the Allowed values list.
3. No unknown top-level keys may appear in the state file.
4. Required fields must be present (non-null where Type disallows null).
5. Timestamps are UTC ISO-8601 with second precision, e.g. `2026-04-18T07:44:32Z`.

Violations are errors, not warnings. The step that detects a violation
must halt with an `invariant_fail` event (see `invariants.md`).
