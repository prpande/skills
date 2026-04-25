# design-coverage — Improvements spec (waves 1-3)

**Date:** 2026-04-25
**Author:** Pratyush Pande
**Status:** Design, pending implementation plan
**Repo:** `prpande/skills`
**Worktree:** `C:/src/skills-design-coverage-improvements` on branch `pratyush/design-coverage-improvements`

## Summary

The `design-coverage` skill works correctly today but produces **inconsistent reports between runs** and **only installs cleanly under `~/.claude/skills/`**. A side-by-side comparison of two runs against the same Figma + same code (2026-04-14 vs 2026-04-25) found 8 errors in one run vs 2 hard fails in the other, with substantially different cluster groupings and severity calls. The drift is methodological, not implementation drift.

This spec proposes 11 improvements grouped into 3 waves. Each wave ships as a single GitHub issue against `prpande/skills` so future agent sessions can pick up an issue cold and ship the work in a parallel PR. Wave 4 (differential mode, lessons-learned feedback loop) is explicitly deferred — those introduce new commands and deserve their own brainstorm.

The single biggest design improvement is a cross-cutting one: **sealed-enum-driven platform-hint frontmatter**. Today, "what counts as a permission hotspot" is agent-judgment per stage; tomorrow, it is hint-file data the scout populates per platform. This collapses ~80% of the run-to-run drift into one declarative file per platform.

## Goals

- **Make reports reproducible across runs.** Two agents running the skill on the same Figma + same code should produce reports that differ only in narrative prose, not in error counts, severity calls, or cluster groupings.
- **Make the skill installable anywhere.** `~/.claude/skills/`, an in-repo `.claude/skills/`, a plugin-installed location — all should work without code changes.
- **Make adding a new platform mechanical, not magical.** A new `platforms/<name>.md` file with declared sealed-enum patterns is enough; the agent does not have to learn the platform's idioms inline.
- **Preserve every refuse-loud invariant** the skill ships with today. None of these improvements weaken any existing safety check.

## Non-goals

- **Not introducing new pipeline commands.** Differential mode (`--compare-against`) and lessons-learned feedback persistence are deferred to wave 4 (separate brainstorm).
- **Not changing the artifact-as-source-of-truth model.** JSON files stay authoritative; Markdown views regenerate with sha256 headers.
- **Not auto-detecting `default_in_scope_hops`** or other policy values. Scout populates pattern-detection results; policy values keep their hand-set defaults.
- **Not breaking existing run-dir artifacts.** New schema additions are additive; existing `00-run-config.json` files from prior runs continue to load (with new fields defaulting).

## The cross-cutting design — sealed-enum-driven hint frontmatter

The skill defines several sealed enums in its schemas. Four of them (`hotspot.type`, `inventory_item.kind`, `inventory_item.source.surface`, `unwalked_destinations.reason`) require **platform-specific code patterns** to be useful. Today the patterns live as prose under stage sections in each `platforms/<name>.md`. Promote them to structured frontmatter so:

1. **Stage 02** can mechanically iterate enum values and grep for each platform's patterns instead of asking the agent to recall idioms.
2. **Stage 03** can deterministically emit one Q per `hotspot.type` value that has any matches in stage 02.
3. **The scout** can detect each enum value's patterns when generating a hint for a new platform.

**Frontmatter shape:**

```yaml
---
name: ios
detect: ["**/*.xcodeproj", "**/*.xcworkspace", "Package.swift"]

# Wave 2 — new top-level fields
multi_anchor_suffixes: ["New", "V2", "Legacy", "Old", "Modern"]
default_in_scope_hops: 2
hotspot_question_overrides: {}

# Wave 2 — sealed-enum-driven patterns
sealed_enum_patterns:
  hotspot.type.feature-flag:
    grep: ["FeatureFlagType\\.", "ImplementationSwitch\\.", "FeatureFlagManager\\."]
    description: "iOS feature-flag branches (compile-time + runtime)"
  hotspot.type.permission:
    grep: ["staff\\.can[A-Z]", "user\\.hasRole\\(", "AVCaptureDevice\\.authorizationStatus", "CLLocationManager", "UNUserNotificationCenter", "PHPhotoLibrary"]
    description: "Staff permissions + system permission gates"
  hotspot.type.server-driven:
    grep: ["response\\.items", "response\\.sections", "JSONDecoder\\(\\)\\.decode"]
  hotspot.type.view-type:
    grep: ["dequeueReusableCell.*withReuseIdentifier", "switch.*\\.status\\b", "switch.*\\.paymentStatus\\b"]
  hotspot.type.form-factor:
    grep: ["UIDevice\\.current\\.userInterfaceIdiom", "horizontalSizeClass", "traitCollection\\.userInterfaceStyle"]
  hotspot.type.process-death:
    grep: ["NSUserActivity", "restorationID", "stateRestorationActivity"]
  hotspot.type.sheet-dialog:
    grep: ["UIAlertController", "\\.sheet\\(isPresented:", "\\.fullScreenCover\\(", "\\.popover\\("]
  inventory_item.kind.screen:
    grep: ["class \\w+ ?: ?UI(View|TableView|CollectionView|Page)Controller", "struct \\w+ ?: ?View\\b", "class \\w+Coordinator\\b"]
  inventory_item.kind.action:
    grep: ["@IBAction", "addTarget\\(self", "Button\\(action:", "\\.onTapGesture", "performSegue\\(withIdentifier:"]
  inventory_item.kind.field:
    grep: ["\\.text ?=", "\\.attributedText ?=", "\\.image ?=", "Text\\(", "Label\\("]
  inventory_item.source.surface.compose:
    grep: ["struct \\w+ ?: ?View\\b"]
    description: "SwiftUI view"
  inventory_item.source.surface.xml:
    grep: ["\\.storyboard\\b", "\\.xib\\b"]
    description: "Storyboard / XIB"
  inventory_item.source.surface.hybrid:
    grep: ["UIHostingController", "UIViewControllerRepresentable", "UIViewRepresentable"]
  unwalked_destinations.reason.platform-bridge:
    grep: ["UIHostingController\\(rootView:", "UIViewControllerRepresentable"]
    description: "SwiftUI <-> UIKit bridges"
  unwalked_destinations.reason.adapter-hosted:
    grep: ["Adapter\\.\\w+\\(", "Bridge\\.\\w+\\("]
  unwalked_destinations.reason.dynamic-identifier:
    grep: ["instantiate.*WithIdentifier:", "Selector\\(\"\\)"]
---

## 01 Flow locator
(prose continues unchanged for human readability)
```

The prose under stage sections stays — humans read it, agents fall back to it for items the structured frontmatter doesn't cover. The structured frontmatter is the **machine-actionable index**.

The scout's `stages/02-pattern-extraction.md` walks each enum value (provided by a new `lib/sealed_enum_index.py`) and produces candidate `grep:` lists by inspecting the unfamiliar codebase.

---

## Wave 1 — Methodology-drift killer (this session)

Single GH issue. Implements the highest-leverage drift fixes plus the lightest piece of universal-reuse infrastructure (skill-relative paths). Self-contained PR.

### #1 — Hotspot question registry

**Problem.** Stage 03 today asks free-form questions invented by the agent. Two agents on the same code produce different question sets (the 2026-04-14 run had 12 sharp Qs; the 2026-04-25 run had 4 batched Qs). Hard fails surface in one run and not the other.

**Design.** A new `lib/hotspot_questions.py` module exposes:

```python
HOTSPOT_QUESTIONS: dict[str, QuestionTemplate] = {
    "feature-flag": QuestionTemplate(
        template="Treat the {symbol} branch as on, off, or both for this audit?",
        default_answer="on",
        severity_if_violated="error",
        applies_when_count_gte=1,
    ),
    "permission": QuestionTemplate(
        template="Assume {symbol} is granted unless a Figma frame explicitly shows the denied state?",
        default_answer="granted",
        severity_if_violated="warn",
        applies_when_count_gte=1,
    ),
    "view-type": QuestionTemplate(
        template="Must Figma cover all {N} variants of {symbol}?",
        default_answer="yes",
        severity_if_violated="error",
        applies_when_count_gte=2,
    ),
    # ... one entry per hotspot.type enum value
}

def emit_questions_for_inventory(inventory: dict, platform_overrides: dict) -> list[Question]:
    """Mechanically enumerate distinct hotspot symbols, look up the template,
    apply platform overrides if any, return one Question per distinct symbol."""
```

Platform hints can override per-platform via the `hotspot_question_overrides:` frontmatter field (cross-cutting design above).

**Stage 03 change.** Replace the free-form "ask about hotspots" prose with: "call `emit_questions_for_inventory(stage2_inventory, platform_overrides)`, then ask each Question via the live in-session interactive interface, never via file handoff."

**Definition of done.**
- `lib/hotspot_questions.py` exists with one entry per `hotspot.type` enum value.
- `stages/03-clarification.md` invokes it instead of free-form prose.
- Two consecutive runs of the skill on the same code + Figma produce **identical question sets** (verifiable in `03-clarifications.json`).

### #2 — Severity decision matrix

**Problem.** Stage 05 today has prose rules for severity ("error if user-noticeable workflow loss"). Two agents read the same prose and pick different severities for the same row (Resource Picker = error in one run, warn in another).

**Design.** A new `lib/severity_matrix.py` module exposes:

```python
SEVERITY_MATRIX: dict[tuple[str, str, str | None, str | None], str] = {
    # (status, kind, hotspot_type, clarification_answer) -> severity
    ("missing", "screen", None, None): "error",
    ("missing", "action", "view-type", "all_variants_required"): "error",
    ("missing", "action", "permission", "granted"): "info",
    ("restructured", "screen", None, None): "warn",
    ("present", None, None, None): "info",
    ("new-in-figma", None, None, None): "info",
    # ...
}

def lookup(status: str, kind: str | None, hotspot_type: str | None,
           clarification_answer: str | None) -> str:
    """Return severity for the row; warn fallback for unknown tuples."""
    key = (status, kind, hotspot_type, clarification_answer)
    if key in SEVERITY_MATRIX:
        return SEVERITY_MATRIX[key]
    _record_miss(key)
    return "warn"
```

Misses are appended to `<run_dir>/_severity_lookup_misses.json` (the only allowed `_*.json` file at the run-dir top level — see #11 for the scratch policy). After each run, the developer can audit misses and add explicit entries.

**Stage 05 change.** Replace the inline severity reasoning with calls to `severity_matrix.lookup(...)`. The comparator's job is to compute `(status, kind, hotspot_type, clarification_answer)` for each row; severity is a pure lookup.

**Definition of done.**
- `lib/severity_matrix.py` exists with at least one entry per `status × kind` combination.
- `stages/05-comparator.md` calls `lookup()` for every row's severity.
- Lookup misses land in `_severity_lookup_misses.json`.
- Two runs on the same comparator inputs produce **identical severity calls**.

### #3 — Out-of-scope as an explicit question

**Problem.** Stage 02 today silently classifies destinations as in-scope or out-of-scope based on agent judgment. The 2026-04-14 run silently put `MBOApptQuickBookViewController` (the Modify flow) into `unwalked_destinations` with reason `out-of-scope-destination`; the 2026-04-25 run kept it in scope and emitted three errors. Same code, opposite calls.

**Design.** Three coordinated changes:

1. **Schema change.** `code_inventory.json`: `unwalked_destinations[].reason` becomes a closed enum with values `adapter-hosted | external-module | swiftui-bridge | dynamic-identifier | platform-bridge`. The string `out-of-scope-destination` is **invalid** and the validator rejects it.

2. **New schema field.** `code_inventory.json`: add `candidate_destinations: [{symbol, file, hop_distance, why_not_walked}]` (not closed enum on `why_not_walked` — free-form rationale). This is where stage 02 emits things it judged "maybe in scope, not sure" instead of silently in-scoping or out-of-scoping.

3. **Stage 03 question.** For each parent screen with non-empty `candidate_destinations`, emit ONE multi-select question:

   > "Reachable from `{parent_screen}` in N hops: `{candidate_1}`, `{candidate_2}`, ... All checked by default. Uncheck any to exclude from this audit."

   The user's selections are persisted in `03-clarifications.json` as a new `in_scope_destinations: [...]` field. Stage 05 reads this list to know which candidates to flag as `missing` if Figma has no counterpart.

**Stage 02 walk policy.** Walk every reachable destination up to `default_in_scope_hops` hops (from the platform-hint frontmatter, default 2). Anything beyond N hops or matching a `unwalked_destinations.reason` enum value goes to that bucket; everything else goes to `candidate_destinations`.

**Definition of done.**
- Schema closed-enum + new array field merged.
- Stage 02 refuses to emit `out-of-scope-destination` as a reason.
- Stage 03 emits the multi-select question per parent screen (default in-scope).
- Two runs on the same code produce identical `in_scope_destinations` (modulo user choice).

### #6 — Skill-relative paths

**Problem.** Every inline Python snippet in `stages/*.md` hard-codes `~/.claude/skills/design-coverage/` as the skill root. The skill silently breaks when installed at any other path (e.g., `.claude/skills/design-coverage/` inside a repo, or a plugin-managed location).

**Design.** A new `lib/skill_root.py`:

```python
from pathlib import Path

def get_skill_root() -> Path:
    """Walk up from this file until we find a SKILL.md sibling, return that dir.
    Raises RuntimeError if SKILL.md isn't found within 5 parent levels."""
    here = Path(__file__).resolve().parent
    for _ in range(5):
        if (here / "SKILL.md").exists():
            return here
        here = here.parent
    raise RuntimeError("Could not locate skill root (SKILL.md not found)")
```

Every inline Python snippet that imports `lib.*` rewrites to:

```python
import sys
from pathlib import Path
# Resolve skill root from this file's location, not from a hard-coded ~/.claude path.
_lib = next(p for p in Path(__file__).resolve().parents
            if (p / "SKILL.md").exists()) / "lib"
sys.path.insert(0, str(_lib))
from skill_root import get_skill_root
SKILL_ROOT = get_skill_root()
```

**Sweep.** Grep every `~/.claude/skills/design-coverage/` and `cd ~/.claude/skills/design-coverage/` reference; replace with skill-root-derived paths. Add a CI lint that fails if any hard-coded path reappears.

**Definition of done.**
- `lib/skill_root.py` exists.
- No `~/.claude/skills/` strings remain in `SKILL.md`, `stages/*.md`, or `lib/*.py`.
- The skill works correctly when symlinked into a repo's `.claude/skills/` directory (verifiable: `cd /tmp/some-repo && /design-coverage <figma>` works).

---

## Wave 2 — Universal-reuse infrastructure

Single GH issue. Frontmatter migration + scout updates + safety rails. Largest wave by line count; lowest design risk.

### #7 — Per-stage schema validation gate

**Design.** `lib/skill_io.py::atomic_write_json` gets a sibling: `validate_and_write_json(path, data, schema_name)`. Loads the named schema from `schemas/`, runs `jsonschema.validate`, and only then calls `atomic_write_json`. On validation failure: refuse-loud with the failing JSON-pointer path (`$.items[3].source.surface: 'foo' is not one of ['compose', 'xml', 'hybrid', 'nav-xml', 'nav-compose']`). Do not write the file. Do not advance to the next stage.

Every stage's "Output" section is rewritten to call `validate_and_write_json` instead of `atomic_write_json`.

**Definition of done.**
- `validate_and_write_json` exists in `lib/skill_io.py`.
- Every stage's "Output" section uses it.
- A deliberately-malformed stage 02 output causes a refuse-loud halt before stage 03 starts.

### #10 — Richer platform-hint frontmatter + scout updates

This is the biggest wave-2 task. Three sub-deliverables:

#### 10a — Frontmatter schema additions

Add to platform-hint frontmatter:

- `multi_anchor_suffixes: list[str]` — consumed by wave 3 #4.
- `default_in_scope_hops: int` (default 2) — consumed by wave 1 #3.
- `hotspot_question_overrides: dict[str, str]` (default `{}`) — consumed by wave 1 #1.
- `sealed_enum_patterns: dict[str, {grep: list[str], description: str | null}]` — consumed by stage 02 + scout.

**The registry of "which enum values need platform-specific patterns" is derived from the schemas, not hand-maintained.** Annotate the relevant enum fields in the schemas with a custom JSON Schema keyword `x-platform-pattern: true` (the `x-` prefix is the convention for keywords validators ignore but tooling can read):

```json
// schemas/inventory_item.json (excerpt)
{
  "properties": {
    "kind": {
      "type": "string",
      "x-platform-pattern": true,
      "enum": ["screen", "state", "action", "field", "screen-group"]
    },
    "source": {
      "properties": {
        "surface": {
          "type": "string",
          "x-platform-pattern": true,
          "enum": ["compose", "xml", "hybrid", "nav-xml", "nav-compose"]
        }
      }
    },
    "hotspot": {
      "properties": {
        "type": {
          "type": "string",
          "x-platform-pattern": true,
          "enum": ["feature-flag", "permission", "server-driven", "view-type",
                   "form-factor", "process-death", "viewpager-tab",
                   "sheet-dialog", "config-qualifier"]
        }
      }
    }
  }
}
```

The closed enum on `unwalked_destinations.reason` (introduced by wave 1 #3) gets the same annotation in `schemas/code_inventory.json`.

A new `lib/sealed_enum_index.py` exposes a derivation function — **no hand-maintained list**:

```python
def get_sealed_enum_pattern_keys() -> list[str]:
    """Walk schemas/ and yield <dotted_path>.<value> for every enum field
    annotated with x-platform-pattern: true. Sorted for deterministic order.

    Adding a new enum value requires editing ONLY the schema file. The
    registry, validator, stage 02, and scout all pick up the change
    automatically on next invocation.
    """
    keys: list[str] = []
    for schema_file in (get_skill_root() / "schemas").glob("*.json"):
        schema = json.loads(schema_file.read_text(encoding="utf-8"))
        for path, field in _walk_schema(schema):
            if field.get("x-platform-pattern") and "enum" in field:
                for value in field["enum"]:
                    keys.append(f"{path}.{value}")
    return sorted(keys)
```

`_walk_schema` is a helper that yields `(dotted_path, field_subtree)` for every field in the schema, recursing into `properties` and following `$ref`s.

**Why schema-derived, not hand-coded:** the schemas are the existing source of truth for what enums exist; a hand-maintained registry duplicates that information and silently drifts when a new enum value lands without a corresponding registry edit. With derivation, adding a new enum value is a one-place change. The validator, stage 02, and the scout all read from `get_sealed_enum_pattern_keys()` — none of them sees a hardcoded list.

**Why not scout-per-codebase inference:** the enum values themselves are universal across platforms (the `hotspot.type` enum has the same values whether the run is iOS, Android, or Flutter); what varies per platform is the **grep patterns mapped to each enum value**. If each platform invented its own enum values, the cross-platform comparator would break. The scout's job is to populate the per-platform `grep:` lists for an already-defined registry, not to invent the registry itself.

Validator gate: hint frontmatter that declares an unknown `sealed_enum_patterns` key (one not returned by `get_sealed_enum_pattern_keys()`) is rejected at load time.

#### 10b — Backfill iOS + Android hints

Lift the prose patterns currently under "## 01 Flow locator" / "## 02 Code inventory" / "## 03 Clarification" sections into the structured frontmatter. Keep the prose for human readability; the structured frontmatter becomes the machine-actionable source of truth.

Both `platforms/ios.md` and `platforms/android.md` get the same migration.

#### 10c — Scout pattern-extraction updates

The `design-coverage-scout/stages/02-pattern-extraction.md` stage gets new responsibilities:

For each key returned by `get_sealed_enum_pattern_keys()`:
1. Run platform-appropriate discovery against the unfamiliar codebase (e.g., for `hotspot.type.feature-flag`, look for naming patterns like `*FeatureFlag*`, `*RemoteConfig*`, `*LaunchDarkly*`, `*Optimizely*`).
2. Emit candidate `grep:` patterns (regex strings).
3. Persist to the draft hint's frontmatter under `sealed_enum_patterns.{key}`.

The existing draft/approve gate stays — the user reviews inferred patterns before the hint is finalized.

Because the registry is schema-derived, the scout automatically picks up new enum values added to schemas without any code change in the scout itself. Adding `viewpager-tab` to `hotspot.type` (for example) makes the scout try to detect viewpager patterns on next run.

**Definition of done.**
- `lib/sealed_enum_index.py::get_sealed_enum_pattern_keys()` exists and derives the registry by walking `schemas/` for `x-platform-pattern: true` annotations.
- The four target schemas (`inventory_item.json`, `code_inventory.json`) carry `x-platform-pattern` annotations on every field whose enum values need platform-specific grep patterns.
- Frontmatter schema accepts the new fields; rejects `sealed_enum_patterns` keys not returned by the derivation function.
- iOS + Android hints include populated `sealed_enum_patterns` for every key the derivation function yields.
- Scout `02-pattern-extraction.md` produces candidate patterns for at least 80% of derived keys on a smoke-test repo (e.g., a Flutter project).
- A unit test confirms that adding a new `x-platform-pattern: true` enum value to a schema causes `get_sealed_enum_pattern_keys()` to surface it on the next call without any other code change.

### #11 — Scratch-file policy

**Design.** SKILL.md adds a "Scratch files" section:

> Intermediate working files (debug dumps, classification scratch, build helpers) MUST go to `<run_dir>/.scratch/`. Pipeline artifacts (numbered `NN-name.json` / `NN-name.md` files plus `_severity_lookup_misses.json`) live at the run-dir top level. Never write `_*.json` (other than `_severity_lookup_misses.json`) or `_*.py` at the run-dir top level.
>
> On first stage, the orchestrator writes `<run_dir>/.gitignore` containing `.scratch/`. This keeps scratch out of git automatically.

Each stage's "Output" section adds a one-line reminder.

**Definition of done.**
- SKILL.md "Scratch files" section exists.
- `<run_dir>/.gitignore` is written on first stage.
- A test run produces zero `_*.json`/`_*.py` files at the run-dir top level (other than the audit log).

---

## Wave 3 — Robustness & UX polish

Single GH issue. Smaller surface area than wave 2; depends on wave 2 frontmatter additions for #4.

### #4 — Multi-anchor disambiguation

**Problem.** Stage 01 silently picks the first matching candidate when a Figma name matches multiple class anchors. The 2026-04-25 run anchored on `AppointmentDetailsHostingController` (the new SwiftUI flow) when the user wanted `MBOApptDetailViewController` (the legacy flow). Mid-run pivot was required.

**Design.** After stage 01's grep loop returns candidate classes, walk pairwise. If two candidates' base names differ only by a suffix from the platform hint's `multi_anchor_suffixes`, refuse-loud with a stage-03-style live question:

> "Found multiple anchors for Figma frame `Appointment Details`:
>  - `MBOApptDetailViewController` (`Legacy/Controllers/.../MBOApptDetailViewController.m`, last modified 2024-11-08, 1842 lines)
>  - `AppointmentDetailsHostingController` (`Scenes/AppointmentDetails/AppointmentDetailsHostingController.swift`, last modified 2026-03-15, 47 lines)
>
> Which should anchor the audit?"

Selected anchor + reason recorded in `00-run-config.json` as `selected_anchor: <name>`, `selected_anchor_reason: user-picked-multi-anchor`.

**Definition of done.**
- Stage 01 detects multi-anchor pairs using `multi_anchor_suffixes`.
- Refuse-loud + interactive Q gates the run.
- `00-run-config.json` records the user's choice.

### #5 — Frame-granularity policy

**Problem.** Stage 04 today inventories at varying granularity (the 2026-04-14 run picked 23 section-level frames; the 2026-04-25 run picked 111 leaf-level frames). Both are valid; neither is consistent across runs.

**Design.** Three coordinated changes:

1. **Pin the level.** Stage 04 inventories at **leaf-frame level** (frames with `type == FRAME` AND no `FRAME` children). Sections and section-level groupings get a new `kind: "screen-group"` enum value (added to `inventory_item.json`'s `kind` enum) and emit as parent items with `parent_id: null`.

2. **Promote frame classification to a real artifact.** What is currently scratch (`_in_scope_with_names.json`) becomes `00-frame-classification.json` — a real pipeline artifact with its own schema (`schemas/frame_classification.json`). Stage 04 reads it.

3. **Add a `figma_dedup_policy` clarification.** Stage 03 emits one Q with options `none | dark-twins-folded | appearance-modes-folded` (default `dark-twins-folded`). Stage 04 reads the policy and folds appearance variants accordingly.

**Definition of done.**
- New `kind: "screen-group"` enum value in `inventory_item.json`.
- `schemas/frame_classification.json` exists; stage 04 emits `00-frame-classification.json` as a top-level artifact.
- `figma_dedup_policy` Q in stage 03; stage 04 honors the answer.
- Two runs on the same Figma produce identical frame counts.

### #12 — Next-5-actions template

**Problem.** Stage 06's narrative summary asks the agent to write 5 imperative-voice action sentences. Two runs produce different wordings even on the same data.

**Design.** A new `lib/action_verbs.py` exposes `ALLOWED_VERBS = ["Ask", "Confirm", "Drop", "Document", "Wire", "Deprecate"]` and a slot-fill template:

```
{N}. **{verb} {object}** — {legacy_ref} {has no | conflicts with} {figma_ref}.
   {one-sentence consequence}. Action: {ask_design | confirm_with_product | document_as_dropped | wire_in_navigation}.
```

SKILL.md's "Final output" section gets the template inline. Agent fills slots; doesn't write prose from scratch. The `verb` slot is constrained to `ALLOWED_VERBS`.

**Definition of done.**
- `lib/action_verbs.py` exists.
- SKILL.md's "Next 5 actions" prose is replaced by the template.
- Two runs on the same `06-report.json` produce action lists where the verbs and noun-objects match (the consequence sentence may vary).

### #13 — Low-confidence verdict warning

**Problem.** The verdict line in `06-summary.md` doesn't surface stage-1 confidence. A low-confidence flow-mapping can produce a clean-looking 🟢 verdict despite shaky foundations.

**Design.** Stage 06's narrative render reads `01-flow-mapping.json.confidence` and `.locator_method`. If `confidence == "low"` OR `locator_method == "name-search"` (no nav-graph match), prepend the verdict line:

```
> ⚠ **Low-confidence anchor — review stage 1 before trusting this report.**
> **Verdict:** 🟢 Ready to ship
```

**Definition of done.**
- Stage 06's verdict-line snippet checks the flow-mapping confidence.
- A low-confidence test run produces the warning prefix in `06-summary.md`.

---

## Wave 4 — Deferred

Differential mode (`--compare-against`) and lessons-learned feedback persistence are intentionally out of scope. Both introduce **new commands** rather than amending existing pipeline behavior; both deserve their own brainstorm to nail the CLI surface, output format, and persistence strategy. Filed as a follow-up note, not as an issue, to avoid pre-committing to a half-formed design.

## GH issue plan

Three issues against `prpande/skills`. One per wave.

**Title pattern:** `[design-coverage] Wave N — <theme>`

**Labels:** `enhancement`, `design-coverage`, `wave-N`. Wave 1 issue additionally gets `in-progress`.

**Body structure (each issue):**

1. **Spec reference** — link to this spec doc, anchor to the relevant wave section.
2. **Problem statement** — copied verbatim from the spec.
3. **Design** — copied verbatim from the spec (including code blocks).
4. **Files in scope** — explicit list of files the wave touches.
5. **Definition of Done** — copied verbatim from the spec.
6. **Inter-wave dependencies** — explicit cross-references (e.g., wave 3 #4 reads `multi_anchor_suffixes` introduced by wave 2 #10a; an agent picking up wave 3 must wait for wave 2 to merge OR work against the wave-2 branch).
7. **Hand-off context** — for an agent picking up cold: where the skill source lives (`skills/design-tooling/design-coverage/`), how to run it (`/design-coverage <figma-url>`), where the prior runs live (in `MindBodyPOS-design-tooling` worktree under `docs/design-coverage/`).

**Issue titles (proposed):**

- Wave 1: `[design-coverage] Wave 1 — Methodology-drift killer (#1, #2, #3, #6)`
- Wave 2: `[design-coverage] Wave 2 — Sealed-enum frontmatter, scout updates, schema validation, scratch policy (#7, #10, #11)`
- Wave 3: `[design-coverage] Wave 3 — Multi-anchor disambiguation, frame-granularity, action-verb template, low-confidence verdict (#4, #5, #12, #13)`

## Risks & open questions

- **Scout work in #10c is the highest-uncertainty piece.** Detecting `sealed_enum_patterns` in an unfamiliar codebase is a non-trivial inference task. Mitigation: ship with iOS + Android hints fully populated, treat scout-generated patterns as drafts the user always reviews. The existing draft/approve gate covers this.
- **Wave 1 + wave 2 ordering.** Wave 1 #3 references `default_in_scope_hops` from wave 2 #10. If waves ship out of order, wave 1 needs a hard-coded default of 2 hops temporarily. Mitigation: wave 1 hard-codes the default; wave 2 makes it configurable. No blocking ordering required.
- **Backward compatibility on `unwalked_destinations.reason`.** Existing run-dir artifacts have free-form reason strings. Mitigation: validator only enforces the closed enum on NEW writes; reads stay tolerant.
- **`emit_questions_for_inventory` may produce too many questions on hub screens.** A screen with 15 distinct hotspot symbols would emit 15 Qs. Mitigation: question batching by `hotspot_type` (one Q with N symbols listed) is allowed; the registry can declare a `batchable_within_type: true` flag per template.
- **CI lint for hard-coded paths (#6).** Requires adding a CI step. If `prpande/skills` doesn't have CI configured, this becomes a manual review checklist instead.

## Acceptance criteria

The spec is "done" when:

- [ ] Spec doc committed to `docs/superpowers/specs/2026-04-25-design-coverage-improvements-design.md`.
- [ ] User has reviewed the spec and approved.
- [ ] Three GH issues filed against `prpande/skills` with this spec's wave sections inline.
- [ ] Wave 1 implementation lands on branch `pratyush/design-coverage-improvements` in this session (commits only — user pushes manually).
- [ ] Implementation plan written via `superpowers:writing-plans`.
