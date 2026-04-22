# Repo layout: type-first reorganization

**Date:** 2026-04-22
**Status:** Approved design, implementation plan present, implemented
**Author:** @prpande

## Problem

The repo currently holds three skill-ish directories flat at the root
(`pr-autopilot/`, `pr-followup/`, `pr-loop-lib/`) alongside `docs/`,
`scripts/`, and `README.md`. The flat shape works today because every
artifact happens to be PR tooling — the root is thematically coherent
by accident.

The repo is intended to grow into a small shareable library of AI
tooling artifacts (skills, prompts, and eventually other types) that
users can install individually without each artifact needing its own
repo. The first non-PR artifact (`prompts/attention-status-page.md`)
has just landed. Without an organizing principle, the root will
accumulate mixed top-level entries and become hard to scan.

## Organizing principle

**Group top-level directories by artifact type (the installable unit
kind), not by theme.** Theme-based grouping (e.g., "pr-tooling")
applies *inside* a type folder when, and only when, two or more
related artifacts exist together.

Rationale: artifact types have distinct install stories
(skills symlink into `~/.claude/skills/`, prompts are pasted into a
conversation, etc.). Type is the most stable axis. Themes come and go.

## Target layout

```
/
├── README.md
├── scripts/
│   └── validate.py
├── docs/
│   └── superpowers/
│       ├── specs/
│       └── plans/
├── skills/
│   └── pr-tooling/
│       ├── pr-autopilot/
│       ├── pr-followup/
│       └── pr-loop-lib/
└── prompts/
    └── attention-status-page.md
```

Five top-level entries. Each serves one clear purpose:

- `README.md` — repo overview, index of artifacts, install instructions.
- `scripts/` — repo-local tooling (currently just `validate.py`).
- `docs/` — design docs and plans, following the superpowers
  convention (`docs/superpowers/specs/`, `docs/superpowers/plans/`).
- `skills/` — installable Claude Code skills.
- `prompts/` — standalone prompt files users paste into a conversation.

## Decisions and rationale

### D1 — Scope of types to accommodate now: skills + prompts only

Other types (plugins, MCP servers, etc.) are hypothetical. Top-level
folders get created when a real artifact needs them, not in
anticipation. YAGNI.

### D2 — PR trio grouped under `skills/pr-tooling/` umbrella

`pr-autopilot`, `pr-followup`, and `pr-loop-lib` are genuinely related:
both skills import `pr-loop-lib`, and all three revolve around the
PR feedback loop. A `pr-tooling/` umbrella folder reflects that
coupling on the repo side.

The umbrella is a **repo-side organizational device only**. The
installed layout under `~/.claude/skills/` stays flat — each of the
three remains an independently installable unit. No reference
rewiring between the skills is required, because they reference
each other through `~/.claude/skills/pr-loop-lib/...` paths, not
through repo-relative paths.

Nesting `pr-loop-lib` literally inside `pr-autopilot/lib/` was
considered and rejected: it would force `pr-followup` to depend on
`pr-autopilot` being installed, breaking independent installability.

### D3 — Design docs stay central at `docs/superpowers/`

The superpowers tooling expects specs and plans at
`docs/superpowers/specs/` and `docs/superpowers/plans/` relative to
the repo root. Colocating design docs under each skill cluster would
fight that convention for no concrete win at current scale.

### D4 — `validate.py` walks `skills/**` dynamically

Today the validator hardcodes
`SKILL_ROOTS = ["pr-autopilot", "pr-followup", "pr-loop-lib"]`.
After the move, rewrite the discovery step to walk `skills/**` and
treat every directory that directly contains one or more `.md`
files as a skill root. Directories that contain only subdirectories
(umbrellas like `pr-tooling/`) are transparent — the walk descends
through them. This rule naturally covers both real skills (which
have `SKILL.md` plus step/reference files) and skill-support libs
like `pr-loop-lib` (which has step/reference files but no
`SKILL.md`). Adding a new skill then requires zero validator edits.

The existing `SKILL.md` frontmatter check remains file-level: it
fires only when a file named `SKILL.md` exists. Non-skill dirs with
only other markdown files (like `pr-loop-lib/`) are unaffected.

Reference resolution inside skills must continue to support:
- skill-root-relative references (`steps/...`, `references/...`,
  `platform/...`),
- repo-relative references that start with a skill folder name
  (`pr-autopilot/...`, `pr-followup/...`, `pr-loop-lib/...`),
- home-ref references (`~/.claude/skills/<skill>/...`).

After the move the repo-relative form still works because the
deepest path component (the skill folder name) is what references
use — the umbrella folder is transparent to references. The
validator's skill-root-name lookup needs to be updated to search
by name anywhere under `skills/**`, not only at the repo root.

### D5 — README install instructions use explicit verbose paths

Each install line shows the full repo-side path explicitly:

```bash
ln -s "$PWD/skills/pr-tooling/pr-autopilot"  "$HOME/.claude/skills/pr-autopilot"
ln -s "$PWD/skills/pr-tooling/pr-followup"   "$HOME/.claude/skills/pr-followup"
ln -s "$PWD/skills/pr-tooling/pr-loop-lib"   "$HOME/.claude/skills/pr-loop-lib"
```

Three skills do not justify a helper script. Revisit if the count
crosses ~6–8.

## Growth guidance

- **New standalone skill** (unrelated to existing clusters):
  `skills/<skill-name>/`, as a peer to `pr-tooling/`. No umbrella
  until a second related skill appears.
- **New related skill pair or trio:** introduce an umbrella folder
  at that point (e.g., `skills/code-review/`). Do not preemptively
  umbrella a single skill.
- **New prompt:** flat in `prompts/`. If prompts grow past ~8–10 and
  cluster thematically, introduce subfolders at that time — not
  before.
- **New artifact type** (plugin, MCP server, etc.): new top-level
  folder when a real artifact arrives.

## Migration mechanics

Moves required:

- `pr-autopilot/`   → `skills/pr-tooling/pr-autopilot/`
- `pr-followup/`    → `skills/pr-tooling/pr-followup/`
- `pr-loop-lib/`    → `skills/pr-tooling/pr-loop-lib/`

Use `git mv` so history is preserved.

Files that need editing after the move:

- `scripts/validate.py` — update `SKILL_ROOTS` logic (see D4).
- `README.md` — update install commands (see D5) and rewrite the
  skills table to reference the new paths under
  `skills/pr-tooling/`. The `Prompts` section already exists on
  main and does not need to change.

Files that should **not** need editing:

- Skill internals (`SKILL.md`, step files, references). They use
  skill-root-relative or home-ref paths, both of which survive
  the move. The validator must continue to resolve these
  correctly.

## Out of scope

- Renaming any of the three PR artifacts.
- Changing `~/.claude/skills/` install target or layout.
- Adding new artifact types or new skills in this change.
- Building an install helper script.
- Reorganizing internals of `pr-loop-lib`, `pr-autopilot`, or
  `pr-followup`.

## Validation after the move

1. `python scripts/validate.py` prints `OK`.
2. Symlinking each of the three skill paths into
   `~/.claude/skills/` results in the same installed layout as
   before (sanity check the install instructions).
3. Skill-internal references (grep for `steps/`, `references/`,
   `platform/`, `pr-autopilot/`, `pr-followup/`, `pr-loop-lib/`,
   and `~/.claude/skills/`) all still resolve per the validator.
