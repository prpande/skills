# Invariants

Finite list of post-step assertions the LLM checks at the end of each
step. Every invariant is a short, deterministic rule. Violations halt
the skill with an `invariant_fail` event logged.

## Why this file exists

Without a runtime schema validator, drift between steps is hard to
detect. Invariants are a defense-in-depth layer — short enough that the
LLM can hold them in working memory and mechanical enough that
evaluation is not judgement-dependent.

Each invariant identifies the step that owns it and the exact predicate.

## Global invariants (checked after every state write)

| # | Predicate | Failure mode if violated |
|---|---|---|
| G1 | `session_id` in state matches `session_id` in lock file | Lock was reclaimed; halt |
| G2 | Every top-level key in state is documented in `context-schema.md` | Unknown key; halt |
| G3 | Every enum field's value is in the schema's Allowed values list | Bad enum value; halt |
| G4 | `last_push_timestamp` never goes backwards between consecutive updates | Clock skew or logic bug; halt |
| G5 | `iteration` never decreases | Logic bug; halt |

## Per-step invariants

### Step 01 — detect-context (pr-autopilot)

| # | Predicate |
|---|---|
| S01.1 | `context.branch` is not `main`/`master` (for pr-autopilot; pr-followup allows any branch) |
| S01.2 | `context.platform` is one of `github`/`azdo` |
| S01.3 | `context.host_platform` is set to one of the 4 enum values |
| S01.4 | `context.self_login` is a non-empty string |
| S01.5 | `context.base_sha != context.head_sha` (diff exists) — warn-only, not halt |

### Step 03 — triage

| # | Predicate |
|---|---|
| S03.1 | `len(actionable) + len(suspicious) + dropped_count == len(all_comments)` where `dropped_count` is an integer total tracked via log event `triage_result.filtered_*` fields |
| S03.2 | No comment appears in both `actionable` and `suspicious` |
| S03.3 | Every item in `actionable` has `body` set (non-empty) |
| S03.4 | Every item in `suspicious` has a `matched_refusal_class` field (from filter C) |

### Step 04 — dispatch-fixers

| # | Predicate |
|---|---|
| S04.1 | `len(agent_returns) == len(dispatch_units)` where dispatch_units is clusters + individual items |
| S04.2 | Every return's `verdict` is one of the 5 allowed values |
| S04.3 | Every return with verdict `fixed` or `fixed-differently` has a corresponding entry in `verifier_judgements` |
| S04.4 | `files_changed_this_iteration` equals the union of `files_changed` across all returns |
| S04.5 | No file in `files_changed_this_iteration` has a path outside `context.repo_root` |

### Step 04.5 — local-verify

| # | Predicate |
|---|---|
| S045.1 | If `files_changed_this_iteration` is non-empty, `sanity_check_passed[iteration]` is set (true or false) — absence is a bug |
| S045.2 | If the rollback branch executed, `files_changed_this_iteration` is now empty |

### Step 06 — commit-push

| # | Predicate |
|---|---|
| S06.1 | If `last_push_sha` was updated in this step, `last_push_timestamp` was also updated |
| S06.2 | `last_push_sha` equals the output of `git rev-parse HEAD` after the push |
| S06.3 | Commit message does NOT contain `-c commit.gpgsign=false` or `--no-verify` (the commit itself didn't use those flags) |

### Step 08 — quiescence-check

| # | Predicate |
|---|---|
| S08.1 | `loop_exit_reason` is set to exactly one of the 4 enum values |
| S08.2 | If `loop_exit_reason` ∈ {`iteration-cap`, `runaway-detected`}, `termination_reason` is also set (to the matching value) |
| S08.3 | If `loop_exit_reason` ∈ {`quiescent-*`}, routing goes to step 09 (not step 11 directly) |

### Step 09 — ci-gate

| # | Predicate |
|---|---|
| S09.1 | Every entry in `ci_results` has `state` ∈ {`green`, `red`, `pending-timeout`} |
| S09.2 | If all entries have `state: green`, `termination_reason` is set to `ci-green` |

### Step 10 — ci-failure-classify

| # | Predicate |
|---|---|
| S10.1 | `ci_reentry_count <= 3` |
| S10.2 | If `ci_reentry_count == 3` after this step, `termination_reason` is set to `ci-reentry-cap` |

### Step 11 — final-report

| # | Predicate |
|---|---|
| S11.1 | `termination_reason` is set |
| S11.2 | Lock file has been removed by the time this step completes |

## How to check an invariant

At the end of any step, after the state write:
1. Load the relevant invariants for this step from this file.
2. Evaluate each predicate against current state.
3. If any fails:
   - Emit log event:
     ```json
     {"event": "invariant_fail", "data": {
       "step": "<step-name>",
       "invariant": "<id, e.g. S03.2>",
       "observed": "<what was true>",
       "expected": "<what the invariant required>"
     }}
     ```
   - Halt the skill with a diagnostic referencing the invariant id.
4. If all pass, proceed to the next step.

## Adding invariants

When introducing new fields or new steps, append rows to the appropriate
table. Keep each predicate:
- **Local** — checkable from the current state + this step's outputs, no
  need to look at step N-5's logs.
- **Mechanical** — boolean evaluation, not judgement.
- **Cheap** — doesn't require re-fetching data from GitHub or re-running
  anything expensive.
