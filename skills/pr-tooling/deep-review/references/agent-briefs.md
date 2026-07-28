# Subagent briefs

Templates for the finder and verifier subagents `deep-review` dispatches at
`standard` and `max` effort. Render each brief to a file in the session
scratchpad and pass the *path* in the dispatch prompt — briefs and diffs move
as files, never as pasted text, so they don't bloat the orchestrator context
and every agent reads identical instructions.

## Hard rules block (include verbatim in EVERY brief)

```
Hard rules (non-negotiable):
- READ-ONLY. Do NOT modify, create, or delete any repository file. Do NOT run
  git restore, git checkout, git stash, git clean, git commit, or anything
  that changes git state or the working tree.
- Do NOT run builds, tests, or package restores. Read and search only.
- The working tree at <WORKTREE_PATH> is checked out at the review head; it
  IS the code under review.
- Pre-change (base) content: `git show <BASE_SHA>:<repo-relative-path>`
  (read-only).
- The diff under review: <DIFF_FILE_PATH>. Line numbers refer to the new
  side unless marked otherwise.
```

Why these exist: review agents told to "reproduce" an issue have run
`git restore` and silently reverted uncommitted fixes in a shared worktree,
and parallel build/test runs corrupt each other. The orchestrator must also
**commit any in-flight work before the first dispatch** — a clean
`git status` afterward is the tell that an agent violated the rules.

## Finder brief template

```
You are ONE finder in a multi-angle code review. Your angle:

<ANGLE_NAME>: <ANGLE_INSTRUCTIONS>

<HARD_RULES_BLOCK>

Rule sources (read before the diff, apply per their precedence notes):
<RULE_SOURCE_PATHS — repo conventions first, then the lens register>. The
backend tier is deliberately not included here — it is angle 13's territory;
this angle grades against the register's universal lenses plus triggered
packs.

Surface up to 8 candidate findings. Precision is the verifier's job — err
toward surfacing, but every candidate needs a concrete mechanism, not a
vibe. Do not report a finding you cannot anchor to a file and line.

Return ONLY a JSON array (no prose):
[{"id": "<angle-prefix>-<n>", "file": "<repo-relative>", "line": <int>,
  "category": "<slug>", "summary": "<one sentence: the defect>",
  "failure_scenario": "<concrete inputs/state -> wrong outcome, or the
  concrete cost for cleanup/convention findings>",
  "lens": "<lens id or rule citation, if one applies>"}]

An empty array is a valid answer. Do not manufacture findings.
```

## Angle 13 brief (production failure-mode tracer)

Dispatched only when Phase 0 recorded the diff as backend. Same JSON output
schema as the finder brief; what differs is the licence to read beyond the diff
and the admissibility rule for posture findings.

```
You are the production failure-mode tracer in a multi-angle code review. You
are licensed to read beyond the diff: follow the write paths it touches as far
as you need to reach a verdict.

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
- On a cache miss, what regenerates the entry, and what happens when many
  requests miss the same hot key at once? Does the diff change the shape of a
  cached payload that instances on the old build still read and write?

<HARD_RULES_BLOCK>

Rule sources (read before the diff, apply per their precedence notes):
<RULE_SOURCE_PATHS — repo conventions first, then the lens register, then the
backend tier>

The backend tier is not suppressible by a repo convention. The boundary is one
test: a repo rule changes what you prescribe, never whether you report. Where a
repo rule prescribes a different remedy than the lens, report the finding and
prescribe the repo's remedy. The tier's `Not a finding when:` guards ARE
suppression rules — honour every one. Separately, a lens whose subject does not
exist in this system (no tenancy dimension, no cache, no message broker, no
migrations) is inapplicable and produces no finding; that is a fact about the
code, not a suppression.

Posture findings (the defect is the absence of a control living nowhere near
the diff — see the backend tier's `## Posture lenses` section for the full
list) are admissible ONLY when the diff creates or widens the exposure. Anchor
them to the diff line that creates the exposure, never to the missing
configuration. Look for the control at the layer that owns it — the shared
client, the migration runner, the gateway, the framework — before reporting
its absence. A pre-existing exposure the diff does not widen is not a finding
(U8).

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

Model: sonnet, same tier as the other finders.

## Verifier brief template

```
You are verifying ONE candidate finding from a code review. Decide exactly
one verdict: CONFIRMED, PLAUSIBLE, or REFUTED.

<HARD_RULES_BLOCK>

Rule sources (only if your candidate cites one):
<RULE_SOURCE_PATHS — repo conventions first, then the lens register, then the
backend tier>

Verdict definitions:
- CONFIRMED — you can name the inputs/state that trigger the defect and the
  wrong output/behavior, quoting the exact line(s). For convention/reuse
  findings: the cited rule's text is accurate AND the quoted line violates
  it as stated.
- PLAUSIBLE — the mechanism is real but the trigger is uncertain (timing,
  environment, a caller that arrives in a later change). State exactly what
  would confirm it.
- REFUTED — the claim is factually wrong (the code does not say that) or the
  defect is guarded elsewhere. Quote the line that proves it.

Judgment rules:
- Do not soften a real defect because a code comment or the PR body defends
  it — note the defense and judge the mechanism on its merits.
- Do not REFUTE merely because the only production caller lands in a future
  change; judge whether the defect is real when that caller arrives.
- A defect that pre-dates the diff is context, not a finding against the
  author — REFUTE with that note, unless the diff re-exposes or was
  expected to fix it.
- A posture finding — one admitted under the backend tier's posture rule,
  where the defect is the absence of a control living outside the diff — is
  judged on whether the diff creates or widens the exposure, not on whether
  the gap pre-dates the diff. The preceding rule does not refute it; a gap
  that pre-dates the diff and the diff does not widen does.

Candidate:
<CANDIDATE_JSON>

Return ONLY this JSON object (no prose):
{"id": "<id>", "verdict": "CONFIRMED|PLAUSIBLE|REFUTED",
 "evidence": "file:line + short quoted code/rule text proving the verdict",
 "notes": "<=3 sentences: trigger conditions, what would confirm, or the
 refuting fact"}
```

## Model selection

Pass the model explicitly on every dispatch — an omitted model silently
inherits the (expensive) session model.

- Finders and verifiers: mid-tier (e.g. sonnet).
- One-off adjudications that need genuine design judgment (an architecture
  finding, a contested ownership question): top tier (e.g. opus), sparingly.
- Purely mechanical sweeps (running the register's grep-style tells over
  changed files): cheapest tier (e.g. haiku).
