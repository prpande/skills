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

## Scope

Invariants are partitioned by the scope in which they are valid. A step
must cite invariants only from its applicable scope; citing an
out-of-scope invariant is itself a bug.

- **`G*`** — Global. Checked after every state write in every step.
- **`SNN.*`** — Step-scoped. Each table below is keyed by the step that
  owns it (e.g., `S01.*` for step 01 of pr-autopilot, `S03.*` for the
  loop's triage step). A step cites only its own `SNN.*` invariants
  plus any global `G*`.
- **`P02.*`** — Preflight-dispatch scope. Applicable in
  `pr-autopilot/steps/02-preflight-review.md` **when preflight performs
  fixer dispatch to address its findings** (mirroring the loop's
  `S04.*`, but for preflight's `preflight_findings[]` rather than the
  loop's `actionable[]`).

**Important cross-scope rule:** Preflight MUST NOT cite `S04.*`. The
post-dispatch predicates in `S04.*` bake in assumptions — keyed off
`feedback_id` from triage, referring to `actionable[]`, depending on an
assigned `pr_number` — that do not hold at preflight. Preflight's
equivalent predicates live in `P02.*`.

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

### Step 02 — preflight-review (pr-autopilot)

| # | Predicate |
|---|---|
| S02.1 | `context.preflight_passes.pass2_raw` is set (array; may be empty) |
| S02.2 | `context.preflight_passes.merged` is set and equals `pass2_raw` at this point (no other passes run at preflight) |
| S02.3 | Every `severity` in `pass2_raw` findings is one of `critical`/`important`/`minor` (lowercase) |

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
| S04.3 | Every entry in `verifier_judgements` has a matching entry in `agent_returns` (by `feedback_id`), AND every `feedback_id` whose fixer invocation produced a `fixed`/`fixed-differently` verdict (recorded via the `subagent_return` log event) has an entry in `verifier_judgements`. Demotion in the policy ladder does NOT excuse a missing verifier_judgement — judgements are keyed off the fixer's ORIGINAL verdict, not the post-ladder one. |
| S04.4 | `files_changed_this_iteration` equals the union of `files_changed` across all returns |
| S04.5 | No file in `files_changed_this_iteration` has a path outside `context.repo_root` |
| S04.7 | After the policy ladder resolves for the current dispatch, no surviving fixer's `changed_files` contains an entry that also appears in any rolled-back fixer's `changed_files` unless a `fixer_reverify` log event for that survivor exists this step with the overlapping files listed in `overlap_files`. See `04-dispatch-fixers.md` — "Overlap re-verify". |

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
| S06.3 | The most recent `git_commit_argv` log event for this step has an `argv` string that contains none of the forbidden-flag tokens, matched as whole words: `--no-verify`, `--no-gpg-sign`, `-c commit.gpgsign=false`. Step 06 MUST emit this event immediately before invoking `git commit ...` (see `06-commit-push.md` and `log-format.md#event-taxonomy`); the predicate greps the argv string, not the commit message, because forbidden flags only ever appear in argv. |

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

### Step 04g — post-open /code-review invocation (pr-autopilot)

| # | Predicate |
|---|---|
| S04g.1 | After step 04g completes, no top-level PR comment authored by `context.self_login` has a body matching `^\s*#{1,6}\s*code[\s-]*review\b` (case-insensitive). Regression guard against α's posting behavior. Check via `gh pr view <PR> --json comments --jq '.comments[] \| select(.author.login == "<self_login>") \| .body'` and grep the heading regex. A hit = hard halt. |

## P02 — preflight-dispatch invariants (pr-autopilot step 02)

Preflight runs an adversarial reviewer and may dispatch fixers to address
its findings — all before any PR exists. The post-dispatch predicates
below are the preflight-scope counterparts of `S04.*`. Preflight cites
these, never `S04.*`.

| # | Predicate |
|---|---|
| P02.1 | Every `fixer_return` from preflight dispatch has a matching `preflight_findings[].id` referenced in its `feedback_id`. Unmatched returns indicate a drift between dispatch input and return. |
| P02.2 | If a `fixer_return.verdict` is `fixed` or `fixed-differently`, either (a) the working-tree diff is non-empty, OR (b) the return carries `no_diff_needed: true` (e.g., the fixer determined the finding was already addressed). |
| P02.3 | For every rolled-back fixer return, the files listed in its `changed_files` are absent from the current working-tree diff. Rollback must be effective. |
| P02.4 | The state file is still named `branch-<slug>.json` at preflight time. No `pr-<N>.json` writes may occur in preflight — the PR number does not exist yet; the state-rename happens in step 04. |

If the preflight dispatch also performs an overlap re-verify (same
semantics as `S04.7`), add a preflight-scoped version here later. For β,
preflight dispatch is rare and single-shot; overlap only matters in the
comment loop where parallel fixers are typical.

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
