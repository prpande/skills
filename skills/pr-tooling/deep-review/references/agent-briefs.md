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
<RULE_SOURCE_PATHS — repo conventions first, then the lens register>

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

## Verifier brief template

```
You are verifying ONE candidate finding from a code review. Decide exactly
one verdict: CONFIRMED, PLAUSIBLE, or REFUTED.

<HARD_RULES_BLOCK>

Rule sources (only if your candidate cites one):
<RULE_SOURCE_PATHS>

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
