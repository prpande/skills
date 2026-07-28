# Backend Production Lenses Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `deep-review` a governing tier of 35 backend production-failure lenses that fires on every backend diff and cannot be suppressed by a repo convention, plus a review angle that can trace write paths beyond the diff to evaluate them.

**Architecture:** One new reference file holds the tier. The existing register keeps its path (`pr-autopilot` resolves it) and gains a four-rule precedence model that inserts the tier above repo conventions, a pointer section, and an admission rule. `SKILL.md` gains angle 13 and wires it into the effort table; `agent-briefs.md` gains its brief. `pr-autopilot`'s preflight step resolves the new file independently and degrades when it is absent.

**Tech Stack:** Markdown skill files. `python scripts/validate.py` is the only build step. No application code, no test framework — verification is the validator plus content assertions via `grep`.

## Global Constraints

- Every task ends with `python scripts/validate.py` printing `OK` and exiting 0.
- The validator scans `skills/**` and `docs/**`. Any backticked reference matching `references/*.md`, `steps/NN-*.md`, `platform/*.md`, or `~/.claude/skills/<skill>/...` must resolve to a real file inside the repo.
- The validator rejects `[TBD]`, `TODO: `, `[fill in`, and `XXX ` at the **start of a line** outside fenced code blocks. Inline mentions are fine.
- **The tree is RED before Task 1.** The committed spec at `docs/superpowers/specs/2026-07-28-backend-production-lenses-design.md` backtick-references `references/backend-lenses.md` at lines 72 and 262. Task 1 creates that file and turns the validator green. Do not "fix" the spec by un-backticking.
- Register voice for all lens text: `- **ID — Imperative rule.** Failure mechanism in one or two sentences.` Guards are a following italic line: `*Not a finding when:* ...`.
- Lens text names mechanisms (`rowversion`, `SELECT ... FOR UPDATE`), never one stack's APIs. Stack-specific tells belong in the existing `dotnet`/`N` pack and are out of scope.
- Do not change the finding JSON schema, the verdict rubric, the report format, or `quick`'s agent count.
- Total changed files across the branch: 7 (2 already committed). Stay under the repo's 10-15 file PR cap.

---

### Task 1: The backend lens tier

**Files:**
- Create: `skills/pr-tooling/deep-review/references/backend-lenses.md`
- Source: `docs/superpowers/specs/2026-07-28-backend-production-lenses-design.md` §"The lenses"

**Interfaces:**
- Consumes: nothing.
- Produces: the file path `references/backend-lenses.md`, resolvable from any skill file and from `docs/`. Lens ids `TX1`–`TX5`, `IDM1`–`IDM6`, `TEN1`–`TEN6`, `CA1`–`CA6`, `MIG1`–`MIG4`, `EXP1`–`EXP8` — 35 ids that Tasks 2, 3 and 4 cite.

- [ ] **Step 1: Confirm the validator is red, and why**

Run: `python scripts/validate.py`
Expected: exit 1. **Every** error line is `missing reference: references/backend-lenses.md` or `missing home-ref: ~/.claude/skills/deep-review/references/backend-lenses.md`, against the spec and this plan only. Any error naming a different file or a different cause means the tree was already broken — stop and investigate.

Run: `python scripts/validate.py 2>&1 | grep -cv 'backend-lenses.md'`
Expected: `0`

- [ ] **Step 2: Create the file with its header and trigger**

Write `skills/pr-tooling/deep-review/references/backend-lenses.md` starting with:

```markdown
# Backend production lenses

The governing tier referenced by precedence rule 2 of `references/lens-register.md`.
Each lens is a failure class that has taken backend services down in production —
distilled from postmortems and published API-security guidance rather than from
this register's own review rounds, and admitted under the rule in the register's
Maintenance section.

**This tier is not suppressible.** A repo rule may *narrow* a finding — swap the
prescribed remedy, name the repo's own helper, restrict which paths it covers —
but may not remove the flag. Where a repo convention conflicts with a lens's
remedy, report the defect and prescribe the repo's remedy. The `Not a finding
when:` guards below are the only suppression rules, and they always apply.

## Trigger

The tier fires on a **backend diff**: the diff touches SQL or ORM bindings or
repository-layer code, an HTTP endpoint or route, a GraphQL schema/resolver/loader,
a message or event handler, a schema migration file, or cache access. This is the
union of the `data-access`, `http`, `graphql`, and `runtime` triggers in the
register, so no new detection is needed.

## Severity defaults

`TEN1`, `TEN2`, `TEN6`, and `EXP8` are security findings: **blocker unless
refuted.** Every other lens takes its severity from the concrete failure scenario.

## Posture lenses

`EXP6` and `EXP7` are posture lenses — the defect is the absence of something that
lives nowhere near the diff. They are admissible only when the diff creates or
widens the exposure, and they anchor to the diff line that creates it, never to
the missing configuration. A pre-existing exposure the diff does not widen is not
a finding (U8).
```

- [ ] **Step 3: Copy the 35 lenses verbatim from the spec**

Append the six group sections from spec §"The lenses" — `### TX`, `### IDM`, `### TEN`, `### CA`, `### MIG`, `### EXP` — with these mechanical changes only:

1. Demote `###` group headings to `##` (they are top-level here).
2. Drop the spec's `### Severity defaults` subsection (already in the header above).
3. Keep every `*Not a finding when:*` line attached to its lens.
4. Keep the `*Posture — ...*` markers on `EXP6` and `EXP7`.

Do not reword, reorder, merge, or add lenses. The spec text is the approved text.

- [ ] **Step 4: Assert the tier is complete**

Run: `grep -cE '^- \*\*(TX|IDM|TEN|CA|MIG|EXP)[0-9]+ —' skills/pr-tooling/deep-review/references/backend-lenses.md`
Expected: `35`

Run: `grep -cE '^\s*\*Not a finding when:\*' skills/pr-tooling/deep-review/references/backend-lenses.md`
Expected: `6` (TX1, TX2, IDM1, TEN1, MIG1, EXP2)

The guards are markdown list continuations, indented to align under their
lens bullet exactly as in the spec. Do not dedent them to column 0 — that
breaks the guard out of its bullet and orphans its wrap line. The pattern
above tolerates the leading whitespace deliberately.

Run: `grep -oE '^- \*\*(TX|IDM|TEN|CA|MIG|EXP)[0-9]+' skills/pr-tooling/deep-review/references/backend-lenses.md | sort | uniq -d`
Expected: empty output (no duplicate ids)

- [ ] **Step 5: Run the validator**

Run: `python scripts/validate.py`
Expected: `OK`, exit 0. Every forward reference in the spec and this plan now resolves — including the `~/.claude/skills/deep-review/references/backend-lenses.md` home-ref, which the validator maps onto the repo's `deep-review` skill root.

- [ ] **Step 6: Commit**

```bash
git add skills/pr-tooling/deep-review/references/backend-lenses.md
git commit -m "feat(deep-review): add the backend production lens tier

35 lenses in six groups (TX/IDM/TEN/CA/MIG/EXP) covering transaction
boundaries, idempotency under retry, tenant scoping, cache races,
rolling-deploy migrations, and exposure bounds."
```

---

### Task 2: Register precedence and the tier pointer

**Files:**
- Modify: `skills/pr-tooling/deep-review/references/lens-register.md:1-21` (header + Precedence), and the `## Maintenance` section at the end.

**Interfaces:**
- Consumes: `references/backend-lenses.md` from Task 1.
- Produces: precedence rule numbering that Tasks 3, 4 and 5 cite by number — rule 1 universal, rule 2 backend tier, rule 3 repo conventions, rule 4 scoped packs.

- [ ] **Step 1: Assert the current state**

Run: `grep -n 'Scoped packs are fallback' skills/pr-tooling/deep-review/references/lens-register.md`
Expected: one hit at line 14, inside the three-rule Precedence list.

- [ ] **Step 2: Amend the opening paragraph**

Replace lines 3-5:

```markdown
The canonical rule set consumed by `deep-review` (all effort levels) and by
`pr-autopilot`'s preflight review. Each lens is a repeatable mistake class
distilled from real review rounds — not a style guide.
```

with:

```markdown
The canonical rule set consumed by `deep-review` (all effort levels) and by
`pr-autopilot`'s preflight review. Each lens in *this file* is a repeatable
mistake class distilled from real review rounds — not a style guide. The
governing backend tier in `references/backend-lenses.md` is distilled instead
from production postmortems and published API-security guidance, and is held to
the admission rule in Maintenance.
```

- [ ] **Step 3: Replace the Precedence section**

Replace the three numbered rules with:

```markdown
1. **Universal lenses (`U`) always apply.**
2. **Backend production lenses always fire on a backend diff.** The tier in
   `references/backend-lenses.md` is not suppressible: a repo rule may *narrow*
   a finding — swap the prescribed remedy, name the repo's own helper, restrict
   which paths it covers — but may not remove the flag. Where a repo convention
   conflicts with a lens's remedy, report the defect and prescribe the repo's
   remedy.
3. **Repo-defined conventions govern** everything below this line. Before
   applying any scoped pack, read the target repo's own rule sources:
   `CLAUDE.md` / `AGENTS.md` / `ARCHITECTURE.md`, any repo review skill or
   runbook under `.claude/skills/`, and per-directory convention docs. Where a
   repo rule and a scoped lens conflict, the repo rule wins — apply it and stay
   silent about the suppressed lens.
4. **Scoped packs are fallback suggestions.** Apply a pack only when the diff
   touches its trigger AND the repo has no rule of its own on that subject.
```

Keep the paragraph that follows, changing its first sentence to name a tier id
as well:

```markdown
Findings cite lenses by id (`Lens U3`, `Lens TEN1`). A lens hit is a *candidate*
— verify context before reporting; quoted strings, test doubles, and generated
code false-positive.
```

- [ ] **Step 4: Add the tier pointer section**

Insert immediately after the Precedence section, before `## Universal — always apply`:

```markdown
## Backend production tier

`references/backend-lenses.md` holds the governing tier described in precedence
rule 2 — 35 lenses in six groups, firing whenever the diff touches SQL/ORM or
repository code, an HTTP or GraphQL endpoint, a message handler, a migration
file, or cache access.

| Prefix | Subject |
|---|---|
| `TX` | transaction boundaries and consistency |
| `IDM` | idempotency and delivery semantics |
| `TEN` | tenancy and scoping |
| `CA` | cache correctness |
| `MIG` | schema change under rolling deploy |
| `EXP` | exposure and resource bounds |
```

- [ ] **Step 5: Add the admission rule to Maintenance**

Append to the `## Maintenance` list:

```markdown
- A new **backend production lens** requires either a real incident or review
  round, or a named external source *plus* a stated `Not a finding when:` guard.
  Without that bar a tier nobody can suppress becomes a best-practices dump, and
  reviewers learn to skip its findings.
```

- [ ] **Step 6: Assert the new state**

Run: `grep -nE '^[0-9]\. \*\*' skills/pr-tooling/deep-review/references/lens-register.md | head -4`
Expected: four rules, in the order Universal / Backend production / Repo-defined / Scoped packs.

Run: `grep -c 'backend-lenses.md' skills/pr-tooling/deep-review/references/lens-register.md`
Expected: `3` (opening paragraph, precedence rule 2, tier section)

- [ ] **Step 7: Run the validator**

Run: `python scripts/validate.py`
Expected: `OK`, exit 0.

- [ ] **Step 8: Commit**

```bash
git add skills/pr-tooling/deep-review/references/lens-register.md
git commit -m "feat(deep-review): promote the backend tier above repo conventions

Precedence becomes four rules: universal, backend production tier, repo
conventions, scoped packs. The tier can be narrowed by a repo rule but
never suppressed. Maintenance gains its admission rule."
```

---

### Task 3: Angle 13 — the production failure-mode tracer

**Files:**
- Modify: `skills/pr-tooling/deep-review/SKILL.md` — file list (lines 17-24), effort table (lines 53-60), Phase 0 step 3 (lines 68-71), angle catalog (ends line 134), Related (lines 185-189)
- Modify: `skills/pr-tooling/deep-review/references/agent-briefs.md` — new brief section after the finder brief template

**Interfaces:**
- Consumes: `references/backend-lenses.md` (Task 1); precedence rule 2 (Task 2).
- Produces: the angle number `13` and the Phase 0 backend-diff flag, both consumed by nothing downstream in this plan but relied on by the skill at runtime.

- [ ] **Step 1: Assert the current state**

Run: `grep -nE 'All 12 angles|angle 13' skills/pr-tooling/deep-review/SKILL.md`
Expected: exactly one hit — `All 12 angles` in the `max` effort row — and no `angle 13`. If `angle 13` already appears, this task was partly applied; reconcile before editing.

- [ ] **Step 2: Add the tier to the file list**

In the bullet list under `# deep-review`, after the `lens-register.md` bullet:

```markdown
- `references/backend-lenses.md` — the governing backend tier (precedence
  rule 2 of the register): transactions, idempotency, tenancy, caching,
  migrations, exposure bounds. Fires on any backend diff and cannot be
  suppressed by a repo convention.
```

- [ ] **Step 3: Update the effort table**

Replace the three table rows with:

```markdown
| `quick` | One adversarial reviewer, inline. Angles 1 + 12 merged into a single pass, graded against the universal lenses, the triggered packs, and the backend tier when the diff is backend. No verification fan-out. |
| `standard` | 6 finder agents (angles 1, 2, 3, 5, 11, 12; angle 11 drops out when Phase 0 finds no repo rule sources), plus angle 13 when the diff is backend → dedup → one verifier per surviving candidate. |
| `max` | All 13 angles → dedup → one verifier per candidate → gap sweep → ranked report. Recall mode: catching every real defect outranks avoiding false positives. |
```

- [ ] **Step 4: Record the backend flag in Phase 0**

Replace Phase 0 step 3:

```markdown
3. Decide which register packs the diff triggers (each pack states its
   trigger), and record whether the diff is **backend** — it touches SQL/ORM
   or repository code, an HTTP or GraphQL endpoint, a message handler, a
   migration file, or cache access. A backend diff fires
   `references/backend-lenses.md` under the register's precedence rule 2, and
   adds angle 13 at `standard` and `max`.
```

- [ ] **Step 5: Add angle 13 to the catalog**

Append after angle 12:

```markdown
13. **Production failure-mode tracer** (backend diffs only). For each write
    path the diff touches, trace entry point → service → repository →
    cache/bus and answer the backend tier's questions: where the transaction
    begins and ends and what non-database I/O sits inside it, what happens on
    a retried call or a redelivered message, where the tenant scope comes from
    and whether it reaches every query and every cache key, what a rolling
    deploy does to this schema change, and what bounds the response. Unlike
    angle 12 — a pattern-match pass over the register — this one reads beyond
    the diff. Cite tier ids.
```

- [ ] **Step 6: Update the Related section**

Replace the `pr-autopilot` sentence with:

```markdown
`pr-autopilot`'s preflight review consumes `references/lens-register.md` and
`references/backend-lenses.md` when this skill is installed alongside it, and
degrades gracefully when either is absent. Keep both paths stable.
```

- [ ] **Step 7: Add the angle-13 brief**

Append to `skills/pr-tooling/deep-review/references/agent-briefs.md`, after the finder brief template and before `## Verifier brief template`:

````markdown
## Angle 13 brief (production failure-mode tracer)

Dispatched only when Phase 0 recorded the diff as backend. Same JSON output
schema as the finder brief; what differs is the licence to read beyond the diff
and the admissibility rule for posture findings.

```
You are the production failure-mode tracer in a multi-angle code review. You
are the only finder licensed to read beyond the diff.

For each write path the diff touches, trace it end to end — entry point →
service → repository → cache/message bus — and answer:
- Where does the transaction begin and end, and what non-database I/O happens
  inside it?
- What happens if the caller retries, or the broker redelivers this message?
- Where does the tenant/authorization scope come from, and does it reach every
  query and every cache key on this path?
- What does a rolling deploy do to this schema change while old instances are
  still serving traffic?
- What bounds the size, depth, or duration of the response?

<HARD_RULES_BLOCK>

Rule sources (read before the diff, apply per their precedence notes):
<RULE_SOURCE_PATHS — repo conventions first, then the lens register, then the
backend tier>

The backend tier is not suppressible by a repo convention. Where a repo rule
prescribes a different remedy than the lens, report the finding and prescribe
the repo's remedy. The tier's `Not a finding when:` guards ARE suppression
rules — honour every one.

Posture findings (the defect is the absence of something living nowhere near
the diff — EXP6, EXP7) are admissible ONLY when the diff creates or widens the
exposure. Anchor them to the diff line that creates the exposure, never to the
missing configuration. A pre-existing exposure the diff does not widen is not a
finding (U8).

Surface up to 8 candidate findings. Precision is the verifier's job — err
toward surfacing, but every candidate needs a concrete mechanism, not a vibe.
Do not report a finding you cannot anchor to a file and line.

Return ONLY a JSON array (no prose):
[{"id": "trace-<n>", "file": "<repo-relative>", "line": <int>,
  "category": "<slug>", "summary": "<one sentence: the defect>",
  "failure_scenario": "<concrete inputs/state -> wrong outcome>",
  "lens": "<tier id, e.g. TX4>"}]

An empty array is a valid answer. Do not manufacture findings.
```
````

Model: sonnet, same tier as the other finders.

- [ ] **Step 8: Assert the new state**

Run: `grep -c 'angle 13' skills/pr-tooling/deep-review/SKILL.md`
Expected: `2` — the effort table's `standard` row and Phase 0 step 3.

Run: `grep -n 'All 13 angles' skills/pr-tooling/deep-review/SKILL.md`
Expected: one hit in the `max` row.

Run: `grep -n '^13\. \*\*Production failure-mode tracer\*\*' skills/pr-tooling/deep-review/SKILL.md`
Expected: one hit, immediately after angle 12 in the catalog.

Run: `grep -n 'Angle 13 brief' skills/pr-tooling/deep-review/references/agent-briefs.md`
Expected: one hit, positioned before `## Verifier brief template`.

- [ ] **Step 9: Run the validator**

Run: `python scripts/validate.py`
Expected: `OK`, exit 0.

- [ ] **Step 10: Commit**

```bash
git add skills/pr-tooling/deep-review/SKILL.md skills/pr-tooling/deep-review/references/agent-briefs.md
git commit -m "feat(deep-review): add angle 13, the production failure-mode tracer

Traces write paths end to end on backend diffs, which several tier
lenses need and a diff-scoped finder cannot do. Runs at standard and
max; quick grades against the tier inline with no extra agent."
```

---

### Task 4: pr-autopilot preflight consumes the tier

**Files:**
- Modify: `skills/pr-tooling/pr-autopilot/steps/02-preflight-review.md:41-59` (the "Lens guidance rendering" section)

**Interfaces:**
- Consumes: `references/backend-lenses.md` (Task 1); the precedence wording from Task 2.
- Produces: a new log event name `backend_lenses_missing`, alongside the existing `lens_register_missing`.

- [ ] **Step 1: Assert the current state**

Run: `grep -n 'lens_register_missing' skills/pr-tooling/pr-autopilot/steps/02-preflight-review.md`
Expected: one hit at line 48. This is the degrade path the new file must mirror.

- [ ] **Step 2: Replace the Lens guidance rendering procedure**

Replace the numbered procedure under `## Lens guidance rendering` with:

```markdown
The prompt template's Pass D grades the diff against the `deep-review`
skill's lens register and its backend production tier when that skill is
installed alongside this one.

1. Resolve `~/.claude/skills/deep-review/references/lens-register.md` and
   `~/.claude/skills/deep-review/references/backend-lenses.md`. The two
   resolve independently — either may be absent.
2. **If the register does not exist**: substitute the empty string, log a
   `lens_register_missing` event, and move on — Pass D self-skips on an
   empty block. This keeps pr-autopilot fully functional standalone.
3. **If the register exists**:
   a. Locate the repo's own rule sources: `CLAUDE.md` / `AGENTS.md` /
      `ARCHITECTURE.md` at the repo root, and any review runbook or
      skill under `.claude/skills/`. Build a precedence preamble:
      "Repo-defined conventions govern and are at: <paths>. The lenses
      below are fallback where the repo is silent; universal lenses
      always apply."
   b. From the register, take the Universal section plus every pack
      whose stated trigger matches the diff's content.
   c. When the diff is **backend** — it touches SQL/ORM or repository code,
      an HTTP or GraphQL endpoint, a message handler, a migration file, or
      cache access — append the whole of `backend-lenses.md`, and extend the
      preamble with: "Backend production lenses (TX/IDM/TEN/CA/MIG/EXP)
      always apply on a backend diff — a repo rule may change the prescribed
      remedy but never suppresses the finding; the tier's `Not a finding
      when:` guards are the only suppression rules." If that file is absent,
      log a `backend_lenses_missing` event and continue with (b) alone,
      leaving the preamble unextended.
   d. Substitute preamble + selected sections as `{{LENS_GUIDANCE}}`.
```

- [ ] **Step 3: Assert both degrade paths are documented**

Run: `grep -cE 'lens_register_missing|backend_lenses_missing' skills/pr-tooling/pr-autopilot/steps/02-preflight-review.md`
Expected: `2`

Run: `grep -c 'backend-lenses.md' skills/pr-tooling/pr-autopilot/steps/02-preflight-review.md`
Expected: `2` (the resolve in step 1, the append in step 3c)

- [ ] **Step 4: Verify the home-ref resolves**

The validator checks `~/.claude/skills/...` references against the repo's skill roots.

Run: `python scripts/validate.py`
Expected: `OK`, exit 0. A `missing home-ref` error here means Task 1's file landed at the wrong path.

- [ ] **Step 5: Commit**

```bash
git add skills/pr-tooling/pr-autopilot/steps/02-preflight-review.md
git commit -m "feat(pr-autopilot): feed the backend lens tier into preflight Pass D

Resolves backend-lenses.md independently of the register, appends it on
a backend diff with the narrow-not-suppress preamble, and degrades via
backend_lenses_missing when the file is absent."
```

---

### Task 5: Cross-file consistency and dogfood

**Files:**
- Modify (only if the checks below fail): any of the four files touched by Tasks 1-4.

**Interfaces:**
- Consumes: everything from Tasks 1-4.
- Produces: a green branch ready for a PR.

- [ ] **Step 1: Verify every tier id cited outside the tier file actually exists**

Run:
```bash
comm -23 \
  <(grep -ohE '\b(TX|IDM|TEN|CA|MIG|EXP)[0-9]+\b' \
      skills/pr-tooling/deep-review/SKILL.md \
      skills/pr-tooling/deep-review/references/lens-register.md \
      skills/pr-tooling/deep-review/references/agent-briefs.md \
      skills/pr-tooling/pr-autopilot/steps/02-preflight-review.md \
    | sort -u) \
  <(grep -ohE '^- \*\*(TX|IDM|TEN|CA|MIG|EXP)[0-9]+' \
      skills/pr-tooling/deep-review/references/backend-lenses.md \
    | sed 's/^- \*\*//' | sort -u)
```
Expected: empty output. Any line printed is an id cited but never defined.

- [ ] **Step 2: Verify the register-only lens ids cited by the tier still exist**

The tier text cross-references `U12`, `U18`, `R3`, `R5`, `R6`, `W6`, `I2`, `U8`.

Run: `for id in U12 U18 R3 R5 R6 W6 I2 U8; do grep -q "\*\*$id —" skills/pr-tooling/deep-review/references/lens-register.md || echo "MISSING $id"; done`
Expected: empty output.

- [ ] **Step 3: Verify the branch file count is under the PR cap**

Run: `git diff --stat origin/main...HEAD | tail -1`
Expected: 7 files changed. If higher, something outside this plan's scope was touched — investigate before raising a PR.

- [ ] **Step 4: Full validator run**

Run: `python scripts/validate.py`
Expected: `OK`, exit 0.

- [ ] **Step 5: Dogfood the tier**

Run `/deep-review` at `standard` against a diff that touches a repository method and a cache read — the branch's own diff does not qualify, so use any backend PR available, or construct a scratch diff in the scratchpad.

Confirm three things:
1. Phase 0 records the diff as backend.
2. Angle 13 is dispatched (7 finders, not 6).
3. At least one finding cites a tier id, or the run reports zero tier findings explicitly rather than silently omitting the angle.

Record the outcome in the commit message of Step 6. If angle 13 does not dispatch, the defect is in Task 3 Step 4 (the Phase 0 flag) — fix there, not by special-casing.

- [ ] **Step 6: Commit any fixes**

```bash
git add -A
git commit -m "fix(deep-review): cross-file consistency after the backend tier

Dogfood run at standard on a backend diff: angle 13 dispatched, tier
ids cited."
```

If Steps 1-5 all passed with no edits, skip this commit.

---

## Out of scope

Deliberately not in this plan, per the spec's non-goals:

- Stack-specific tells for the tier (they belong in the `dotnet`/`N` pack).
- Changes to the finding JSON schema, verdict rubric, or report format.
- Changes to `quick`'s agent count.
- Per-repo register staging — that mechanism exists and is untouched.
- Any change to `pr-loop-lib/references/adversarial-review-prompt.md`. Its Pass D
  content is substituted at render time by `02-preflight-review.md`, so Task 4
  covers it. Editing the template directly would duplicate the tier text.
