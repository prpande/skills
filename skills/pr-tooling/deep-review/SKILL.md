---
name: deep-review
description: >
  Multi-angle adversarial code review graded against a curated lens
  register — for a PR (number or link), a branch, local changes, or as a
  pre-PR self-check. Fans out independent finder agents, verifies every
  candidate finding with a skeptic agent, sweeps for gaps, and reports a
  ranked, evidence-backed finding list. Use when the user says "review PR
  N", "deep review", "/deep-review", or wants a thorough self-check
  before raising a PR.
argument-hint: "[pr-number|branch] [quick|standard|max]"
allowed-tools: Bash, Read, Write, Glob, Grep, Agent
---

# deep-review

Standalone review skill. Everything it needs ships in this directory:

- `references/lens-register.md` — the rule set the review is graded
  against, and its precedence model (universal lenses always apply; the
  backend tier always fires on a backend diff; repo-defined conventions
  govern below that; scoped packs are fallback).
- `references/backend-lenses.md` — the governing backend tier (precedence
  rule 2 of the register): transactions, idempotency, tenancy, caching,
  migrations, exposure bounds. Fires on any backend diff and cannot be
  suppressed by a repo convention.
- `references/agent-briefs.md` — finder/verifier brief templates, the
  subagent hard-rules block, and model-selection guidance.

Read the register's Precedence section before looking at the diff.
Generic judgment alone misses register rules and prescribes fixes the
repo's conventions forbid.

## Mode and effort selection

| Argument | Mode | Diff source |
|---|---|---|
| PR number or link | PR | `gh pr diff <n>` (or platform equivalent) |
| Branch name | Local | `git diff origin/<default>...<branch>` |
| Nothing | Local | `git diff origin/<default>...HEAD` |

Always `git fetch origin <default-branch>` first — a stale local default
branch pollutes the diff with already-merged commits.

**PR mode:** also fetch the PR title/description (scope check) and the
existing comment threads, so findings don't repeat points already raised
or resolved. Judge existing bot/AI review comments on their merits:
endorse the correct ones rather than re-deriving them, and explicitly
flag hallucinated ones (e.g. an invented API parameter) — don't defer to
them. For a stacked PR, diff against the PR's *actual* base branch, not
the default branch.

**Local mode:** the three-dot diff excludes uncommitted work. Check
`git status`; if there are uncommitted modifications, include them
(`git diff HEAD` plus untracked files that belong to the change) and tag
those findings `(uncommitted)`.

Effort (second argument, default `standard`):

| Level | Shape |
|---|---|
| `quick` | One adversarial reviewer, inline. Angles 1 + 12 + 14 merged into a single pass, graded against the universal lenses, the triggered packs, and the backend tier when the diff is backend. No verification fan-out. |
| `standard` | 8 finder agents (angles 1, 2, 3, 5, 9, 11, 12, 14; angle 11 drops out when Phase 0 finds no repo rule sources), plus angle 13 when the diff is backend → dedup → one verifier per surviving candidate. |
| `max` | All 14 angles — angle 13 only when the diff is backend, so 13 otherwise → dedup → one verifier per candidate → gap sweep → ranked report. Recall mode: catching every real defect outranks avoiding false positives. |

Angles 9 and 14 are in `standard` deliberately. A backtest over six human review
rounds found the two largest classes of miss were duplication of existing code
and constructs that never earned their place. Angle 12 already had U1 in scope
at `standard` and the duplicates shipped anyway: one pattern-match sweep across
the whole register reliably skips the lenses that require *running* searches and
reporting what they returned. A census needs an agent whose only job is the
census. The cost is two more mid-tier finders on every run.

## Phase 0 — Gather

1. Resolve mode, fetch, and write the diff to a scratchpad file. The
   diff file is the review scope; agents receive its path, never pasted
   text. Record the base SHA (the PR's base, or the merge-base with the
   default branch) and the worktree path — the agent briefs substitute
   both.
2. Locate the repo's own rule sources: `CLAUDE.md` / `AGENTS.md` /
   `ARCHITECTURE.md`, review runbooks or skills under `.claude/skills/`,
   per-directory convention docs. List their paths — they are handed to
   every agent and they outrank the register's scoped packs.
3. Decide which register packs the diff triggers (each pack states its
   trigger), and record whether the diff is **backend** — the diff touches
   SQL or ORM bindings or repository-layer code, an HTTP endpoint or route, a
   GraphQL schema/resolver/loader, a message or event handler, a schema
   migration file, or cache access. A backend diff fires
   `references/backend-lenses.md` under the register's precedence rule 2, and
   adds angle 13 at `standard` and `max`.
4. **Commit any in-flight work before dispatching agents** — see the
   hard-rules rationale in `references/agent-briefs.md`.

## Phase 1 — Find (`standard` and `max`)

At `quick`, skip Phases 1–3: run one inline adversarial pass yourself —
angles 1, 12, and 14 from the catalog below, graded against the located
rule sources, the universal lenses, the packs the diff triggers, and the
backend tier when the diff is backend — and go straight to Phase 4.

Otherwise, dispatch independent finder agents per angle (render briefs from
`references/agent-briefs.md`; all dispatches for a phase go out in one
message so they run in parallel; pass `model` explicitly on every
dispatch). Do not let one angle's conclusions suppress another's — two
angles flagging the same line for different reasons are two candidates.

Angle catalog:

1. **Line-by-line diff scan.** Every hunk, then the enclosing function —
   bugs on unchanged lines of a touched function are in scope. Inverted
   conditions, off-by-one, null deref, missing await, falsy-zero,
   copy-paste wrong-variable, swallowed errors.
2. **Removed-behavior audit.** For every deleted/replaced line, name the
   invariant it enforced and find where the new code re-establishes it.
   A removed guard, dropped error path, narrowed validation, or deleted
   covering test is a candidate.
3. **Cross-file tracer.** For each changed function, find callers and
   callees; flag call sites broken by new preconditions, changed return
   shapes, new exceptions, ordering dependencies.
4. **Cross-artifact identifier drift.** Enumerate every identifier the
   diff introduces or modifies (fields, env/template variables, flag
   names, enum members, config keys); cross-reference every occurrence;
   flag spelling drift, declared-here-not-there, values outside the
   declared enum.
5. **Interface and contract sweep.** For each external call (API, CLI,
   database, service): pagination handled? assumed fields/types
   guaranteed? required parameters present, named, ordered? documented
   failure modes handled or silently passed through?
6. **Control-flow and containment trace.** For each loop, state machine,
   retry counter, or exception block: trace empty input, no-progress
   input, and unhandled-exception input. For structured content nested
   in a container format (regex in markdown, code in heredocs,
   serialized-in-serialized), check the container's escaping rules. For
   any validator/schema the diff touches, confirm its rules cover every
   form appearing elsewhere in the tree.
7. **Language-pitfall specialist.** The classic footguns of the diff's
   language/framework (closure-captured loop vars, mutable defaults,
   `==` coercion, culture-sensitive formatting, float equality,
   timezone/DST drift, injection).
8. **Wrapper/proxy correctness.** New wrapping types (cache, proxy,
   decorator, adapter) route every method to the wrapped instance — not
   back through a registry/global — and forward everything callers use.
9. **Reuse census.** A mechanical survey, not a judgment. For every file
   the diff adds, run U1's full search list and **report what each search
   returned even when it returned nothing**. An empty census stated
   explicitly is a result; an empty census left unsaid is indistinguishable
   from one that never ran, which is how greppable duplicates survive
   review. Name the existing owner where one exists (register U1–U5).
10. **Simplification and efficiency.** Redundant/derivable state,
    copy-paste variation, dead code, repeated I/O, sequential
    independent work, N+1 loops (U10).
11. **Conventions.** Violations of the repo's own rule sources located
    in Phase 0 — quote the exact rule and the exact line; no
    spirit-of-the-doc inferences.
12. **Lens audit.** The register's universal lenses plus the triggered
    packs, applied per the precedence model. Cite lens ids.
13. **Production failure-mode tracer** (backend diffs only). For each write
    path the diff touches, trace entry point → service → repository →
    cache/bus and answer the backend tier's questions: where the transaction
    begins and ends and what non-database I/O sits inside it, what happens on
    a retried call or a redelivered message, where the tenant scope comes from
    and whether it reaches every query and every cache key, what a rolling
    deploy does to this schema change, what bounds the response, and what a
    cache miss on a hot key costs when the cached shape has changed. Unlike
    angle 12 — a pattern-match pass over the register — this one reads beyond
    the diff. Cite tier ids.
14. **Subtraction and proportionality.** Every other angle asks what is
    missing, wrong, or unguarded, so a construct that is present, correct and
    unnecessary is invisible to all of them — and one that is present, correct
    and over-constraining reads as rigour. This angle asks the opposite
    question. Enumerate every type, interface, provider, wrapper, extension
    class, attribute and constant the diff adds; count each one's production
    call sites; and for each, state what breaks if it is deleted and its body
    inlined (U20). Do the same for guards: for every new precondition,
    assertion, or required-scope check, name what degrades without it — a
    guard whose answer is "nothing degrades, it just commits" is a finding,
    not defence in depth. On a backend diff the transaction case of that
    check is TX6, which angle 13 carries with the rest of the tier; cite it
    only when you have the tier in front of you. Then step back to the whole diff: is it larger than
    the problem requires, and does new test scaffolding — a second test class
    for one subject, new helper files, a documented exception to the repo's own
    rules — exist to work around a constraint this change introduced? Treat
    that scaffolding as evidence about the production design, not as a
    deliverable (T5). Report the root construct, not each symptom.

## Phase 2 — Verify (`standard` and `max`)

1. Dedup candidates pointing at the same line/mechanism; keep the one
   with the most concrete failure scenario.
2. One verifier agent per surviving candidate (brief template in
   `references/agent-briefs.md`): CONFIRMED / PLAUSIBLE / REFUTED.
3. Keep CONFIRMED and PLAUSIBLE. At `max`, a single non-REFUTED vote
   carries the finding — do not drop on uncertainty.
4. Escalate to a top-tier adjudicator only for findings whose verdict
   requires genuine design judgment (contested ownership, architecture).

## Phase 3 — Sweep (`max` only)

One fresh finder that receives the verified list and hunts ONLY for
defects not on it: moved/extracted code that dropped a guard,
setup/teardown asymmetry, config defaults flipped, second-tier footguns.
Up to 8 new candidates; verify them the same way. An empty sweep is a
valid result — do not pad.

## Phase 4 — Report

Assign each finding a severity — **blocker** (security gap, data
corruption, production-reliability risk, breaking contract change),
**important** (correctness/reliability issue worth a discussion; merge
can proceed with an agreed follow-up), or **minor** (mention, never
block). Rank most-severe first; correctness outranks cleanup/convention
findings when a cap forces cuts. Each finding: severity, file, line,
one-sentence claim, concrete failure scenario (or concrete cost),
category, verdict, and the lens/rule citation when one applies.

Close with an overall recommendation — **Approve / Request Changes /
Comment** — where only blocker findings justify Request Changes.
Approving with caveats ("fix in follow-up") is a valid outcome.

- If the host provides a `ReportFindings` tool, call it **once** with the
  ranked list (≤15) and do not also print the findings as prose. If
  reported findings are fixed later in the session, immediately re-call
  it with an `outcome` per finding before any prose summary.
- Otherwise write the report to a scratchpad file and present it,
  leading with the verdict and the top findings.
- **Never post to the PR, push, or mutate review threads unless
  explicitly asked.** The review is a local deliverable by default.

## Maintenance

Follow the register's Maintenance section: repo-specific lessons go to
the repo's own runbook as part of the review; generalizable lessons are
added to `references/lens-register.md` in a deliberate update session.

## Related

`pr-autopilot`'s preflight review consumes `references/lens-register.md` and
`references/backend-lenses.md` when this skill is installed alongside it, and
degrades gracefully when either is absent. Keep both paths stable.
