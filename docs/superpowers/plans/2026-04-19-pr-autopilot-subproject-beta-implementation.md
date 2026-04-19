# pr-autopilot Sub-Project β Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the 10 concurrency / escaping / invariant-correctness fixes from the [2026-04-19 sub-project β design](../specs/2026-04-19-pr-autopilot-subproject-beta-design.md), plus the late-added Section 5 "internal-only automated review" (item 11). Zero-dependency: no Python, no pip install, no new CLI tooling. All edits land in existing markdown files.

**Source of requirements:** The "Known follow-ups for sub-project β" list in PR [#3](https://github.com/prpande/skills/pull/3) (concurrency + escaping), plus unresolved findings from inline review comments on that PR.

**Architecture:** Corrective edits to α. No new reference files. No new step files. Ten existing markdown files edited across `pr-loop-lib/references/`, `pr-loop-lib/steps/`, and `pr-autopilot/steps/`.

**Tech stack:** Markdown + YAML frontmatter. Shell (`bash`, `git`, `gh`). Claude Code Skill + Agent tools. No Python, Node, or pip install.

**Working directory:** `<worktree-path>` on branch `<feature-branch>` (worktree of the main checkout). The original run of this plan used `C:\src\skills-beta` on branch `pp/pr-autopilot-subproject-beta-design`; these are retained in quoted shell commands below only as historical examples.

**Testing:** Same as α — markdown prose, no unit-test runner. Structural validation via existing `scripts/validate.py`. Smoke test via a real PR at the end (the β PR itself runs through the just-updated pr-autopilot skill).

**Per-task cadence:** each task edits one file (or makes one coherent grouped edit), runs `python scripts/validate.py`, commits. No new scripts.

**Repo layout changes** (all edits to existing files):

```
pr-loop-lib/references/
  state-protocol.md              (EDIT, Task 1)        — durability primitives rewrite
  log-format.md                  (EDIT, Task 2)        — add new event records
  invariants.md                  (EDIT, Task 3)        — scope preamble + P02.* + S06.3 rework
  fixer-verifier-prompt.md       (EDIT, Task 7)        — nonce-delimited untrusted slots

pr-loop-lib/steps/
  03-triage.md                   (EDIT, Task 4)        — Filter B.5 two-step pipeline
  06-commit-push.md              (EDIT, Task 5)        — emit git_commit_argv event
  04-dispatch-fixers.md          (EDIT, Task 6, 7, 9)  — overlap re-verify; nonce emit; user-intervention-needed
  11-final-report.md             (EDIT, Task 9)        — ci-red / ci-skipped wire-in

pr-autopilot/steps/
  02-preflight-review.md         (EDIT, Task 8)        — cite P02.* instead of S04.*; compute description_hash
```

Task count: 9 tasks across 4 phases. Task 7 is the only one that spans two files (prompt template + step that emits nonce); grouped to keep mechanic coherent.

---

## Phase 1 — Durability primitives (Section 1 of the spec)

### Task 1: Rewrite `state-protocol.md` durability section

**Files:**
- Edit: `pr-loop-lib/references/state-protocol.md`

- [ ] **Step 1 — Replace lock acquisition section**

Replace the current lock-acquire prose (Read-then-Write on a `.lock` file) with the directory-as-lock pattern:

```bash
lock_dir=".pr-autopilot/pr-${PR}.lock"
if mkdir "$lock_dir" 2>/dev/null; then
  printf '%s\n' "$SESSION_ID" > "$lock_dir/session"
  printf '%s\n' "$(date +%s)" > "$lock_dir/lease"
  # acquired
else
  # read $lock_dir/lease; if (now - lease) > 1800, reclaim by overwriting
fi
```

Add an explicit statement: *"The lock path literal stays `.pr-autopilot/pr-<PR>.lock` (and `.pr-autopilot/branch-<slug>.lock` in preflight) — only the entry type changes (file → directory)."* Update release to `rm -rf "$lock_dir"`. Update stale-reclaim to read `$lock_dir/lease` instead of the flat file.

- [ ] **Step 2 — Replace slug encoding**

Replace the current `branch.replace('/', '-')` prose with reversible percent-encoding:

```bash
slug=$(printf '%s' "$branch" | sed -e 's/%/%25/g' -e 's|/|%2F|g')
```

Note: `%` must be escaped first so subsequent `/` → `%2F` doesn't re-encode earlier `%25` back into `%`. Give the collision example (`feature/a-b` vs `feature-a/b` both → `feature-a-b` under the old scheme; now `feature%2Fa-b` vs `feature-a%2Fb`) so the rationale is legible to the next reader.

- [ ] **Step 3 — Add atomic-write primitive**

Add a new subsection "Atomic state writes":

```bash
printf '%s' "$payload" > "$state.tmp.$$" && mv "$state.tmp.$$" "$state"
```

Document the NTFS caveat honestly: on Linux/macOS `rename(2)` is atomic when source and destination share a filesystem; on native Windows/NTFS the OS performs delete-then-rename and isn't strictly atomic. Document the existing log-replay recovery path as the mitigation.

Call out: *"Do not use the Write tool directly on the state file — it does not guarantee atomic replacement."*

- [ ] **Step 4 — Add migration one-liner**

At the top of the durability section:

> Migration from α: any flat `.pr-autopilot/*.lock` files or pre-β state artifacts under `.pr-autopilot/` may be safely deleted before β acquires. β ships before any production α run; no in-flight migration logic is shipped.

- [ ] **Step 5 — Validate and commit**

```bash
python scripts/validate.py
git add pr-loop-lib/references/state-protocol.md
git commit -m "state-protocol: mkdir-lock, percent-encoded slug, tmp+mv atomic writes (β item 1,2,4)"
```

---

## Phase 2 — Invariant correctness (Section 2 of the spec)

### Task 2: Add new log events to `log-format.md`

**Files:**
- Edit: `pr-loop-lib/references/log-format.md`

- [ ] **Step 1 — Extend event taxonomy**

Append five new event types to the taxonomy table:

| `event` | `data` payload |
|---|---|
| `git_commit_argv` | `{argv: "<space-joined flags>"}` |
| `fixer_reverify` | `{survivor_id, rolled_back_id, overlap_files, new_verdict}` |
| `code_review_rescue_failed` | `{author, body_prefix}` |
| `triage_dedup_miss` | `{candidate_lead, closest_preflight_lead, author}` |
| `verifier_nonce_collision` | `{slot, body_sample}` |

Document each: what fires it, why it exists, what a consumer does with it. Note that `git_commit_argv.argv` is flat-string (space-joined) and therefore lossy for args with spaces — acceptable because the predicate only cares about flag presence.

- [ ] **Step 2 — Validate and commit**

```bash
python scripts/validate.py
git add pr-loop-lib/references/log-format.md
git commit -m "log-format: add five β event types (argv, reverify, rescue-fail, dedup-miss, nonce-collision)"
```

### Task 3: Rework `invariants.md` — scope preamble, P02.*, S06.3

**Files:**
- Edit: `pr-loop-lib/references/invariants.md`

- [ ] **Step 1 — Add scope preamble at top**

Insert, right after the file title:

> **Scope.** `G*` invariants are global (apply in every step). `S*.*` invariants apply *only* inside the comment loop (`pr-loop-lib/steps/03`–`06`). `P*.*` invariants apply in preflight contexts (`pr-autopilot/steps/02`). A step must cite only invariants from its applicable scope.

- [ ] **Step 2 — Introduce P02.* block**

Add a new top-level section `## P02.* — Preflight dispatch invariants` with the four predicates from the spec:

- P02.1: every `fixer_return` has a matching `preflight_findings[].id`
- P02.2: `fixed` / `fixed-differently` verdicts have a non-empty working-tree diff OR `no_diff_needed: true`
- P02.3: rolled-back fixer diffs are absent from current working-tree diff
- P02.4: state file is still `branch-<slug>.json`; no `pr-<N>.json` writes (PR doesn't exist yet)

- [ ] **Step 3 — Rework S06.3 predicate**

Replace the current S06.3 text (checking commit message) with:

> **S06.3** — The latest `git_commit_argv` log event for the current step must not contain any of: `--no-verify`, `--no-gpg-sign`, `-c commit.gpgsign=false`. Checked by greping the `argv` string for each forbidden flag as a whole word.

Add a cross-reference to `log-format.md#event-taxonomy` and to step 06's emit directive (added in Task 5).

- [ ] **Step 4 — Validate and commit**

```bash
python scripts/validate.py
git add pr-loop-lib/references/invariants.md
git commit -m "invariants: add P02.* preflight scope; rework S06.3 to check logged argv (β item 6,8)"
```

### Task 5: Emit `git_commit_argv` in step 06

**Files:**
- Edit: `pr-loop-lib/steps/06-commit-push.md`

- [ ] **Step 1 — Prescribe pre-commit argv log emission**

In the commit-execution subsection, *before* the `git commit` invocation, add:

```bash
# Emit git_commit_argv event for S06.3 audit trail
git_commit_args_str="$*"  # or the exact flags the step assembled
printf '%s\n' "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)\",\"pr\":${PR:-0},\"session_id\":\"$SESSION_ID\",\"iteration\":${ITERATION:-0},\"step\":\"06-commit-push\",\"event\":\"git_commit_argv\",\"data\":{\"argv\":\"$git_commit_args_str\"}}" >> "$LOG"
```

Prose note: *"This event MUST be emitted before `git commit` actually runs. S06.3 checks this event — not the commit message — to verify no hook-skipping flags were used."*

- [ ] **Step 2 — Validate and commit**

```bash
python scripts/validate.py
git add pr-loop-lib/steps/06-commit-push.md
git commit -m "06-commit-push: emit git_commit_argv event for S06.3 (β item 8)"
```

---

## Phase 3 — Filter B.5 rewrite (Section 3 of the spec)

### Task 4: Rewrite Filter B.5 in `03-triage.md`

**Files:**
- Edit: `pr-loop-lib/steps/03-triage.md`

- [ ] **Step 1 — Replace the tolerant-rescue section**

Replace the exact-literal `### Code review\n` prefix check with:

```
^\s*#{1,6}\s*code[\s-]*review\b      (case-insensitive)
```

On match, strip the heading line and carry the remainder as candidate body. On near-miss (top-level comment whose author is in the known-bots list but body doesn't match), emit `code_review_rescue_failed` with a 200-char body sample.

- [ ] **Step 2 — Replace the dedup section with normalized-lead-paragraph hash**

Spell out the five normalization steps (strip fences+HTML, first blank-line split, lowercase+whitespace-collapse, truncate 200, sha1). Reference the preflight-side computation: preflight step 02 computes `description_hash` per finding using the same algorithm (Task 8).

Dedup rule: `if hash(candidate_lead) == any preflight_finding.description_hash: mark dup`.

On non-match against a preflight finding from the *same source author*, emit `triage_dedup_miss` with both normalized leads.

- [ ] **Step 3 — Validate and commit**

```bash
python scripts/validate.py
git add pr-loop-lib/steps/03-triage.md
git commit -m "03-triage: Filter B.5 tolerant rescue + normalized-lead dedup (β item 7,10)"
```

---

## Phase 4 — Isolated items (Section 4 of the spec)

### Task 6: Overlap re-verify in `04-dispatch-fixers.md`

**Files:**
- Edit: `pr-loop-lib/steps/04-dispatch-fixers.md`

- [ ] **Step 1 — Add overlap-re-verify subsection to Policy Ladder**

Insert after the rollback step in the Policy Ladder:

> **Overlap re-verify.** After any rollback, compute `overlap_set = { survivor : changed_files ∩ rolled_back.changed_files ≠ ∅ }`. For each survivor in overlap_set, examine the current working-tree diff for the overlap file(s). If the current diff is empty (survivor's change was redundant with the rolled-back change), skip re-verify and cascade-rollback. Otherwise re-dispatch the verifier with the current diff. On verdict drop to `feedback-wrong`, cascade-rollback. On verifier error, escalate survivor to `needs-human`. Emit `fixer_reverify` for each re-dispatch.

- [ ] **Step 2 — Add S04.7 reference**

Add near the ladder: *"Invariant S04.7 (invariants.md) — no survivor's `changed_files` contains an entry also present in a rolled-back fixer's `changed_files` without a `fixer_reverify` log event."*

- [ ] **Step 3 — Update `invariants.md` to add S04.7**

```markdown
**S04.7** — After the policy ladder resolves for the current dispatch, no survivor fixer's `changed_files` contains an entry also present in any rolled-back fixer's `changed_files` unless a `fixer_reverify` event for that survivor exists in the log with the overlapping files listed.
```

- [ ] **Step 4 — Validate and commit**

```bash
python scripts/validate.py
git add pr-loop-lib/steps/04-dispatch-fixers.md pr-loop-lib/references/invariants.md
git commit -m "04-dispatch-fixers: overlap re-verify in policy ladder; add S04.7 (β item 3)"
```

### Task 7: Nonce-delimited untrusted slots in verifier prompt

**Files:**
- Edit: `pr-loop-lib/references/fixer-verifier-prompt.md`
- Edit: `pr-loop-lib/steps/04-dispatch-fixers.md` (nonce emit mechanic)

- [ ] **Step 1 — Update `fixer-verifier-prompt.md`**

Replace the three untrusted slots with nonce-delimited variants:

```
<UNTRUSTED_FEEDBACK_${NONCE}>
{{FEEDBACK_BODY_VERBATIM}}
</UNTRUSTED_FEEDBACK_${NONCE}>

<UNTRUSTED_REASON_${NONCE}>
{{FIXER_REASON}}
</UNTRUSTED_REASON_${NONCE}>

<UNTRUSTED_DIFF_${NONCE}>
{{FIXER_DIFF}}
</UNTRUSTED_DIFF_${NONCE}>
```

Add a system-prompt preamble explaining the nonce and the three tag patterns. Specify: raw content must not contain `_${NONCE}`; on first collision regenerate; on second, abort and log `verifier_nonce_collision`.

- [ ] **Step 2 — Update `04-dispatch-fixers.md` nonce emit**

Before rendering the verifier prompt:

```bash
NONCE=$(printf '%08x' $((RANDOM * RANDOM)))
# ensure no slot body contains "_${NONCE}"; regenerate once if collision; abort if still colliding
```

Use builtins only — no `uuidgen` (not portable to minimal git-bash). `RANDOM * RANDOM` gives ~30 bits of entropy — sufficient since we only need low collision probability against arbitrary user content, not cryptographic strength.

- [ ] **Step 3 — Validate and commit**

```bash
python scripts/validate.py
git add pr-loop-lib/references/fixer-verifier-prompt.md pr-loop-lib/steps/04-dispatch-fixers.md
git commit -m "fixer-verifier: nonce-delimited untrusted slots for all three inputs (β item 5)"
```

### Task 8: Cite `P02.*` and compute preflight `description_hash` in step 02

**Files:**
- Edit: `pr-autopilot/steps/02-preflight-review.md`

- [ ] **Step 1 — Replace S04.* citations with P02.***

Find every `S04.*` reference in step 02's post-dispatch invariant block and replace with the corresponding `P02.*`. Cross-reference `invariants.md#p02-preflight-dispatch-invariants`.

- [ ] **Step 2 — Add description_hash computation at preflight-finding time**

When preflight-findings are written to `preflight_findings[]`, also compute and store `description_hash` per finding using the five-step normalization from Task 4 (so Filter B.5's dedup can compare keys deterministically at loop-iter-1).

- [ ] **Step 3 — Validate and commit**

```bash
python scripts/validate.py
git add pr-autopilot/steps/02-preflight-review.md
git commit -m "02-preflight: cite P02.* invariants; store per-finding description_hash (β item 6,7)"
```

### Task 9: Wire in unused termination reasons

**Files:**
- Edit: `pr-loop-lib/steps/11-final-report.md` (ci-red, ci-skipped)
- Edit: `pr-loop-lib/steps/04-dispatch-fixers.md` (user-intervention-needed)

- [ ] **Step 1 — Wire `ci-red` in step 11**

Where the CI-gate loop runs out of retries while checks are still failing, set `context.termination_reason = "ci-red"`.

- [ ] **Step 2 — Wire `ci-skipped` in step 11**

In the CI-gate preamble, when `gh pr checks` reports zero workflow runs in the post-push lookback window (no CI configured for this repo), set `context.termination_reason = "ci-skipped"`.

- [ ] **Step 3 — Wire `user-intervention-needed` in step 04**

In the policy-ladder `needs-human` escalation path, and in the overlap re-verify fallback path (Task 6), set `context.termination_reason = "user-intervention-needed"` when the escalation terminates the loop.

- [ ] **Step 4 — Validate and commit**

```bash
python scripts/validate.py
git add pr-loop-lib/steps/11-final-report.md pr-loop-lib/steps/04-dispatch-fixers.md
git commit -m "termination-reasons: wire ci-red, ci-skipped, user-intervention-needed at real sites (β item 9)"
```

---

## Phase 4b — Internal-only automated review (Section 5 of the spec)

Late-added to β scope. Four coordinated edits across pr-autopilot
step files plus two reference files.

### Task 9b: Add new context fields

**Files:**
- Edit: `pr-loop-lib/references/context-schema.md`

- [ ] **Step 1 — Add three fields**

Append rows to the appropriate tables:

| Field | Type | Purpose |
|---|---|---|
| `code_review_raw_output` | string (default "") | Captured return of host's `review` skill. Never posted. |
| `internal_review_findings` | array of objects (default `[]`) | Per-finding records; see Section 5 of spec for shape. |
| `internal_review_summary_path` | string or null | Path to `<repo>/.pr-autopilot/pr-<PR>-review-summary.md`. |

- [ ] **Step 2 — Validate and commit**

```bash
python scripts/validate.py
git add pr-loop-lib/references/context-schema.md
git commit -m "context-schema: add internal_review_* fields (β item 11)"
```

### Task 9c: Preflight writes to summary file, drops Minor-from-body wiring

**Files:**
- Edit: `pr-autopilot/steps/02-preflight-review.md`

- [ ] **Step 1 — Initialize the summary file on first write**

Right after preflight findings are classified by severity, create
`.pr-autopilot/pr-<PR>-review-summary.md` (or `branch-<slug>-review-
summary.md` pre-PR-assignment) and populate the preflight section.
Store the path in `context.internal_review_summary_path`. Use
Primitive C (tmp+mv) from state-protocol.md — same atomicity rule as
state writes.

- [ ] **Step 2 — Populate `internal_review_findings` with preflight entries**

For each Critical/Important finding that dispatch handled, append a
record to `context.internal_review_findings` with `source:
"preflight"` and the post-dispatch outcome (`status`). For each Minor
finding, append with `status: "captured-only"` (not surfaced on PR,
not dispatched).

- [ ] **Step 3 — Explicit note: minor findings NOT folded into PR body**

Add a sentence in the "Action policy on findings" section: *"Minor
findings are captured in `context.preflight_minor_findings` AND in the
summary artifact, but are NOT included in the PR body under β. See
`04-open-pr.md` for the removed PR-body section."*

- [ ] **Step 4 — Validate and commit**

```bash
python scripts/validate.py
git add pr-autopilot/steps/02-preflight-review.md
git commit -m "02-preflight: write review summary file; drop minor→PR-body wire (β item 11)"
```

### Task 9d: 04g rewrite — capture, don't post; dispatch fixers; new invariant

**Files:**
- Edit: `pr-autopilot/steps/04-open-pr.md`
- Edit: `pr-loop-lib/references/invariants.md`

- [ ] **Step 1 — Remove "Known minor observations" from PR body template**

Delete the row from the Section Fill Rules table in `04-open-pr.md`.
Remove any code path that appended the section.

- [ ] **Step 2 — Rewrite 04g procedure**

Replace the "Why 'post once and continue'" subsection and update the
Invocation subsection so that:
- `review` skill invocation remains as α.
- Rendered output is captured into `context.code_review_raw_output`.
- Findings are parsed (reuse Filter B.5 Stage 1's parser prose — put
  the parser in its own small reference in 03-triage.md if needed,
  or duplicate the specification here).
- Dedup against `preflight_findings[].description_hash` via the
  normalized-lead hash (Section 3). Log `triage_dedup_hit` for
  matches.
- Non-dup findings go through step 04-dispatch-fixers mechanics under
  `P02.*` scope (same as preflight dispatch). Verifier, policy
  ladder, and overlap re-verify apply.
- Any resulting diff is committed + pushed via step 06 mechanics,
  commit subject: `Address internal /code-review findings (preflight)`.
- Record each finding in `context.internal_review_findings` with
  `source: "code-review"` and the post-dispatch outcome. Append to the
  summary file.
- `gh pr comment` is NOT called. Add an explicit "do NOT post" line in
  the procedure.
- Update the host-skill table's "Posts to PR?" column: for
  `claude-code`, the new answer is **"No — captured locally; not
  posted"**.

- [ ] **Step 3 — Add S04g.1 invariant**

In `pr-loop-lib/references/invariants.md`, append a new
"Step 04g — post-open code-review invocation (pr-autopilot)" table
with:

```
| S04g.1 | After step 04g completes, `gh pr view --comments --json
          comments --jq ...` returns no top-level comment authored by
          `context.self_login` whose body matches
          ^\s*#{1,6}\s*code[\s-]*review\b (case-insensitive). A hit
          means the orchestrator regressed into α posting behavior and
          is a hard halt. |
```

Cite S04g.1 at the end of step 04g's procedure.

- [ ] **Step 4 — Validate and commit**

```bash
python scripts/validate.py
git add pr-autopilot/steps/04-open-pr.md pr-loop-lib/references/invariants.md
git commit -m "04g: capture /code-review output internally; never post; add S04g.1 (β item 11)"
```

### Task 9e: Final-report surfaces summary + counts

**Files:**
- Edit: `pr-loop-lib/steps/11-final-report.md`

- [ ] **Step 1 — Replace the "Preflight adversarial review" + "/code-review (post-open)" blocks**

with structured counts from `context.internal_review_findings` by
source. Add a top-level line:

```
Internal review summary: <repo-root>/.pr-autopilot/pr-<N>-review-summary.md
```

so the operator knows where the full detail lives.

- [ ] **Step 2 — Validate and commit**

```bash
python scripts/validate.py
git add pr-loop-lib/steps/11-final-report.md
git commit -m "11-final-report: surface internal-review summary path and counts (β item 11)"
```

## Phase 5 — Smoke test and PR

### Task 10: Refresh skill and open β PR via pr-autopilot

- [ ] **Step 1 — Refresh the skill in this session**

After the last implementation commit, re-read `pr-autopilot/SKILL.md` and every edited step file so the orchestrator runs using the β version of the skill (not the α version it loaded at session start).

- [ ] **Step 2 — Invoke `pr-autopilot`**

Invoke the skill. Preflight adversarial review will run against β's own diff — this is the intended smoke test. Any findings surfaced by the adversarial Pass 2 or by the post-open `/code-review` are addressed in-loop as the loop expects.

- [ ] **Step 3 — Monitor loop to completion**

Drive through the comment loop to `ci-green` (or appropriately-wired `ci-skipped`).

---

## Validation checklist (end of each task)

- [ ] `python scripts/validate.py` passes
- [ ] Commit message follows the `<area>: <change> (β item N)` pattern
- [ ] No new files in `scripts/`
- [ ] No new Python, Node, or pip install references anywhere
- [ ] The task's invariant predicates from the spec are stated somewhere readable by an LLM re-reading the file cold

## Open questions carried from the spec

- **R1** (description_hash 200-char truncation): tune only if `triage_dedup_miss` events show a miss pattern post-merge.
- **R2** (re-verify fan-out on large overlap sets): accept as-is; document in operator-facing notes.
- **R3** (NFS / SMB filesystems): scope-assume local filesystem; document in `state-protocol.md`.
