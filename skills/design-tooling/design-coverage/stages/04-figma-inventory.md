# Stage 4 — Figma Inventory

## Purpose

Build a structured inventory of the Figma design's screens, states, actions, and fields — plus a screenshot cross-check per frame to catch cases where the structured metadata and the pixels disagree.

## Resumability

**First action:** read `<run_dir>/run.json`. Skip if `stages["4"].status == "completed"`. Otherwise, re-read `figma_inventory.json` — frames already processed are skipped.

## Inputs

- `<run_dir>/flow_mapping.json` (Stage 1) — tells you which Figma frames are in-scope.
- Figma MCP tools: `get_design_context` and `get_screenshot` (paired per frame).

## Output

Write `<run_dir>/figma_inventory.json`. Schema: [`schemas/figma_inventory.json`](../schemas/figma_inventory.json).

Shape:

```
{
  "items": [ InventoryItem, ... ],
  "frames": [
    { "frame_id": "...", "screenshot_cross_check": "agreed" | "disagreed" | "n/a", "error": string | null }
  ]
}
```

Then regenerate `<run_dir>/figma_inventory.md` via `lib/renderer.py:render_figma_inventory`.

## Per-frame procedure

For each in-scope top-level Figma frame:

1. Call Figma MCP `get_design_context(fileKey, nodeId=frame_id)` to get structured data (layers, components, text, design tokens, annotations, Code Connect mappings).
2. Call `get_screenshot(fileKey, nodeId=frame_id)`.
3. Extract `InventoryItem` rows for the frame itself (`kind: "screen"`) plus each meaningful state/action/field inside it. Use stable slug IDs rooted at the frame (e.g., `appt-details.header.save-button`). Set `parent_id` to build the screen → state → action/field hierarchy.
4. Compare structured data against the screenshot. Set `screenshot_cross_check`:
   - `agreed` — structured data and screenshot tell the same story.
   - `disagreed` — they differ meaningfully (e.g., a button labelled "Save" in metadata shows as "Continue" in the pixels). Stage 5 will bump severity on any comparison row referencing this frame.
   - `n/a` — frame type doesn't support a useful cross-check (e.g., pure icon, pure divider).

## Refuse-loud condition

If a **specific** frame's MCP call fails, record the failure on that frame's entry (`error: "<reason>"`, `screenshot_cross_check: "n/a"`) and continue. If **every** frame fails, refuse: set `run.json` stage 4 status to `"refused"`, render the Markdown view with the reason, and exit.

## Atomic write pattern

```bash
cd ~/.claude/skills/design-coverage/
```

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "lib"))
from skill_io import atomic_write_json, read_json

inventory = read_json(run_dir / "figma_inventory.json") or {"items": [], "frames": []}
# append new items + frame entry
atomic_write_json(run_dir / "figma_inventory.json", inventory)
```

Write incrementally — after each frame — so an interrupted session resumes without re-querying frames already processed.
