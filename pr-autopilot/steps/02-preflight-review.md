# Step 02 — Preflight adversarial review

Single adversarial Sonnet subagent dispatch. Pass 1 (the 5-reviewer
fan-out) was removed in favor of invoking the host's native code-review
skill post-open (see step 04 sub-step 4g). Post-open review output
flows back through the comment loop.

## Subagent invocation

Follow this procedure:

1. Read `pr-loop-lib/references/adversarial-review-prompt.md`.
2. Render the template by substituting:
   - `{{BASE_SHA}}` → `context.base_sha`
   - `{{HEAD_SHA}}` → `context.head_sha`
   - `{{WHAT_WAS_BUILT}}` → see "What-was-built inference" below
   - `{{INTENT_DOCS}}` → concatenated contents of files in
     `context.spec_candidates` (if any; empty string if none)
   - `{{DIFF}}` → output of `git diff <base_sha>...<head_sha>`
3. Log a `subagent_dispatch` event with `role: "adversarial-reviewer"`,
   `model: "sonnet"`, the first 200 chars of the rendered prompt, and
   `timeout_s: 300`.
4. Dispatch a subagent via the Agent tool with:
   - `subagent_type: "general-purpose"`
   - The rendered prompt as the prompt.
5. Parse the JSON response.
6. Log a `subagent_return` event.
7. Store the parsed findings into
   `context.preflight_passes.pass2_raw`.

## What-was-built inference

Same as the existing behavior — priority order:
1. Current Claude Code session's conversation history (if visible) —
   look for phrases like "implementing", "add support for", "fix",
   "migrate".
2. Branch name (e.g., `pp/ip-restriction-contract-tests` → "IP
   restriction contract tests").
3. Top commit message (first line).

If none are available, ask the user: "What is this PR for?".

## Action policy on findings

- **Critical + Important findings**: fix inline BEFORE step 04 opens the
  PR. Use the loop library's
  `pr-loop-lib/steps/04-dispatch-fixers.md` mechanics. Each finding
  becomes a preflight dispatch unit; dispatch fixer subagents in
  parallel with conflict avoidance.
- **Minor findings**: record in `context.preflight_minor_findings` AND
  append to the local review-summary artifact (see "Review-summary
  artifact" below). **Under β these are NOT folded into the PR body** —
  α's "Known minor observations" section has been removed from the PR
  template per Section 5 of the β spec. Minor findings are visible
  only to the invoking user via the local summary file.

**Invariant scope when reusing 04-dispatch-fixers mechanics.** When
preflight executes the fixer-dispatch procedure from
`pr-loop-lib/steps/04-dispatch-fixers.md`, the applicable post-dispatch
invariants are **`P02.*`** from `pr-loop-lib/references/invariants.md`,
NOT `S04.*`. `S04.*` assume a comment-loop context (triage, actionable
array, assigned PR number) that does not exist at preflight. See the
"Scope" section of `invariants.md` for the rationale. `S04.7` (overlap
re-verify) also does not apply in preflight — preflight dispatch is
single-shot and parallel-fixer overlap is rare enough to not warrant
preflight mirroring in β.

## Post-fix verification

After applying Critical + Important fixes, re-run
`pr-loop-lib/steps/04.5-local-verify.md` to ensure build and tests
still pass. If they fail, apply the same first-failure retry /
second-failure rollback logic described there.

## Merged list

`context.preflight_passes.merged` is populated at this point with
the full finding list (identical to `pass2_raw` since no Pass 1 runs
at preflight). Later, iter 1's triage step may dedup against this
list using Filter B.5's **normalized-lead description hash** from
`pr-loop-lib/steps/03-triage.md` (NOT the category-based key in
`merge-rules.md` — triage items don't carry `category`; see the
"Triage override" section of merge-rules.md).

### Per-finding `description_hash` (for Filter B.5 dedup)

For each finding in `merged`, compute and store a `description_hash`
field using the same normalization that Filter B.5 applies at triage
time, so dedup at iter 1 is a simple equality check over identical
hashes (not a re-normalization round-trip):

1. Take the finding's `description` field (the human-readable summary
   sentence produced by the adversarial reviewer).
2. Strip fenced code blocks (` ``` … ``` `) and HTML tags.
3. Take the lead paragraph — everything up to the first blank line.
4. Lowercase and collapse whitespace to single spaces.
5. Truncate to 200 characters.
6. SHA-1.

Store the resulting hex string as
`context.preflight_passes.merged[].description_hash` (NOT a separate
`preflight_findings[]` — that name doesn't exist in the schema and
would trip G2). Each `merged[]` entry also gets a stable `id` field:
**`preflight-<N>` where `<N>` is the 1-indexed position in the
`pass2_raw` array at first population, never renumbered even if the
skill retries a dispatch**. Deterministic ids let P02.1's predicate
"every `fixer_return.feedback_id` matches a `merged[].id`" be checked
mechanically, and survive `ScheduleWakeup` resumes without drift.

See `pr-loop-lib/steps/03-triage.md#filter-b5` for the receiving-side
normalization — the two must stay in lock-step. Step 04g's internal
`/code-review` dedup (see `04-open-pr.md`) also reads from
`preflight_passes.merged[].description_hash`.

## Review-summary artifact

Under β, the skill writes a markdown summary of every finding it
encountered — from preflight (this step) and from post-open
`/code-review` (step 04g) — to a local file for the invoking user:

```
<repo-root>/.pr-autopilot/pr-<PR>-review-summary.md
```

(Or `branch-<slug>-review-summary.md` before the PR number is
assigned — the state-protocol rename applies to this file alongside
`pr-<PR>.{json,log,lock}`.)

Step 02 is responsible for **creating** this file and populating its
preflight section. Step 04g extends it with the `/code-review`
section.

### When to write

After preflight findings are classified (Critical / Important / Minor)
and **before** dispatching fixers for Critical/Important:

1. Determine the path: `<repo-root>/.pr-autopilot/branch-<slug>-review-summary.md`
   at first invocation (pre-PR-number).
2. Atomically write the initial skeleton (use Primitive C tmp+mv from
   `pr-loop-lib/references/state-protocol.md`):

   ```markdown
   # pr-autopilot internal review summary — <branch>

   Generated by pr-autopilot at <ISO-8601 ts>. This file is local
   (gitignored) and is not visible on the PR.

   ## Preflight adversarial review (Pass 2)

   - Critical: <N> (dispatched for inline fix)
   - Important: <N> (dispatched for inline fix)
   - Minor: <N> (captured; NOT surfaced on PR)

   _Fixer outcomes populated after preflight dispatch completes._
   ```

3. Set `context.internal_review_summary_path` to that path.
4. Dispatch Critical/Important fixers as before.
5. After dispatch completes, append per-finding outcome sections and
   **add an entry to `context.internal_review_findings`** per finding:

   ```json
   { "source": "preflight",
     "severity": "critical" | "important" | "minor",
     "file": "<relative path>",
     "line": <int or null>,
     "description": "<one-line summary>",
     "status": "fixed" | "fixed-differently" | "captured-only" |
               "feedback-wrong" | "needs-human",
     "fixer_feedback_id": "<id>" or null,
     "verifier_judgement": "<addresses|partial|not-addresses|feedback-wrong>" or null
   }
   ```

   `captured-only` is the status for Minor findings (no dispatch
   happened for them).

6. Rewrite the summary section with the populated per-finding bullets
   (see spec Section 5 for the exact markdown format). Use Primitive C
   atomic write again.

### Rename at PR-create time

After step 04's `gh pr create` assigns a `pr_number`, the
state-protocol `state_rename` event renames
`branch-<slug>-review-summary.md` to `pr-<PR>-review-summary.md` as
part of the same rename batch as state/log/lock. Update
`context.internal_review_summary_path` to the new location.

## Failure mode

If the subagent returns malformed JSON or a timeout occurs:
1. Log an `error` event.
2. Treat as a pass with `context.preflight_minor_findings = []` and
   `context.preflight_passes.pass2_raw = []`.
3. Do NOT block the PR — the post-open `/code-review` invocation (step
   04g) will catch issues.

## Invariants

After this step completes, verify (per
`pr-loop-lib/references/invariants.md`):
- `context.preflight_passes.pass2_raw` is set (may be empty).
- `context.preflight_passes.merged` is set (equals `pass2_raw`).
- Every `severity` in the findings is one of `critical`/`important`/`minor`.
