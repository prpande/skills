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
  becomes an actionable item; dispatch fixer subagents in parallel
  with conflict avoidance.
- **Minor findings**: record in `context.preflight_minor_findings`.
  Step 04 folds them into the PR body as a "Known minor observations"
  bullet list.

## Post-fix verification

After applying Critical + Important fixes, re-run
`pr-loop-lib/steps/04.5-local-verify.md` to ensure build and tests
still pass. If they fail, apply the same first-failure retry /
second-failure rollback logic described there.

## Merged list

`context.preflight_passes.merged` is populated at this point with
the full finding list (identical to `pass2_raw` since no Pass 1 runs
at preflight). Later, iter 1's triage step may dedup against this
list per `pr-loop-lib/references/merge-rules.md` when `/code-review`'s
output arrives.

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
