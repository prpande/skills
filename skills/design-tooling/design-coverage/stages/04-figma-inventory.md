# Stage 4 — Figma Inventory

## Purpose

Build a structured inventory of the Figma design's screens, states, actions, and fields — plus a screenshot cross-check per frame to catch cases where the structured metadata and the pixels disagree.

## Resumability

**First action:** check whether `<run_dir>/04-figma-inventory.json` already exists. If it does, re-read it and skip frames already processed (day-one stage resume is artifact-based; see spec "Run config artifact").

## Inputs

- `<run_dir>/01-flow-mapping.json` (Stage 1) — tells you which Figma frames are in-scope.
- Figma MCP tools: `mcp__plugin_figma_figma__get_design_context` and `mcp__plugin_figma_figma__get_screenshot` (paired per frame).

## Output

Write `<run_dir>/04-figma-inventory.json`. Schema: [`schemas/figma_inventory.json`](../schemas/figma_inventory.json).

Shape:

```
{
  "items": [ InventoryItem, ... ],
  "frames": [
    { "frame_id": "...", "screenshot_cross_check": "agreed" | "disagreed" | "n/a", "error": string | null }
  ]
}
```

Then regenerate `<run_dir>/04-figma-inventory.md` via the inline pattern shown in "Atomic write pattern" below (extend with `(run_dir / "04-figma-inventory.md").write_text(render_figma_inventory(inventory))`).

## Frame classification and dedup policy (wave 3 #5)

### Step 0 — Classify frames and emit `00-frame-classification.json`

Before the per-frame loop, classify every in-scope Figma frame as leaf or non-leaf,
and emit the classification as a top-level pipeline artifact. Write this file
**unconditionally** on every invocation (including resumes) — it is deterministic
so re-writing is safe. Do NOT skip the write when the file already exists.

A **leaf frame** = `type == "FRAME"` AND has no direct `FRAME`-type children.

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "lib"))
from skill_io import validate_and_write_json, read_json
from skill_root import get_skill_root

# all_in_scope_frames: list of raw Figma frame dicts from the MCP response.
# Each has at least: {"id": ..., "name": ..., "type": ..., "children": [...], "parentId": ...}
def _is_leaf(frame: dict) -> bool:
    return not any(c.get("type") == "FRAME" for c in frame.get("children", []))

frame_classification = {
    "frames": [
        {
            "frame_id":        f["id"],
            "name":            f["name"],
            "is_leaf":         _is_leaf(f),
            "figma_parent_id": f.get("parentId"),  # Figma node parent ID (not pipeline parent_id)
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

This replaces the old `<run_dir>/.scratch/_in_scope_with_names.json` scratch pattern.

### Step 0b — Read `figma_dedup_policy`

```python
clarifications = read_json(run_dir / "03-clarifications.json") or {}
figma_dedup_policy = clarifications.get("figma_dedup_policy", "dark-twins-folded")
```

The policy controls how appearance-variant twin frames are folded in step 3 below.

### Section-level frames → `kind: "screen-group"`

Non-leaf frames (those with `FRAME` children) are section-level groupings. Emit each
as a `kind: "screen-group"` `InventoryItem` with `parent_id: null` — no MCP call
or screenshot needed, just the frame name and metadata. Only leaf frames go through
the full per-frame procedure below.

## Per-frame procedure

Process **only leaf frames** (those with `is_leaf: true` in the classification).
For each leaf frame:

1. Call `mcp__plugin_figma_figma__get_design_context(fileKey, nodeId=frame_id)` to get structured data (layers, components, text, design tokens, annotations, Code Connect mappings).
2. Call `mcp__plugin_figma_figma__get_screenshot(fileKey, nodeId=frame_id)`.
3. Extract `InventoryItem` rows for the frame itself (`kind: "screen"`) plus each meaningful state/action/field inside it. Use stable slug IDs rooted at the frame (e.g., `appt-details.header.save-button`). Set `parent_id` to build the screen → state → action/field hierarchy.

   **Appearance-variant folding** (apply `figma_dedup_policy`):
   - `"none"` → emit every variant as its own `InventoryItem`.
   - `"dark-twins-folded"` *(default)* → when two leaf frames share the same logical
     name and differ only by a light/dark appearance suffix (e.g., `Appt Details – Light`
     and `Appt Details – Dark`), emit **one** item with `modes: ["light", "dark"]`
     instead of two separate rows. This prevents the comparison matrix from doubling
     up on visual variants.
   - `"appearance-modes-folded"` → fold all appearance-variant twins (including
     dynamic type, high-contrast) into one item; populate `modes` with all detected
     variant labels.

   When a frame's intent is unclear from metadata alone (e.g., labelled as a demo
   or coachmark), set `ambiguous: true` with a one-sentence `ambiguity_reason` —
   stage 5 will surface it in the report.
4. Compare structured data against the screenshot. Set `screenshot_cross_check`:
   - `agreed` — structured data and screenshot tell the same story.
   - `disagreed` — they differ meaningfully (e.g., a button labelled "Save" in metadata shows as "Continue" in the pixels). Stage 5 will bump severity on any comparison row referencing this frame.
   - `n/a` — frame type doesn't support a useful cross-check (e.g., pure icon, pure divider).

## Refuse-loud condition

If a **specific** frame's MCP call fails, record the failure on that frame's entry (`error: "<reason>"`, `screenshot_cross_check: "n/a"`) and continue. If **every** frame fails, refuse: write `04-figma-inventory.json` with an empty `items: []` and every frame carrying `error`, render the Markdown view, and exit.

## Atomic write pattern

```bash
# Resolve the skill root portably: walk up from CWD to find SKILL.md, with
# fallback to the standard install location when CWD is outside the skill tree.
cd "$(python -c 'import sys; from pathlib import Path; p=Path.cwd(); fb=Path.home()/".claude"/"skills"/"design-coverage"; cands=[q for q in [p,*p.parents,fb] if (q/"SKILL.md").exists()]; print(cands[0]) if cands else sys.exit("design-coverage skill not found")')"
```

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "lib"))
from skill_io import validate_and_write_json, read_json
from skill_root import get_skill_root

inventory = read_json(run_dir / "04-figma-inventory.json") or {"items": [], "frames": []}
# append new items + frame entry
validate_and_write_json(
    run_dir / "04-figma-inventory.json",
    inventory,
    "figma_inventory.json",
    get_skill_root() / "schemas",
)
```

Write incrementally — after each frame — so an interrupted session resumes without re-querying frames already processed.

> Scratch reminder: any intermediate file produced by this stage (debug
> dumps, classification scratch) goes to `<run_dir>/.scratch/`, never the
> run-dir top level.
