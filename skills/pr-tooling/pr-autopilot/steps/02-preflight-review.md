# Step 02 — Preflight adversarial review

One adversarial Sonnet subagent, plus a playbook checklist agent when
the repo has a review playbook. The host's native `/code-review` runs
after this, still before the PR opens (step 03.5).

**Reviews the post-`/simplify` head.** Step 01.5 runs the quality-only
`/simplify` pass and (on claude-code, committed case) advances
`context.head_sha` to the cleanup commit. The `{{DIFF}}` below therefore
reflects already-simplified code, so the reviewer spends its budget on
correctness rather than complexity churn `/simplify` has already
removed. When step 01.5 was skipped, folded, or rolled back,
`context.head_sha` is whatever it was at step 01 — the diff is still
correct, just not pre-simplified.

## Subagent invocation

Follow this procedure:

1. Write `git diff <base_sha>...<head_sha>` to
   `<repo-root>/.pr-autopilot/branch-<slug>.diff` (the checklist agent
   reads it), then read `pr-loop-lib/references/adversarial-review-prompt.md`.
2. Render the template by substituting:
   - `{{BASE_SHA}}` → `context.base_sha`
   - `{{HEAD_SHA}}` → `context.head_sha`
   - `{{WHAT_WAS_BUILT}}` → see "What-was-built inference" below
   - `{{INTENT_DOCS}}` → concatenated contents of files in
     `context.spec_candidates` (if any; empty string if none)
   - `{{DIFF}}` → output of `git diff <base_sha>...<head_sha>`
   - `{{CONTEXT_MAP}}` → contents of `context.context_map_path` (step
     01.7); empty string when it is null
   - `{{LENS_GUIDANCE}}` → see "Lens guidance rendering" below
3. Log a `subagent_dispatch` event with `role: "adversarial-reviewer"`,
   `model: "sonnet"`, the first 200 chars of the rendered prompt, and
   `timeout_s: 300`.
4. Dispatch a subagent via the Agent tool with:
   - `subagent_type: "general-purpose"`
   - `model: "sonnet"`, passed explicitly
   - The rendered prompt as the prompt.
   In the same message, dispatch the playbook checklist agent (below)
   when it applies, so the two run in parallel.
5. Parse the JSON responses.
6. Log a `subagent_return` event per agent.
7. Store the adversarial findings, then the checklist findings, into
   `context.preflight_passes.pass2_raw`, in that order.

## Playbook checklist

Runs when the repo has a review playbook: `.github/claude-review-instructions.md`
or `.github/copilot-instructions.md`. These hold the rules the repo's
review bots apply, and a single reviewer with many lenses skips most of
them, so one agent answers them one by one.

Dispatch `subagent_type: "pr-reviewer"`, `model: "sonnet"`. Prompt:

```
Check this diff against the repo's review playbook, rule by rule.
Playbook files: <paths>. Other repo rule sources: <CLAUDE.md / AGENTS.md /
ARCHITECTURE.md and .claude/skills review runbooks that exist>.
Diff: <repo-root>/.pr-autopilot/branch-<slug>.diff. Context map: <context_map_path or "none">.

For every rule the playbook lists to always flag, and every convention
it states, decide whether the diff breaks it. Answer only from evidence:
a rule the diff does not touch is skipped, not reported. For each rule
the diff breaks, return one finding citing the diff line and the
playbook line. A rule in an "always flag" list, or marked high
priority, is at least "important".

Return strict JSON in the shape of
pr-loop-lib/references/adversarial-review-prompt.md "Output format",
with "category": "conventions" and the playbook rule quoted at the start
of "description".
```

A malformed or missing reply is logged as an `error` event and
contributes no findings; it never blocks the step.

## Lens guidance rendering

The prompt template's Pass D grades the diff against the `deep-review`
skill's lens register and its backend production tier when that skill is
installed alongside this one.

1. Resolve `~/.claude/skills/deep-review/references/lens-register.md` and
   `~/.claude/skills/deep-review/references/backend-lenses.md`. The two
   resolve independently — either may be absent, and neither absence
   suppresses the other.
2. Decide whether the diff is **backend**: the diff touches SQL or ORM
   bindings or repository-layer code, an HTTP endpoint or route, a GraphQL
   schema/resolver/loader, a message or event handler, a schema migration
   file, or cache access.
3. Collect lens sections from whichever sources resolved. Each contributes
   independently:
   a. **Register present** — take the Universal section plus every pack
      whose stated trigger matches the diff's content. **Register absent**
      — log a `lens_register_missing` event and contribute nothing here.
   b. **Backend diff, tier present** — append the whole of
      `backend-lenses.md`. **Backend diff, tier absent** — log a
      `backend_lenses_missing` event and contribute nothing here. On a
      non-backend diff the tier does not apply: contribute nothing, log
      nothing.
4. **If neither (a) nor (b) contributed**: substitute the empty string for
   `{{LENS_GUIDANCE}}` and move on — Pass D self-skips on an empty block.
   This keeps pr-autopilot fully functional standalone.
5. Otherwise build the precedence preamble, one sentence per contributing
   source, and substitute preamble + collected sections as
   `{{LENS_GUIDANCE}}`:
   a. Locate the repo's own rule sources: `CLAUDE.md` / `AGENTS.md` /
      `ARCHITECTURE.md` at the repo root, the review playbook files
      `.github/claude-review-instructions.md` and
      `.github/copilot-instructions.md`, and any review runbook or
      skill under `.claude/skills/`. Open with: "Repo-defined conventions
      govern everything below this line and are at: <paths>."
   b. When (a) contributed, add: "The lenses below are fallback where the
      repo is silent; universal lenses always apply."
   c. When (b) contributed, add: "Backend production lenses
      (TX/IDM/TEN/CA/MIG/EXP) always apply on a backend diff — a repo rule
      changes what you prescribe, never whether you report; the tier's
      `Not a finding when:` guards are the only suppression rules."

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

Every finding above nit level ends as a fix or a declaration before the
PR opens. A finding listed and left alone is the main reason reviewers
re-raise what our own review already saw.

- **Nit**: `severity: "minor"` and `category: "style"`, and not a lens
  hit (no lens id in the description). Record in
  `context.preflight_minor_findings` and the review summary with status
  `nit`. Not dispatched.
- **Everything else** (Critical, Important, and every other Minor, lens
  hits included): dispatch a fixer BEFORE step 03.5 runs, using the loop
  library's `pr-loop-lib/steps/04-dispatch-fixers.md` mechanics. Each
  finding becomes a preflight dispatch unit; dispatch fixer subagents in
  parallel with conflict avoidance.
- **Code kept** (final fixer verdict `not-addressing` or `replied`; a
  verifier `feedback-wrong` ends as `not-addressing`): status
  `declared`. The fixer's `reply_text` holds the reason. Add a
  `context.declarations[]` entry (schema in `pr-loop-lib/references/context-schema.md`)
  with `kind: "kept-finding"`, the finding's id as `finding_id`, and a
  `statement` that says, in one present-tense sentence, what the code
  does and why it stays. Step 03.5 writes it into a commit message and
  step 04 into the PR body. When the kept code departs from a legacy
  implementation or a sibling service and the code does not show why,
  the fixer adds one line at the departure giving the reason.
- **Undecided** (final verdict `needs-human`, which includes a verifier
  `partial`, or `ui-deferred`): status `needs-human`; step 04 lists it
  under "Open questions for reviewers" in the PR body.

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

After applying preflight fixes, re-run
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
6. SHA-256 (via `sha256sum | cut -c1-64` on Linux/Git-Bash or
   `shasum -a 256 | cut -c1-64` on macOS). Must match the helper used
   in `pr-loop-lib/steps/03-triage.md` Stage 2 — both sides MUST use
   the same algorithm. SHA-1 is not used here because chosen-prefix
   collisions could allow a crafted comment to suppress a preflight finding.

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
normalization — the two must stay in lock-step. Step 03.5's
`/code-review` dedup also reads from
`preflight_passes.merged[].description_hash`.

## Review-summary artifact

Under β, the skill writes a markdown summary of every finding it
encountered — from preflight (this step) and from the pre-open
`/code-review` (step 03.5) — to a local file for the invoking user:

```
<repo-root>/.pr-autopilot/pr-<PR>-review-summary.md
```

(Or `branch-<slug>-review-summary.md` before the PR number is
assigned — the state-protocol rename applies to this file alongside
`pr-<PR>.{json,log,lock}`.)

Step 02 is responsible for **creating** this file and populating its
preflight section. Step 03.5 extends it with the `/code-review` and
fix-round sections.

### When to write

After preflight findings are classified (Critical / Important / Minor /
nit) and **before** dispatching fixers:

1. Determine the path: `<repo-root>/.pr-autopilot/branch-<slug>-review-summary.md`
   at first invocation (pre-PR-number).
2. Atomically write the initial skeleton (use Primitive C tmp+mv from
   `pr-loop-lib/references/state-protocol.md`):

   ```markdown
   # pr-autopilot internal review summary — <branch>

   Generated by pr-autopilot at <ISO-8601 ts>. This file is local
   (gitignored) and is not visible on the PR.

   ## Preflight adversarial review (Pass 2)

   - Critical: <N> (dispatched)
   - Important: <N> (dispatched)
   - Minor: <N> (dispatched)
   - Nit: <N> (captured only)

   _Fixer outcomes populated after preflight dispatch completes._
   ```

3. Set `context.internal_review_summary_path` to that path.
4. Dispatch fixers for every finding that is not a nit.
5. After dispatch completes, append per-finding outcome sections and
   **add an entry to `context.internal_review_findings`** per finding:

   ```json
   { "source": "preflight",
     "severity": "critical" | "important" | "minor",
     "file": "<relative path>",
     "line": <int or null>,
     "description": "<one-line summary>",
     "status": "fixed" | "fixed-differently" | "nit" | "declared" |
               "needs-human" | "duplicate",
     "fixer_feedback_id": "<id>" or null,
     "verifier_judgement": "<addresses|partial|not-addresses|feedback-wrong>" or null
   }
   ```

   `nit` is the only status for a finding that was not dispatched.
   `declared` always has a matching `context.declarations[]` entry.

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
3. Do NOT block the PR — step 03.5's `/code-review` still runs.

## Invariants

After this step completes, verify (per
`pr-loop-lib/references/invariants.md`):
- `context.preflight_passes.pass2_raw` is set (may be empty).
- `context.preflight_passes.merged` is set (equals `pass2_raw`).
- Every `severity` in the findings is one of `critical`/`important`/`minor`.
