# design-coverage / design-coverage-scout — Platform-agnostic design

**Date**: 2026-04-22
**Author**: Pratyush Pande
**Status**: Design, pending implementation plan

## Summary

Two user-level Claude Code skills that together cover Figma-vs-code design-coverage analysis across any UI stack:

- **`design-coverage`** — compares an existing in-code UI flow against a new Figma design and produces an auditable, confidence-tagged discrepancy report. Same six-stage pipeline and artifact model as the two platform-specific skills it supersedes (MindBodyPOS #5349 for iOS, Express-Android #5190 for Android), but with platform knowledge pushed into optional per-platform hint files under `platforms/<name>.md`. Core stage prompts are LLM-led and platform-agnostic; hints are composed in when available.
- **`design-coverage-scout`** — companion skill that inspects an unfamiliar repository and emits a new `platforms/<name>.md` hint file conforming to the shared template. Invokable standalone for pre-building hints, and invoked inline by `design-coverage` when a user lands on an unknown stack.

Both skills live in this repo under `skills/design-tooling/` (parallel to `skills/pr-tooling/`) and install via the established symlink pattern. The two existing platform-repo PRs will be **closed, not merged**, with their stage-1/2/3 content preserved as the day-one hint files.

## Goals

- **Single skill works on any UI stack.** One install, one command, no repo-specific forks.
- **Preserve hard-won platform wisdom.** iOS's feature-flag patterns, Android's config-qualifier gotchas, hybrid `ComposeView` hosts, and everything else the two existing PRs already captured — move to hint files, don't lose it.
- **Keep the "refuse loudly" discipline** from both existing skills. Silent low-confidence reports are worse than loud halts.
- **Keep the interactive stage-3 discipline** from both existing skills. Human clarifications happen live, never via file handoff.
- **Preserve the source-of-truth model.** JSON artifacts are authoritative; Markdown views are regenerated with `DO-NOT-EDIT` banners and sha256 headers so staleness is detectable.
- **Make adding a new platform cheap.** One Markdown file per platform, shape pinned by a shared template, structural lint gate on CI.
- **Offer a bootstrap path for unknown stacks** via `design-coverage-scout`, so the first run on a new platform doesn't require a human to hand-write a hint.

## Non-goals

- **Not trying to produce platform-specific hints for every known stack on day one.** Ship with `ios` and `android` only; web and others are follow-up work.
- **Not replacing the live human clarification step.** Scout can generate a hint file; it cannot replace the stage-3 Q&A during an actual coverage run.
- **Not locking the hint format to iOS/Android specifics.** The template captures shape (sections, frontmatter, confidence), not content.
- **Not auto-committing hints.** Scout writes drafts, prints previews, requires explicit user approval before moving `.draft` → final. Users commit and push themselves.
- **Not enforcing a specific Figma MCP response-caching policy.** Same deferral as both existing PRs.
- **Not re-deriving stages 4–6.** The Figma inventory, comparator, and report generator from the Android PR are lifted verbatim — they were already platform-agnostic.

## Architecture

Six-stage pipeline for the main skill, three-stage pipeline for scout. Both share the same library code and artifact discipline.

```
~/.claude/skills/
  design-coverage/                         # main skill
    SKILL.md                               # orchestrator + arg parsing + platform resolution
    README.md
    stages/
      01-flow-locator.md                   # platform-agnostic core
      02-code-inventory.md                 # platform-agnostic core
      03-clarification.md                  # platform-agnostic core
      04-figma-inventory.md                # lifted verbatim from Android PR
      05-comparator.md                     # lifted verbatim
      06-report-generator.md               # lifted verbatim
    platforms/
      ios.md                               # day-one hint, ported from MindBodyPOS #5349
      android.md                           # day-one hint, ported from Express-Android #5190
    lib/
      validator.py                         # hand-rolled JSON-Schema validator (Android PR)
      renderer.py                          # JSON → Markdown with sha256 headers
      skill_io.py                          # atomic writes, run-dir helpers, retry tracker
      slugify.py
    schemas/                               # 8 schemas, inventory_item shared via $ref
      inventory_item.json
      run.json                             # +platform, +hint_source, +skill_version
      flow_mapping.json
      code_inventory.json
      clarifications.json
      figma_inventory.json
      comparison.json
      report.json

  design-coverage-scout/                   # companion skill
    SKILL.md
    README.md
    stages/
      01-stack-profile.md
      02-pattern-extraction.md
      03-hint-rendering.md
    hint-template.md                       # structural contract all hints must satisfy
    schemas/
      hint_draft.json
```

Runs land in the **target repo** at `docs/design-coverage/<YYYY-MM-DD>-<flow-slug>/`, same as both existing skills, overridable via `--output-dir`. Scout drafts land at `<skill-install>/platforms/<name>.md.draft` and move to `<name>.md` only on explicit user approval.

## Repository layout in this repo

```
C:/src/skills/
├── skills/
│   ├── pr-tooling/                 (existing)
│   │   ├── pr-autopilot/
│   │   ├── pr-followup/
│   │   └── pr-loop-lib/
│   └── design-tooling/             (NEW)
│       ├── design-coverage/
│       └── design-coverage-scout/
├── skill-tests/                    (NEW top-level; matches memory rule "keep tests out of .claude/")
│   ├── design-coverage/
│   │   ├── conftest.py
│   │   ├── tests/
│   │   └── fixtures/
│   └── design-coverage-scout/
│       ├── conftest.py
│       ├── tests/
│       └── fixtures/
├── docs/
│   └── superpowers/
│       ├── specs/2026-04-22-design-coverage-platform-agnostic-design.md     (this file)
│       └── plans/2026-04-22-design-coverage-platform-agnostic.md            (to be written)
├── scripts/
│   └── validate.py                 (extended: SKILL.md walker + hint-frontmatter lint)
├── prompts/                        (existing)
└── README.md                       (updated: both new skills added to table)
```

## Locked design decisions

| #  | Decision                                                                          |
|----|-----------------------------------------------------------------------------------|
| D1 | **Hybrid architecture** — platform-agnostic LLM-led core + optional hint files.  |
| D2 | **Day-one hints: iOS + Android only.** Web deferred to a follow-up.              |
| D3 | **Unknown stack → live prompt + flag escape.** Three options in prompt: generate (scout), name a platform, or proceed agnostic. `--platform <name>` flag skips prompt. |
| D4 | **Output dir: default target repo's `docs/design-coverage/...`,** `--output-dir` overrides. |
| D5 | **Both existing PRs closed, not merged.** This skill supersedes them.            |
| D6 | **One hint file per platform, sectioned by stage.** Marker-substituted into core stage prompts at `<!-- PLATFORM_HINTS -->`. |
| D7 | **Scout ships as a peer skill, invokable standalone and internally.**            |
| D8 | **Scout's methodology lives inline in its stage prompts,** not as excerpts from the iOS/Android specs. A structural `hint-template.md` captures hint shape. |
| D9 | **Scout writes drafts, not finals.** Explicit user approval required; no auto-commit. |
| D10| **Tests live at `skill-tests/` at the repo root,** not inside the symlinked skill dirs. |

## Invocation

```
/design-coverage <figma-url> [--old-flow <hint>] [--platform <name>] [--output-dir <path>]
/design-coverage-scout [--platform-name <name>] [--force]
```

### Arguments for `design-coverage`

| Arg              | Required | Purpose                                                              |
|------------------|----------|----------------------------------------------------------------------|
| `<figma-url>`    | yes      | Figma design URL; parsed into `fileKey` + `nodeId`.                 |
| `--old-flow`     | no       | String hint to disambiguate flow detection in stage 1.              |
| `--platform`     | no       | `ios` / `android` / `agnostic` / (future) other hint names.         |
| `--output-dir`   | no       | Override default artifact path.                                      |

### Arguments for `design-coverage-scout`

| Arg                 | Required | Purpose                                                            |
|---------------------|----------|--------------------------------------------------------------------|
| `--platform-name`   | no       | Name to use for the generated hint file. If omitted, derived from detected stack. |
| `--force`           | no       | Overwrite an existing `platforms/<name>.md` without draft gating.  |

### Platform resolution flow

Happens in the main skill before stage 1:

1. If `--platform <name>` provided → honor it. `agnostic` skips hint loading entirely.
2. Else glob each existing `platforms/*.md` frontmatter `detect` pattern against CWD:
   - Exactly one matches → proceed with that hint; log detection in `00-run-config.json`.
   - Multiple match (e.g., monorepo) → refuse, list matches, require `--platform`.
   - None match → **unknown-stack** branch below.
3. Unknown stack → single live prompt in the main session:
   > "Detected stack doesn't match any existing hint. Choose: (a) generate a hint for this stack now (runs `design-coverage-scout`), (b) name a platform from [ios, android], (c) proceed agnostic."
4. Answer stamped into `run.json` under `platform` + `hint_source` (`detection` | `flag` | `user-prompt` | `scout-generated` | `agnostic`).

## Hint contract

Each hint is one Markdown file at `design-coverage/platforms/<name>.md`. Must satisfy the template at `design-coverage-scout/hint-template.md`:

```markdown
---
name: <platform-name>
detect:
  - "<glob that signals this platform>"
description: One-line summary of the platform this hint covers.
confidence: high | medium | low
---

## 01 Flow locator
<platform-specific guidance for finding the flow entry point and walking
 navigation>

## 02 Code inventory
<platform-specific guidance for enumerating screens / states / actions /
 fields>

## 03 Clarification
<list of platform-specific hotspot topics for stage-3 Q&A>

## Unresolved questions (optional)
<items the hint author was unsure about; emitted by scout when confidence
 < high; human resolves before removing the section>
```

### Marker substitution

Each of `stages/01-flow-locator.md`, `02-code-inventory.md`, `03-clarification.md` ends with:

```markdown
<!-- PLATFORM_HINTS -->
```

At invocation, the orchestrator reads the matching section from `platforms/<resolved>.md` and substitutes it under a `## Platform-specific hints (<name>)` heading. In agnostic mode, the marker is removed and the core prompt stands alone. The fully-composed prompt is persisted to `<run-dir>/<stage>-prompt.md` for auditability — no cross-file reads inside the subagent.

Stages 4–6 do not carry the marker; they are platform-agnostic end-to-end.

## Core stage prompts (main skill)

All three carry the `<!-- PLATFORM_HINTS -->` marker. Prompt voice is neutral — "the navigation entry point for this flow," not "the `ViewController`."

**01 — Flow locator.** Given a Figma frame set and optional `--old-flow` hint, locate the existing flow: (1) find entry screen by name correspondence, (2) enumerate reachable destinations by walking the stack's navigation structure, (3) emit `flow_mapping.json`. Refuse on all-default-named Figma frames. Refuse if no entry point locates with confidence.

**02 — Code inventory.** For each screen in the flow, enumerate `inventory_item` rows (screens, states, actions, fields) via ripgrep discovery → focused LLM reads → cross-linking. Screens may be one or many files (hybrid hosts exist on some stacks — hint describes them). Emit `code_inventory.json`. Orphaned items preserved, never silently dropped.

**03 — Clarification.** Identify hotspots — decision points whose rendered state depends on runtime data (flags, permissions, responsive config, roles, server-driven content). Ask the human live in-session. Short-circuit to `{"resolved": []}` on empty hotspot list.

**04 / 05 / 06** — lifted verbatim from the Android PR.

## Scout's pipeline

Scout mirrors the main skill's stage scaffolding with a different target:

- **01 — Stack profile.** Enumerate language, build system, UI framework, navigation style, state-container convention. Refuse if the repo is a mix (e.g., both iOS and Android trees at top level). Emit `stack-profile.json`.
- **02 — Pattern extraction.** For each hint-template section, harvest concrete patterns from the repo — file globs, representative snippets, hotspot-topic evidence. Emit `hint-draft.json` with per-section confidence.
- **03 — Hint rendering.** Render `<symlink-target>/../design-coverage/platforms/<name>.md.draft` using `hint-template.md` as the shape contract. Print a preview in the live session. On user approval, move `.draft` → `<name>.md`. Below-medium confidence on any required section forces the draft gate.

Scout's stage prompts carry the investigative methodology inline — *platform-agnostic* guidance about what signals to look for when characterizing a UI stack (nav framework shape, screen-unit declaration conventions, feature-flag/permission/responsive-branch patterns, hybrid-host patterns). Nothing quoted from the two existing spec docs.

### Symlink-aware write target

Scout resolves its own install path with `os.path.realpath(__file__)` and writes drafts to `../design-coverage/platforms/<name>.md` relative to the resolved source dir. Installed via symlink → drafts land in this repo for sharing. Installed via copy → drafts land in `~/.claude/skills/design-coverage/platforms/`; scout prints a one-line notice that the user should copy the file to the shared repo clone and commit.

## Data model & schemas

Eight schemas survive from the Android PR. `inventory_item.json` remains shared between `code_inventory.json` and `figma_inventory.json` via `$ref`. The hand-rolled validator is carried over unchanged.

### Run config artifact (day-one shape)

The orchestrator writes a single run-config artifact to the run dir on init,
named `00-run-config.json`:

```jsonc
{
  "figma_url": "<from args>",
  "old_flow_hint": "<from args or null>",
  "platform": "ios | android | agnostic | <hint-name>",
  "hint_source": "detection | flag | user-prompt | scout-generated | agnostic",
  "skill_version": "<git-sha-of-C:/src/skills>"
}
```

`hint_source` makes every run honest about the basis of its report.

The ported `run.json` schema (from the Android PR) additionally carries a
`stages["1"…"6"].status` block for stage-level resume. On day one the
orchestrator does **not** write `run.json` to disk — stage resume is
artifact-based (skip stages whose output file exists in the run dir).
Restoring stage-status persistence to `run.json` is a known follow-up
(see Known limitations).

### Scout-only schema

`hint_draft.json` — intermediate state between scout's stage-2 pattern extraction and stage-3 hint rendering. Holds per-section harvested patterns, confidence, and "unresolved questions" items.

## Error handling — refuse-loud triggers

### Carried over from both PRs

- Stage 1 — all Figma frames default-named → refuse.
- Stage 1 — no flow entry point locatable with confidence → refuse, suggest `--old-flow`.
- Stage 3 — zero hotspots → short-circuit, not error.
- Stage 5 — missing `pass`/`severity` on any comparison row → schema rejects; stage retries.
- Stage 6 — orphaned inventory items → rendered under explicit "Orphaned items" section.

### New for this skill

- **Multiple hint `detect` patterns match CWD** → refuse, list matches, require `--platform`.
- **Hint file fails frontmatter validation** (missing `name`, `detect`, required sections, malformed `confidence`) → refuse before stage 1; point user at `hint-template.md`.
- **Scout refuses to overwrite** an existing hint without `--force`.
- **Scout's confidence < `medium`** on any required section → draft gate always, regardless of `--force`.

## Testing strategy

Tests live at `skill-tests/` at the repo root (not under the symlinked skill dirs). Both skills conform to the existing `scripts/validate.py`.

### Day-one test targets

- **`design-coverage`**: ~60 pytest cases.
  - All existing Android PR tests ported (50).
  - New: `test_platform_detection.py`, `test_hint_injection.py`, `test_agnostic_mode.py`, `test_hint_frontmatter.py`, `test_multi_hint_refuse.py`.
  - Fixtures: `detection/` (pure-ios, pure-android, ambiguous, unknown mini-repos), `hint-injection/` (core+hint → expected composed prompt), `platforms/` (the real ios.md and android.md under shape test).
- **`design-coverage-scout`**: ~25 pytest cases.
  - New: `test_stack_profile.py`, `test_pattern_extraction.py`, `test_hint_rendering.py`, `test_hint_template_shape.py`, `test_refuse_overwrite.py`.
  - Fixtures: `stacks/` (tiny-ios, tiny-android, tiny-react mini-repos), `rendered-hints/` (expected `platforms/<name>.md` for each stack).

### Conformance

Both skills pass `python scripts/validate.py`. Validator extended to:

1. Walk every `skills/*/*/SKILL.md` (not just the specific pr-tooling set currently encoded).
2. Lint all `design-coverage/platforms/*.md` against the frontmatter + section-header contract.

### What we don't test

LLM subagent output quality. Tests pin orchestration — what gets written, what schemas are satisfied, what refusal triggers fire. Subagent quality is verified by dogfood runs (see Known limitations).

## Installation

```bash
# From a C:/src/skills clone:
ln -s "$PWD/skills/design-tooling/design-coverage"        "$HOME/.claude/skills/design-coverage"
ln -s "$PWD/skills/design-tooling/design-coverage-scout"  "$HOME/.claude/skills/design-coverage-scout"

# Windows cmd:
# mklink /D %USERPROFILE%\.claude\skills\design-coverage        %CD%\skills\design-tooling\design-coverage
# mklink /D %USERPROFILE%\.claude\skills\design-coverage-scout  %CD%\skills\design-tooling\design-coverage-scout
```

Restart the Claude Code session; both appear in `/<list>`.

## Rollout sequence

Single PR to `C:/src/skills`, sequenced internally as reviewable commits:

1. `scripts/validate.py` generalization + hint-frontmatter lint rule.
2. `skills/design-tooling/design-coverage/` skeleton — SKILL.md, stages (core prompts), lib/, schemas/, empty `platforms/`.
3. `skill-tests/design-coverage/` — all ported Android tests + new platform-resolver/hint-injection/agnostic cases. All passing.
4. `skills/design-tooling/design-coverage/platforms/ios.md` — content ported from MindBodyPOS #5349.
5. `skills/design-tooling/design-coverage/platforms/android.md` — content ported from Express-Android #5190.
6. `skills/design-tooling/design-coverage-scout/` skeleton + `hint-template.md`.
7. `skill-tests/design-coverage-scout/`.
8. `README.md` updates at repo root — add both skills to the table, add install lines, add design-doc/plan links.
9. `docs/superpowers/specs/` and `docs/superpowers/plans/` — this file and the forthcoming plan.

No dogfood run blocks the PR. A smoke run on one prior modernization happens before internal announcement.

## Migration

### Closing the two existing PRs

Both PRs (#5349 MindBodyPOS, #5190 Express-Android) close with a comment linking to the new skills-repo PR and noting that:

- Content from their `stages/01-flow-locator.md`, `stages/02-code-inventory.md`, `stages/03-clarification.md` is preserved as `platforms/ios.md` / `platforms/android.md`.
- The spec docs at `docs/superpowers/specs/2026-04-14-design-coverage-process-design.md` (iOS) and `docs/superpowers/specs/2026-04-14-design-coverage-android-design.md` (Android) were the methodological reference for this skill but are **not imported**. The methodology is restated in platform-neutral form inside the new skills' own stage prompts.
- Install moves to the shared skills repo going forward.

### Branches

Remain on both platform repos for 60 days, then get deleted. No code was merged to `develop` from either branch; no further cleanup is required.

### Team communication

A short note to the iOS and Android teams (Slack or equivalent) announcing the move, the install command, and the day-one supported platforms — **not part of this PR**, a follow-up action item.

## Known limitations / future work

- **No web hint on day one.** Users on React / Vue / Angular / Next.js fall through to agnostic-mode or run scout. Web hint is the highest-priority follow-up.
- **No Figma MCP response caching.** Same deferral as both existing PRs; load-bearing for iteration speed on large flows.
- **No automated dogfood run in CI.** Same as both existing PRs. Smoke runs are a manual check before internal announcement.
- **Scout can refuse to profile exotic stacks.** If stage-1 can't characterize the UI layer at all, it refuses and points the user at `hint-template.md` for manual authoring.
- **`skill_version` is a git SHA, not a semver tag.** Fine for this repo's pattern; may want semver later.
- **Day-one schemas retain Android-specific field names and enum values** — inherited from the verbatim port of stages 4–6. Specifically:
  - `flow_mapping.json` requires `mappings[].android_destination`; iOS runs populate this Android-named field without apology.
  - `report.json` uses `matrix[].android_screen` for the code-side column; same.
  - `inventory_item.json` `source.surface` enum is `[compose, xml, hybrid, nav-xml, nav-compose]` — Android-only; iOS runs emit the nearest match (typically `compose` for SwiftUI and `xml` for UIKit/storyboard/XIB) until the enum is generalized. Platform-neutral rename to `{destination, code_screen, surface ∈ open-string}` (or a platform-union enum) is a follow-up tracked with the other schema-rename tasks below.
- **`code_inventory.json` requires `unwalked_destinations`.** Only the Android nav-graph walk produces meaningful entries; iOS runs emit `[]`. Relaxing to optional or renaming to a platform-neutral "unmatched Figma frames" concept is follow-up.
- **Stage resume is artifact-based, not status-tracked.** The ported `run.json` schema ships with a stages-status block but nothing writes the file on day one. Artifact-presence (does `01-flow-mapping.json` exist in the run dir?) is the sole resume signal. Restoring persistence is follow-up.
- **Schemas follow the Android PR's shape, not the iOS PR's.** Two architecturally different data models exist across the two source PRs: Android embeds `hotspot: {type, question}` per `inventory_item` and uses `flow_mapping.json` keyed on `{locator_method, confidence, mappings[]}`; iOS uses a top-level `hotspots[]` array with items referencing via `related_hotspot`, and `flow_mapping.schema.json` keyed on `{status, detected_flow, old_flow_entry_points, figma_frames}`. This PR inherits the Android shape verbatim for lib, schemas, and stages 4-6. Switching to the iOS shape (which is the better-tested of the two) is a potential follow-up but out of scope here — it would require rewriting schemas, stages, renderer, fixtures, and tests.

## Open questions

None. All locked in D1–D10.
