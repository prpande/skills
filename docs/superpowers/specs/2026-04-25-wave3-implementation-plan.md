# Wave 3 — Implementation Plan (issue #13)

This document is the agent-facing implementation plan for Wave 3 of the
design-coverage improvements. It precedes code changes; all items below
require review approval before implementation begins.

Reference spec: `docs/superpowers/specs/2026-04-25-design-coverage-improvements-design.md`
Feature branch: `claude/issue-13-implementation-DwefJ`

---

## Scope

Wave 3 covers four improvements:

| ID  | Title                          |
|-----|-------------------------------|
| #4  | Multi-anchor disambiguation    |
| #5  | Frame-granularity policy       |
| #12 | Next-5-actions template        |
| #13 | Low-confidence verdict warning |

---

## Pre-conditions

- `multi_anchor_suffixes` frontmatter field is already defined in
  `lib/hint_frontmatter.py` (landed with wave 2 on `pratyush/design-coverage-wave-2`,
  already merged into `main`).
- `sealed_enum_index.get_sealed_enum_pattern_keys()` auto-derives keys from schemas,
  so adding `"screen-group"` to `inventory_item.json` will flow through automatically.

---

## Change-by-change breakdown

### 1. `schemas/inventory_item.json` — add `"screen-group"` to `kind` enum

**Why:** #5 requires section-level frame groupings to emit as a distinct kind.

**What changes:**
```diff
-"enum": ["screen", "state", "action", "field"]
+"enum": ["screen", "screen-group", "state", "action", "field"]
```

`x-platform-pattern: true` is already set on `kind`, so `inventory_item.kind.screen-group`
flows into `get_sealed_enum_pattern_keys()` automatically — no other wiring required.

---

### 2. `schemas/frame_classification.json` (NEW)

**Why:** #5 promotes `_in_scope_with_names.json` (scratch) to a real pipeline artifact
`00-frame-classification.json` with a validated schema.

**Shape:**
```json
{
  "$id": "frame_classification.json",
  "type": "object",
  "required": ["frames"],
  "properties": {
    "frames": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["frame_id", "name", "is_leaf", "parent_id"],
        "properties": {
          "frame_id":  { "type": "string",          "minLength": 1 },
          "name":      { "type": "string",          "minLength": 1 },
          "is_leaf":   { "type": "boolean"                        },
          "parent_id": { "type": ["string", "null"]               }
        }
      }
    }
  }
}
```

---

### 3. `lib/action_verbs.py` (NEW)

**Why:** #12 requires a constrained verb list and a slot-fill template so two runs on
the same data produce matching action verbs and noun-objects.

**Contents:**
```python
ALLOWED_VERBS = ["Ask", "Confirm", "Drop", "Document", "Wire", "Deprecate"]

ACTION_TEMPLATE = (
    "{N}. **{verb} {object}** — {legacy_ref} {has no | conflicts with} {figma_ref}.\n"
    "   {one-sentence consequence}. Action: "
    "{ask_design | confirm_with_product | document_as_dropped | wire_in_navigation}."
)
```

No logic beyond the constant exports — just the vocabulary contract.

---

### 4. `schemas/clarifications.json` — add `figma_dedup_policy` field

**Why:** Stage 03's new `figma_dedup_policy` Q (for #5) needs a home in the schema.
Adding it as a top-level field (not a hotspot `resolved[]` entry) because it is a
global Figma-inventory policy, not a per-hotspot decision.

**What changes:**
```diff
 "properties": {
   "resolved": { ... },
-  "in_scope_destinations": { ... }
+  "in_scope_destinations": { ... },
+  "figma_dedup_policy": {
+    "type": "string",
+    "enum": ["none", "dark-twins-folded", "appearance-modes-folded"]
+  }
 }
```

---

### 5. `stages/01-flow-locator.md` — multi-anchor disambiguation (#4)

**Where it fits:** After the candidate-class grep loop (Pass 1 and Pass 2), before
writing `01-flow-mapping.json`.

**Algorithm to document:**
1. Read `multi_anchor_suffixes` from the resolved platform-hint frontmatter
   (already available via `hint_frontmatter.parse_hint_frontmatter`).
   Default to `[]` if the field is absent (hint has no ambiguous-suffix pairs).
2. Strip each known suffix from the end of every candidate class name; compare
   the resulting base names pairwise.
3. If any two candidates share the same base name → **refuse-loud** (interactive
   in-session, never a file handoff):

   > "Found multiple anchors for Figma frame `<name>`:\n
   >  - `<CandidateA>` (`<file>`, last modified `<date>`, `<N>` lines)\n
   >  - `<CandidateB>` (`<file>`, last modified `<date>`, `<N>` lines)\n\n
   > Which should anchor the audit?"

   Ask via the live `AskUserQuestion` interface with each candidate as a choice.
4. Record the user's selection in `00-run-config.json`:
   ```json
   "selected_anchor": "<chosen class name>",
   "selected_anchor_reason": "user-picked-multi-anchor"
   ```
5. Continue stage 01 using only the selected anchor.

**Run-config schema note:** The `00-run-config.json` is written by the orchestrator
(SKILL.md), not validated against `schemas/run.json` (which is the stages-status
schema). No schema change is required — `selected_anchor` and `selected_anchor_reason`
are additive fields on the open-shape run-config object.

---

### 6. `stages/03-clarification.md` — `figma_dedup_policy` Q (#5)

**Where it fits:** After hotspot questions and candidate-destination scope, before
writing `03-clarifications.json`.

**New question to emit:**
> "How should Figma appearance variants (light/dark mode, etc.) be handled in the
> inventory?
>  - `none` — keep all variants as separate inventory items
>  - `dark-twins-folded` *(default)* — fold light/dark pairs into one item with
>    `modes: ["light", "dark"]`
>  - `appearance-modes-folded` — fold all appearance variants (including dynamic
>    type, high-contrast) into one item"

Persist the answer in `03-clarifications.json` as:
```json
"figma_dedup_policy": "dark-twins-folded"
```

**Short-circuit update:** The existing short-circuit ("If both lists are empty,
write and exit") is updated to also write `figma_dedup_policy` with the default
`"dark-twins-folded"` when the user is not asked — so stage 04 always has the
field available.

---

### 7. `stages/04-figma-inventory.md` — leaf-frame level + screen-group + frame-classification (#5)

Three coordinated changes:

#### 7a — Pin granularity to leaf-frame level

A **leaf frame** = `type == "FRAME"` AND has no direct `FRAME`-type children.

For each in-scope Figma file:
1. Identify all frames with `type == FRAME`.
2. Classify each: if it has no `FRAME` children → `is_leaf: true`; else → `is_leaf: false`.
3. **Only** process leaf frames through the full per-frame procedure (MCP call,
   screenshot, InventoryItem generation).
4. Emit section-level (non-leaf) frames as `kind: "screen-group"` InventoryItems
   with `parent_id: null` — no MCP call needed, just the frame metadata.

#### 7b — Emit `00-frame-classification.json` as a real artifact

Before the per-frame loop, emit:
```python
frame_classification = {
    "frames": [
        {
            "frame_id": f["id"],
            "name":     f["name"],
            "is_leaf":  <bool>,
            "parent_id": f.get("parentId")  # Figma parent, not pipeline parent_id
        }
        for f in all_in_scope_frames
    ]
}
validate_and_write_json(
    run_dir / "00-frame-classification.json",
    frame_classification,
    "frame_classification.json",
    get_skill_root() / "schemas",
)
```

This replaces the old `<run_dir>/.scratch/_in_scope_with_names.json` pattern.

#### 7c — Honor `figma_dedup_policy`

Read `03-clarifications.json`'s `figma_dedup_policy` (default `"dark-twins-folded"`
if field absent for backward compatibility). Apply folding:
- `"none"` → emit every variant as its own InventoryItem.
- `"dark-twins-folded"` → when two leaf frames share the same logical name and differ
  only by a light/dark appearance suffix (e.g., `Appt Details – Light` /
  `Appt Details – Dark`), emit one item with `modes: ["light", "dark"]`.
- `"appearance-modes-folded"` → fold all appearance-variant twins into one item;
  populate `modes` with all detected variant labels.

---

### 8. `SKILL.md` — slot-fill template + low-confidence warning (#12, #13)

#### 8a — Low-confidence verdict warning (#13)

In "Final output" § "Required structure" item 2, replace:

> `> **Verdict:** 🟢 Ready to ship`

with a conditional:

> Read `<run-dir>/01-flow-mapping.json`. If `confidence == "low"` OR
> `locator_method == "name-search"`, prepend the verdict block with:
>
> ```
> > ⚠ **Low-confidence anchor — review stage 1 before trusting this report.**
> > **Verdict:** 🟢 Ready to ship
> ```
>
> Otherwise emit the verdict line without the warning.

#### 8b — Next-5-actions slot-fill template (#12)

In "Required structure" item 3 ("Next 5 actions"), replace the free-prose instruction:

> "One sentence each, imperative voice, beginning with a verb ("Ask design to add…", …)"

with the constrained template:

> Verb **must** be one of `ALLOWED_VERBS` from `lib/action_verbs.py`:
> `Ask | Confirm | Drop | Document | Wire | Deprecate`.
>
> Each action uses this slot-fill template:
> ```
> {N}. **{verb} {object}** — {legacy_ref} {has no | conflicts with} {figma_ref}.
>    {one-sentence consequence}. Action: {ask_design | confirm_with_product | document_as_dropped | wire_in_navigation}.
> ```
>
> Fill every slot. Do not write free-form prose in place of the template.

---

### 9. `stages/06-report-generator.md` — cross-reference (#12, #13)

Add a short reference section to the "Narrative summary (NOT this stage)" block
noting that:
- The narrative render reads `01-flow-mapping.json.confidence` and `.locator_method`
  to decide whether to prepend the low-confidence warning (see SKILL.md § "Final output").
- The "Next 5 actions" block in the narrative is constrained by `lib/action_verbs.py`'s
  `ALLOWED_VERBS` and slot-fill template (see SKILL.md § "Final output").

No logic changes to this file — purely cross-reference prose so an agent reading
stage 06 in isolation knows where to look.

---

## Tests to add

All tests go under `skill-tests/design-coverage/tests/`.

### `test_multi_anchor_disambiguate.py`

Tests the multi-anchor detection algorithm described in stage 01.

**Fixtures needed** (`skill-tests/design-coverage/fixtures/stage-01/multi-anchor/`):
- `input/AppointmentDetailsViewController.swift` — contains `class AppointmentDetailsViewController`
- `input/AppointmentDetailsHostingController.swift` — contains `class AppointmentDetailsHostingController`
- `hint_suffixes.json` — `["ViewController", "HostingController"]`

**Tests:**
1. `test_multi_anchor_detected` — given two candidates whose base names match after
   stripping suffixes, `detect_multi_anchor_pair(candidates, suffixes)` returns the
   pair.
2. `test_single_anchor_not_flagged` — one candidate never triggers disambiguation.
3. `test_no_suffix_match_not_flagged` — two candidates with different base names after
   stripping are not flagged.
4. `test_run_config_records_selected_anchor` — the run-config dict gains
   `selected_anchor` and `selected_anchor_reason: "user-picked-multi-anchor"` when a
   selection is made.

### `test_frame_classification_schema.py`

Tests that `schemas/frame_classification.json` is well-formed and validates correct
and incorrect payloads.

**Fixtures needed** (`skill-tests/design-coverage/fixtures/frame-classification/`):
- `valid_leaf_only.json` — two leaf frames, `parent_id: null`
- `valid_mixed.json` — one parent frame (`is_leaf: false`) + two leaf children
- `invalid_missing_is_leaf.json` — frame item missing `is_leaf` field

**Tests:**
1. `test_schema_file_exists` — `schemas/frame_classification.json` is present and
   parses as valid JSON.
2. `test_valid_leaf_only_passes` — fixture validates against schema.
3. `test_valid_mixed_passes` — mixed parent+leaf fixture validates.
4. `test_missing_is_leaf_fails` — invalid fixture raises `ValidationError`.

### `test_action_verbs.py`

Tests `lib/action_verbs.py`.

**Tests:**
1. `test_allowed_verbs_exported` — `ALLOWED_VERBS` exists and equals
   `["Ask", "Confirm", "Drop", "Document", "Wire", "Deprecate"]`.
2. `test_action_template_exported` — `ACTION_TEMPLATE` exists and is a non-empty string.
3. `test_template_contains_verb_slot` — `ACTION_TEMPLATE` contains `{verb}`.
4. `test_template_contains_object_slot` — `ACTION_TEMPLATE` contains `{object}`.

### `test_low_confidence_verdict.py`

Tests the low-confidence verdict prepend logic described in SKILL.md.

**Tests:**
1. `test_low_confidence_triggers_warning` — a flow-mapping with `confidence: "low"` +
   any `locator_method` produces a warning-prepended verdict block.
2. `test_name_search_triggers_warning` — `locator_method: "name-search"` (regardless
   of `confidence`) produces a warning-prepended verdict block.
3. `test_high_confidence_nav_graph_no_warning` — `confidence: "high"` +
   `locator_method: "nav-graph"` produces a clean verdict with no warning.
4. `test_warning_block_contains_expected_text` — the warning block contains
   `⚠` and `Low-confidence anchor`.

---

## Unchanged files

The following files are **not touched** by Wave 3:

- `stages/02-code-inventory.md`
- `stages/05-comparator.md`
- `schemas/comparison.json`, `schemas/code_inventory.json`, `schemas/figma_inventory.json`,
  `schemas/flow_mapping.json`, `schemas/report.json`, `schemas/run.json`
- All `lib/` files except the new `lib/action_verbs.py`
- `design-coverage-scout/` — untouched by wave 3

---

## Execution order

1. `schemas/inventory_item.json` — add `screen-group` (unblocks sealed-enum derivation)
2. `schemas/frame_classification.json` — new schema
3. `schemas/clarifications.json` — add `figma_dedup_policy`
4. `lib/action_verbs.py` — new file
5. `stages/01-flow-locator.md` — multi-anchor section
6. `stages/03-clarification.md` — `figma_dedup_policy` Q
7. `stages/04-figma-inventory.md` — leaf-frame level + screen-group + classification artifact
8. `SKILL.md` — verdict warning + slot-fill template
9. `stages/06-report-generator.md` — cross-references
10. Tests + fixtures

Each step is independently reviewable; no step creates a compile/import dependency on
a later step (the stage `.md` files are prose, not executable code, so order matters
only for logical completeness).
