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
| `effort_docs` | array of strings | default `[]` | Absolute paths of intent docs kept outside the repo (step 01 "Effort docs"). Read as data by steps 01.7, 02 and 03.5; never edited, staged or aligned against. |

## Pre-review simplify (step 01.5) output

`pr-autopilot` only. Written by `pr-autopilot/steps/01.5-simplify.md`
before any internal review. Absent on `pr-followup` runs (which never
run `/simplify`).

| Field | Type | Required | Description |
|---|---|---|---|
| `simplify_outcome` | enum or null | default `null` | `committed` \| `folded` \| `no-changes` \| `rolled-back` \| `skipped`. Result of the pre-review `/simplify` pass; `null` when the step has not run (e.g. on `pr-followup`, which never runs it). `committed`: cleanup committed separately and `head_sha` advanced. `folded`: edits left in the tree to be committed by step 03.5 A (uncommitted work overlapped). `skipped`: non-claude-code host or empty range. |
| `simplify_files` | array of strings | default `[]` | Relative paths `/simplify` touched. On the fold path these are also merged into `uncommitted` so step 03.5 A stages them. |
| `simplify_skipped` | array of objects | default `[]` | Points `/simplify` saw and did not apply because they change behaviour: `{file, line, summary, reason}`. Step 03.5 D turns each into a candidate finding `simplify-N`. |

## Context map (step 01.7) output

`pr-autopilot` only.

| Field | Type | Required | Description |
|---|---|---|---|
| `context_map_path` | string or null | default `null` | Path to `<repo-root>/.pr-autopilot/branch-<slug>-context-map.md`. `null` when step 01.7 wrote no usable map. Not renamed at PR create. |
| `context_map_sources` | array of strings | default `[]` | Sources the context mapper read: `workspace-map`, `api-catalog`, `sibling-repos`, `new-relic`, `effort-docs`. |
| `context_map_checks` | array of objects | default `[]` | Every check the map raises: `{id, text}`, ids `C1`, `C2`, ... as written in the map. |
| `context_check_answers` | array of objects | default `[]` | The step 02 context agent's answer to each check: `{id, answer: "yes" \| "no" \| "cannot-tell", evidence, reason}`. One per `context_map_checks` id. A `yes` has a finding with that `check_id`. |

## Lens review (step 02, launched in step 03.5) and spec alignment output

| Field | Type | Required | Description |
|---|---|---|---|
| `what_was_built` | string or null | no | Inferred intent summary, set by step 01.7 |
| `preflight_minor_findings` | array of objects | default `[]` | Nit findings (`severity: "minor"`, `category: "style"`, no lens id), recorded in the local review summary and never dispatched. Every other Minor finding is dispatched. |
| `preflight_passes` | object | default `{}` | `{pass2_raw: [...], merged: [...]}`. `pass2_raw`: every lens agent's findings in the fixed agent order, each with `id` (`preflight-N`) and `agent`. `merged`: the same list with cross-agent duplicates folded into the lower id, which lists them in `duplicate_ids`. A finding may carry `declared_risk`, `settled_item` and `check_id`. |
| `lens_agents` | array of objects | default `[]` | The step 02 agents for this run, in dispatch order: `{name, status: "pending" \| "done" \| "failed"}`. `name` is `context`, `pack:<name>`, `backend` or `universal`. |
| `spec_updates` | array of objects | default `[]` | Spec file edits made by step 03 |
| `blocked_drifts` | array of objects | default `[]` | Drifts that caused HALT before PR open |
| `spec_alignment_notes` | array of strings | default `[]` | Human-readable notes for PR body |

## Loop runtime state

| Field | Type | Required | Description |
|---|---|---|---|
| `iteration` | integer | default `0` | Current loop iteration (1-indexed once loop starts) |
| `user_iteration_cap` | integer | default `10` | Cap from skill argument |
| `no_wait_first_iteration` | boolean | default `false` | Set by pr-followup |
| `wait_override_minutes` | integer or null | no | From `--wait N`. Interpreted as `max(5, N)` by `pr-loop-lib/steps/01-wait-cycle.md` — the 5-minute floor applies to the *effective* delay, not the raw user input. Values below 5 are accepted at parse time but clamped up in step 01 with a warning log event. The floor's reduction from 10 to 5 minutes is paired with the two-consecutive-quiescent-iteration exit rule in step 08, which together preserve the original ~10-minute wall-clock window for late-arriving reviewer-bot comments. |
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
| `ui_deferred_items` | array of objects | default `[]` | Items the fixer judged to be UI / design / copy changes; deferred to end-of-run user approval. Each entry: `{feedback_id, thread_id?, path?, line?, author, body, proposal, reply_text}`. Step 11 prompts the user and may re-enter step 04 scoped to approved items. |
| `ui_deferred_actionable` | array of objects | default `[]` | Scoped overlay written by step 11 before re-dispatching approved `ui_deferred_items`. During that one step-04 invocation, the dispatcher reads its actionable list from this field in place of `context.actionable`. Never replaces `context.actionable`; the persisted top-level `actionable` is left unchanged. Same shape as the individual items in `context.actionable`. |
| `consecutive_quiescent_iterations` | integer | default `0` | Incremented on each soft-quiescent iteration (`quiescent-zero-actionable` or `quiescent-no-code-change`). Reset to `0` on any non-quiescent iteration outcome. Read by step 08 to decide between routing back to step 01 (counter == 1) or onward to step 09 (counter >= 2). |
| `last_quiescence_reason` | enum or null | default `null` | The most recent soft-quiescent reason; one of `quiescent-zero-actionable` \| `quiescent-no-code-change`. Set on each soft-quiescent iteration (in lockstep with `consecutive_quiescent_iterations` increment). Cleared (set to `null`) when the counter resets. Carried for the report and for log readability. |
| `sanity_check_passed` | object | default `{}` | `{ <iteration>: <bool> }` |

## CI gate

| Field | Type | Required | Description |
|---|---|---|---|
| `ci_results` | array of objects | default `[]` | Per-check `{name, state, link, raw_state, extra}` |
| `ci_reentry_count` | integer | default `0` | Max 3 |

## Termination

| Field | Type | Required | Description |
|---|---|---|---|
| `loop_exit_reason` | enum or null | no | `quiescent-confirmed` \| `iteration-cap` \| `runaway-detected`. The two old soft-quiescent values (`quiescent-zero-actionable`, `quiescent-no-code-change`) were removed in 2026-05-06; they no longer cause a loop exit on their own — they are recorded on `last_quiescence_reason` (above) on the first quiescent iteration, and the loop continues. Only the second consecutive quiescent iteration writes `loop_exit_reason = quiescent-confirmed` and exits. State files written by older skill versions may contain the removed values; that is expected — schema validation runs at write time, not on every read. |
| `termination_reason` | enum or null | no | `ci-green` \| `ci-red` \| `ci-skipped` \| `ci-timeout` \| `ci-reentry-cap` \| `ci-pre-existing-failures` \| `iteration-cap` \| `runaway-detected` \| `user-intervention-needed` |
| `code_review_invoked` | boolean | default `false` | True after pr-autopilot step 03.5 invokes `/code-review`. Its output is kept locally and never posted. |
| `code_review_invoked_at` | string (ISO-8601) or null | no | When `/code-review` was dispatched |
| `code_review_status` | enum or null | default `null` | `running` \| `done` \| `skipped`. `running` while step 03.5 waits for the background result; step 04 never starts while it is `running`. |
| `code_review_raw_output` | string | default `""` | Result text of the host's `code-review` skill, parsed by step 03.5. Never posted. |
| `code_review_dismissed` | array of objects | default `[]` | Candidates `/code-review` refuted or dropped: `{summary, reason}`. Re-checked by step 03.5's fix-round review. |
| `fix_round_base_sha` | string (hex) or null | no | HEAD before step 03.5's fix commit; the base of the fix-round review diff. Under `--dry-run`, the id of the snapshot tree taken before the fixers ran. |
| `fix_round_head_tree` | string (hex) or null | default `null` | `--dry-run` only: the snapshot tree taken after the fixers ran; the head of the fix-round review diff. |
| `declarations` | array of objects | default `[]` | Decisions kept on purpose, written into commit messages (step 03.5) and the PR body (step 04). Each entry: `{kind: "kept-finding" \| "difference" \| "scope", statement, file?, line?, finding_id?, in_commit}`. `statement` is one present-tense sentence. `in_commit` is the SHA of the commit whose message carries it. |
| `internal_review_findings` | array of objects | default `[]` | Per-finding audit trail for the local review summary. Each entry: `{source: "preflight" \| "code-review" \| "simplify" \| "fix-round", severity, file, line?, description, status: "fixed" \| "fixed-differently" \| "nit" \| "declared" \| "needs-human" \| "duplicate" \| "captured-only" \| "feedback-wrong", fixer_feedback_id?, verifier_judgement?, declared_risk?, settled_item?}`. `nit` findings, and findings with `declared_risk: true` (status `needs-human`, the settled choice stays the author's call), are the only ones left undispatched. `captured-only` and `feedback-wrong` are legacy values: step 03.5 never writes them, and validation accepts them so `/pr-followup` can load and rewrite state files from older skill versions. |
| `internal_review_summary_path` | string or null | no | Path to the markdown summary file at `<repo-root>/.pr-autopilot/pr-<PR>-review-summary.md` (or `branch-<slug>-review-summary.md` pre-PR-assignment). Set in step 03.5 when the lens agent returns; renamed by state-protocol at PR-create time alongside the other branch-* files. |

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
  "verdict": "fixed | fixed-differently | replied | not-addressing | needs-human | ui-deferred",
  "feedback_id": "string",
  "feedback_type": "inline | issue | review | thread",
  "reply_text": "string (markdown)",
  "files_changed": "array of strings (relative paths)",
  "reason": "string (one sentence)",
  "suspicious": "boolean (default false)",
  "cluster_assessment": "string or null"
}
```

`ui-deferred` is never emitted with a non-empty `files_changed`. Step
04's validation rolls back and demotes to `needs-human` if a fixer
violates this.

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

`fixer_verdict_after` does NOT include `ui-deferred`: verification
only runs when the fixer originally edited files (verdict `fixed` or
`fixed-differently`), so the policy ladder can never land on
`ui-deferred` post-hoc.

## Validation rules (applied by the LLM on every write)

1. Every field value must match the Type column.
2. Every enum value must be in the Allowed values list.
3. No unknown top-level keys may appear in the state file.
4. Required fields must be present (non-null where Type disallows null).
5. Timestamps are UTC ISO-8601 strings ending in `Z`, with second
   precision OR fractional-second precision (milli/microseconds).
   Accepted forms: `2026-04-18T07:44:32Z`, `2026-04-18T07:44:32.123Z`,
   `2026-04-18T07:44:32.123456Z`. Platform normalizers (e.g.,
   `pr-loop-lib/platform/azdo.md`) may leave source precision intact
   rather than truncating — validators accept either.

Violations are errors, not warnings. The step that detects a violation
must halt with an `invariant_fail` event (see `invariants.md`).
