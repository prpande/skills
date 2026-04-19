# pr-autopilot improvements — sub-project α: foundations + adversarial review

**Date**: 2026-04-18
**Author**: Pratyush Pande
**Status**: Design, pending implementation plan
**Supersedes specific parts of**: [2026-04-17 pr-autopilot skill design](./2026-04-17-pr-autopilot-skill-design.md)

## Summary

First of three sub-projects that address the architectural, correctness, and observability gaps identified in a critique of the original `pr-autopilot` / `pr-followup` skills. Sub-project α introduces: a central schema documented in one file; durable per-PR state surviving `ScheduleWakeup` cycles; a concurrent-invocation advisory lock; structured JSON-lines logging; an adversarial second reviewer in preflight; post-open invocation of the host platform's native code-review skill; a fixer-output verification pass that catches confidently-wrong review suggestions; plus repo-agnosticity hygiene.

**Zero-dependency constraint**: the skill must not require `pip install`, `npm install`, or any runtime other than what the host platform already provides (`git`, `gh` or `az`, Bash, and the LLM itself). This means the implementation mechanism is markdown-prose-driven with shell-level state primitives — not Python scripts. We accept the loss of unit tests and strict runtime schema validation as tradeoffs; we mitigate both via (a) short, re-read-every-step schema documentation, (b) an invariants-at-end-of-step check list the LLM applies, and (c) captured JSON reference fixtures for manual replay.

## Goals

- Eliminate silent schema drift between step files (critique #1).
- Persist context across `ScheduleWakeup` cycles so session restarts don't lose loop state (critique #4).
- Prevent two concurrent skill invocations on the same PR from corrupting each other's state (critique edge case).
- Give the user an audit trail (JSON-lines log) for when the skill makes non-obvious decisions (critique #13).
- Catch issues at preflight that a linear review misses — cross-artifact drift, external-interface contract mismatches, control-flow termination, format/content escaping, validator completeness (critique #14, generic).
- Defend against confidently-wrong reviewer feedback being applied blindly (critique #16).
- Keep the skill install-free: no new runtime dependencies.

## Non-goals

- Rewriting the orchestrator into compiled code. The skill stays markdown-driven; the LLM is still the orchestrator.
- Unit-test infrastructure. We accept smoke-test-only verification as a cost of zero-dependency.
- Changing any user-visible feature of the existing skills. No feature cuts.
- Addressing edge cases that require platform-side cooperation (GitHub App identity for `/code-review` output, branch protection overrides). Those stay on the backlog.

## Architecture

Every change in this sub-project is additive. The existing skill layout is preserved:

```
pr-autopilot/, pr-followup/, pr-loop-lib/   (unchanged top-level structure)
pr-loop-lib/references/                      (new files added here)
  context-schema.md                          (NEW)
  state-protocol.md                          (NEW)
  log-format.md                              (NEW)
  invariants.md                              (NEW)
  adversarial-review-prompt.md               (NEW)
  fixer-verifier-prompt.md                   (NEW)
  merge-rules.md                             (NEW)
  known-bots.md                              (existing, scrubbed — see Cleanup)
  ...                                        (other existing references unchanged)
```

No new content in `scripts/`. The existing `scripts/validate.py` stays as a markdown structural checker only — it is not extended to runtime state validation, and no new scripts are added. All sub-project α logic lives in markdown reference files.

### Per-PR state location

State, log, and lock files live inside the repo the skill is operating on:

- State: `<repo-root>/.pr-autopilot/pr-<PR>.json`
- Log: `<repo-root>/.pr-autopilot/pr-<PR>.log` (JSON-lines)
- Lock: `<repo-root>/.pr-autopilot/pr-<PR>.lock`

Rationale: state is per-repo by nature (PRs belong to repos). Keeping it alongside the repo is natural, makes cleanup obvious (`rm -rf .pr-autopilot`), and keeps two worktrees of the same repo naturally partitioned. On first use in a repo the skill appends `.pr-autopilot/` to `.gitignore` if not already present.

### Data flow — how the LLM uses the state files

The markdown step files say, at every entry: *"Before acting, read `pr-loop-lib/references/context-schema.md` and the state file at `.pr-autopilot/pr-<PR>.json`. Validate every field you intend to write against the schema. After acting, update the state file atomically via the Write tool (which replaces the file) and append a log event."*

The LLM reads the schema, reads the state, makes changes, writes state, appends log. No intermediate language runtime. Every state transition is auditable because the log captures it.

## Reference files (new)

### `context-schema.md`

Single source of truth for the `context.*` fields referenced across every step. Short enough to re-read at every step entry (target: under 150 lines). Each field gets a row with:

- Field name
- Type (JSON-schema style — string, integer, array, object, enum)
- Allowed values (for enums: the literal list)
- Purpose (one sentence)
- Which step populates it, which step consumes it

The existing 28 `context.*` fields are documented. New fields introduced by sub-project α are added here:

- `context.session_id` — UUID generated at skill entry; written into the lock file; constant across `ScheduleWakeup` wakes.
- `context.host_platform` — one of `claude-code`, `codex`, `gemini`, `other`.
- `context.preflight_passes` — object carrying `pass2_raw` and `merged` (no `pass1_*` fields since we dropped structured Pass 1).
- `context.verifier_judgements` — array, one entry per fixer return where verification ran.
- `context.code_review_invoked` — boolean, true after `/code-review` fires.
- `context.code_review_invoked_at` — ISO-8601 timestamp.

### `state-protocol.md`

Describes how the LLM reads, writes, and locks the state file. Covers:

- **Initial write on first entry**: check lock exists; if present and `acquired_at < 30 min ago`, halt with concurrent-session error; otherwise write a new lock file with `session_id` + `acquired_at` (current UTC ISO-8601).
- **Lease refresh**: every state-file update, overwrite the lock file with the same `session_id` and a fresh `acquired_at`.
- **Stale lock reclaim**: if the lock file's `acquired_at` is more than 30 minutes old, treat the holder as dead, overwrite the lock with a new session, log a `lock_stale_reclaimed` event.
- **Release on termination**: step 11 (final report) deletes the lock file. If step 11 never runs (crash), lock goes stale and the next invocation reclaims it after 30 min.
- **Atomic write**: the Write tool replaces files atomically. No partial state on disk after a crash mid-write. For appends (log file), use `printf ... >> file` via Bash — POSIX append is atomic for small writes.
- **First-run `.gitignore` entry**: on first `state init`, read `.gitignore` (or create it); if `.pr-autopilot/` is not already listed, append the line.

The file is prescriptive enough that the LLM can follow it without interpretation gaps. Example phrasing: *"To acquire the lock, first read `.pr-autopilot/pr-<PR>.lock`. If the file does not exist, write a new lock with the current session's session_id and the current UTC timestamp. If the file exists, parse the `acquired_at` field..."* — step by step.

### `log-format.md`

Defines the JSON-lines event schema. Every event has `ts`, `pr`, `session_id`, `iteration`, `step`, `event`, `data`. Event types:

| Event | When | `data` shape |
|---|---|---|
| `skill_start` | Skill entry | `{args, cap, wait_override, host}` |
| `step_start` / `step_end` | Every step transition | `{step_name}` |
| `state_write` | After every state update | `{changed_keys}` |
| `lock_acquired` / `lock_released` / `lock_stale_reclaimed` | Lock protocol events | `{session_id}` |
| `comments_fetched` | Step 02 (loop) | `{surface_counts, total}` |
| `triage_result` | Step 03 | `{actionable, suspicious, filtered_self, filtered_known_bot, filtered_pre_push}` |
| `cluster_gate_fired` | Step 04 | `{items, clusters_formed}` |
| `subagent_dispatch` | Every Agent tool call | `{role, model, prompt_first_200_chars, feedback_id?, timeout_s}` |
| `subagent_return` | Every subagent return | `{role, feedback_id?, verdict, files_changed, reason_first_200_chars, duration_ms}` |
| `verifier_judgement` | After fixer verifier runs | `{feedback_id, fixer_verdict_before, fixer_verdict_after, judgement, reason_first_200_chars}` |
| `local_verify` | Step 04.5 | `{iteration, passed, failed_cmd?, retry_attempted, rolled_back}` |
| `commit_pushed` | Step 06 | `{sha, files, message_first_line}` |
| `reply_posted` | Step 07 | `{feedback_id, thread_id?, surface, resolved}` |
| `quiescence` | Step 08 | `{reason, loop_exit_reason, termination_reason}` |
| `ci_result` | Step 09 | `{check_name, state, link}` |
| `code_review_invoked` | After `gh pr create` (step 04 of pr-autopilot) | `{host, skill, invoked_at}` |
| `skill_end` | Step 11 | `{termination_reason, iterations, commits, fixes_applied}` |
| `invariant_fail` | End of any step | `{step, invariant, observed, expected}` |
| `error` | Unhandled exception | `{stage, error_type, message}` |

Prompt text and reason fields are truncated to 200 characters. The log is the user-facing audit trail.

### `invariants.md`

Finite list of post-step assertions the LLM checks at the end of each step and fails loudly if any violate. Examples:

- **After step 03**: `len(actionable) + len(suspicious) + len(dropped) == len(all_comments)`. Every comment must be accounted for.
- **After step 04**: `len(agent_returns) == len(actionable) + len(cluster_units)`. Every dispatched unit returned something.
- **After step 04.5**: if `context.files_changed_this_iteration` is non-empty, `context.sanity_check_passed[iteration]` must be set (true or false — absence is a bug).
- **After step 06**: if `last_push_sha` updated, `last_push_timestamp` also updated, and both match the latest commit on HEAD.
- **After step 08**: exactly one of `{loop_exit_reason, termination_reason}` routing paths is triggered. Never both missing.

Violations are logged as `invariant_fail` events and halt the skill with a diagnostic. The LLM is instructed to compute these finite checks; they are short enough to verify mentally.

### `adversarial-review-prompt.md`

Contains the full Pass 2 persona prompt, kept repo-agnostic. Scope: three-pass adversarial review — linear per-file, cross-artifact consistency sweep (identifier drift), interface + control-flow sweep (external contracts, termination traces, format/content escaping, validator completeness). Output: JSON findings list with severity, evidence-based only.

The prompt is stored as a reference so it can be edited by the user (e.g., to tune the persona) without touching the step file that dispatches it.

### `fixer-verifier-prompt.md`

Contains the verifier subagent prompt. Scope: given a feedback item and the diff a fixer produced, judge whether the diff addresses the feedback. Output: JSON with `judgement` ∈ `{addresses, partial, not-addresses, feedback-wrong}` plus evidence citation.

Verdict gating (defined in the prompt + enforced by the invoking markdown):
- `feedback-wrong` is only reachable when the fixer's own verdict was `fixed-differently`. On `fixed` verdicts, the verifier's hardest rejection is `not-addresses`.
- `fixed-differently` whose diff addresses the stated concern → verifier judgement `addresses` (different mechanism is fine).

### `merge-rules.md`

Documents the dedup and severity rule (currently only used by the preflight merge of Pass 2 findings with any `/code-review` output that lands during iter 1):

- Deduplicate by `(file, line_range, category)` similarity.
- If the same finding is flagged by Pass 2 (preflight) AND later posted by `/code-review` (post-open), escalate severity one tier.
- Metadata preserved: which source, confidence score (where available), dedup-key.

## Step-by-step changes

### Step 01 — `pr-autopilot/steps/01-detect-context.md`

Additions:
- Detect `host_platform`: check `$CLAUDE_CODE_ENV` first, then fall back to `$CODEX_ENV`, then `$GEMINI_CLI_ENV`, then default to `"other"`. The exact detection commands live in `state-protocol.md`. Store the result in `context.host_platform`.
- Generate `session_id` (UUID); store in context.
- Perform preflight environment checks: `gh auth status`, `git rev-parse --show-toplevel`, `gh pr view` for draft-PR detection. Halt early with a clear diagnostic if any fail.
- On first entry for a given PR, initialize the state file per `state-protocol.md`. On re-entry (post-wakeup), load existing state and refresh the lock lease.

### Step 02 — `pr-autopilot/steps/02-preflight-review.md`

Revised flow:
- **Pass 1 is dropped.** No multi-reviewer fan-out, no Haiku scoring layer.
- **Pass 2 is the only preflight review**: one Sonnet adversarial subagent dispatch using `adversarial-review-prompt.md`.
- Findings are classified by severity (Critical / Important / Minor).
- Critical + Important findings are fixed inline before PR opens (same as current behavior — dispatched via `pr-loop-lib/steps/04-dispatch-fixers.md` mechanics).
- Minor findings are recorded in `context.preflight_minor_findings` and folded into the PR body's "Known minor observations" section.

### Step 04 — `pr-autopilot/steps/04-open-pr.md`

Addition at the end (new sub-step 4g):
- After `gh pr create` succeeds and outputs are recorded, invoke the host's native code-review skill.
- On Claude Code: use the Skill tool to invoke `code-review`.
- On other hosts: log `code_review_invoked` event with `host: other, skipped: true`.
- Fire-and-forget — the loop proceeds to the wait cycle; `/code-review`'s output lands as a PR comment during iter 1.
- Record `context.code_review_invoked = true` and `context.code_review_invoked_at`.

### Loop step 03 — `pr-loop-lib/steps/03-triage.md`

Addition: a known-bot exemption for the `/code-review` output.

- Top-level PR comments authored by `context.self_login` (the invoking user) are normally dropped by Filter A's self-login rule.
- Exception: if the body starts with `### Code review` (the canonical signature of `/code-review`'s comment), keep it as actionable.
- Parse each numbered finding from the comment body into its own actionable item with `surface: issue`, `body: <finding text>`, `path`/`line` extracted from the embedded SHA URL.

### Loop step 04 — `pr-loop-lib/steps/04-dispatch-fixers.md`

Addition: the fixer-verifier layer.

- After each fixer returns with `verdict: fixed` or `fixed-differently`, dispatch a verifier subagent using `fixer-verifier-prompt.md`.
- The verifier receives: original feedback text (wrapped in `<UNTRUSTED_COMMENT>`), the fixer's verdict + reason, and the diff of just the files the fixer changed.
- Apply the policy ladder per the verifier's judgement:
  - `addresses` → accept as-is.
  - `partial` → demote verdict to `needs-human`, keep the diff in the working tree.
  - `not-addresses` → demote to `needs-human`, roll back the fixer's file changes.
  - `feedback-wrong` (only when fixer's original verdict was `fixed-differently`) → demote to `not-addressing`, roll back, reply declining with verifier's evidence.
- Every judgement logged as `verifier_judgement` event.

### Step 11 — `pr-loop-lib/steps/11-final-report.md`

Additions:
- New section in the report: **Verifier judgements** — counts of `addresses / partial / not-addresses / feedback-wrong` across the run.
- Log file path printed in the report footer so the user knows where to look for detail.
- On `skill_end`, release the lock per `state-protocol.md`.

## Cleanup (item M + repo-agnosticity)

1. **Delete** `docs/superpowers/plans/2026-04-17-pr-autopilot-skill-implementation.md` (the 3,028-line throwaway).
2. **Scrub** `pr-loop-lib/references/known-bots.md`: remove user/team-specific default entries (`mergewatch-playlist[bot]`, `mindbody-ado-pipelines[bot]`, `sonarqube-mbodevme[bot]`); keep generic defaults (`Copilot`, `copilot-pull-request-reviewer[bot]`, `dependabot[bot]`, `github-actions[bot]`, generic `sonarqube*[bot]` pattern); move the removed entries into a "Adding team-specific bots" section as extension examples.
3. **Grep-and-review** all skill files for hardcoded user/repo references (`mindbody`, `prpande`, `BizApp`); rewrite any user-facing references as generic. Historical design docs keep their context.
4. **Note in the existing 2026-04-17 design doc**: add a top-level pointer to this 2026-04-18 improvements spec for anyone reading the history.

## Repo-agnosticity in reference data

- Captured JSON fixtures from real PRs (kept under `pr-loop-lib/fixtures/` as reference data for future manual testing) are anonymized: repo owner/name → `owner/repo`, non-bot user logins → `user-a`/`user-b`, commit SHAs kept but not referenced by fixtures, timestamps rebased to epoch 2024-01-01 preserving relative ordering. Bot logins are preserved since they're what the classifier matches.
- No skill file names a specific PR as a case study. The design doc (this file) may reference specific PRs in the context of the critique that motivated the work, since it's historical.

## What we accept as cost

- **No unit tests.** Changes to the triage rules, merge logic, or filter regexes are verified by reading the change, then smoke-testing on a real PR. Fixtures exist as reference data but nothing runs them automatically.
- **No strict schema enforcement at runtime.** If the LLM writes a state field with a value outside the documented enum, nothing rejects the write immediately — detection happens at the next consumer of the field. Mitigations: the schema file is short enough to be re-read every step, and the `invariants.md` checks catch obvious violations (e.g., step 03's account-every-comment invariant would fail if triage wrote an invalid category).
- **Weaker concurrency safety.** The advisory lock is convention-enforced (the LLM honors it) rather than OS-enforced (via `flock` or similar). Two malicious sessions could race, but two cooperative sessions are well-protected by the lease + stale-reclaim logic.

These costs are the price of zero-dependency. They are acceptable for a user-level skill where the primary threat model is "a single user runs this on their own PRs" rather than "adversarial multi-tenancy."

## Open questions

None as of this revision.

## Decisions log

- **Zero-dependency**: skill requires only `git`, `gh` or `az`, Bash, and the LLM. No Python, Node, pip install, or additional packages.
- **State location**: `<repo-root>/.pr-autopilot/` with `.gitignore` entry added on first use. Per-repo, per-PR files.
- **Lock strategy**: advisory file-existence + 30-minute lease, reclaimable if stale.
- **Preflight review**: single adversarial Pass 2 subagent only. Pass 1 dropped. Host's native `/code-review` handles rigorous review post-open by firing once after PR creation.
- **Fixer-verifier gating**: `feedback-wrong` only reachable from `fixed-differently` origin.
- **Logs**: JSON-lines in `.pr-autopilot/`, prompt fields truncated to 200 characters.
- **Tests**: captured JSON fixtures for reference only, no test runner.
- **Invariants**: short list of post-step assertions the LLM checks and fails loudly on.
- **Known-bots**: generic defaults only; team-specific bots move to an "extension" section.
- **Worktree and branch**: this work proceeds on `pp/pr-autopilot-subproject-alpha-design` at `C:\src\skills-alpha`. PR #1 (the original build) is merged to main; this sub-project builds on top.
