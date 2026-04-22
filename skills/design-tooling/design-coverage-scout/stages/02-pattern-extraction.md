# Scout Stage 02 — Pattern extraction

## Inputs

- `<run-dir>/stack-profile.json` from stage 1.
- The current repository.

## Objective

For each of the three required hint sections (`01 Flow locator`,
`02 Code inventory`, `03 Clarification`), harvest concrete patterns from this
repo that will be rendered into `platforms/<name>.md` in stage 3. Write
`<run-dir>/hint-draft.json` conforming to
`~/.claude/skills/design-coverage-scout/schemas/hint_draft.json`.

## Durability rule (applies to every section below)

Hint files live in the shared skills repo and are re-used across many runs
against the same stack, months apart. **Describe patterns, not instance
counts.** Do not embed point-in-time tallies like "329 UIViewController hits
across 143 files" or "175 `@Published` hits repo-wide" — these drift as the
repo evolves and turn a hint file stale.

Concretely:

- **Allowed**: ripgrep-ready patterns (`class .*ViewController`,
  `@Composable fun <PascalCase>Screen`), concrete class names that are
  structurally load-bearing (e.g., a base protocol like `Coordinator` at a
  specific path), representative examples ("e.g., `SettingsCoordinator`,
  `MoreCoordinator`").
- **Not allowed**: numeric hit counts, file-count tallies, "X hits repo-wide",
  "N files match" — even approximate. If you need to convey scale, use
  qualitative words ("dominant", "common", "rare") instead.

When in doubt, ask: "would this sentence still be accurate a year from now?"
If a number would be wrong by then, cut the number.

## Method

### For the `flow_locator` section

- Find 1–2 concrete examples of how flows are declared (the file glob, the
  class/decorator name, the route-constant pattern).
- Identify the navigation walker approach (how destinations are listed from a
  starting point).
- Note any refuse-loud conditions specific to this stack.

### For the `code_inventory` section

- Identify the screen-declaration glob (e.g., `class .*Fragment` OR
  `@Composable fun <PascalCase>Screen`).
- Identify the state-container glob (e.g., `class .*ViewModel`).
- Identify the action pattern (e.g., `.clickable { ... }`, `@IBAction`).
- Identify the field-rendering pattern (e.g., `Text(`, `TextView`).
- Identify hybrid-host pattern if one exists.

### For the `clarification` section

- Grep for feature-flag usage pattern name(s).
- Grep for permission-check patterns (`checkSelfPermission`,
  `AVCaptureDevice.authorizationStatus`).
- Grep for server-driven-content markers (network-layer references from UI
  code).
- Grep for responsive/config-branch patterns (`values-night/`, size-class
  checks, media queries).
- Grep for A/B-test hooks.
- Compile a list of topics to ask the human about (what the
  `03 Clarification` section will list).

## Confidence rules

- All three sections harvested ≥ 1 concrete pattern → `confidence: "high"`.
- Some sections empty → `confidence: "medium"` AND add items to
  `unresolved_questions`.
- No section harvested anything → stop, tell the user to author the hint
  manually from `hint-template.md`.

## Output

Write `<run-dir>/hint-draft.json` conforming to the schema. Each
`sections.flow_locator`, `sections.code_inventory`, `sections.clarification`
is a prose string written in hint-file style — imperative voice, concrete
patterns, links to actual tokens in the repo. If any section is below
confidence, populate `unresolved_questions` with specific asks for the curator.
