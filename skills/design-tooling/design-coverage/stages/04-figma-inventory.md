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

## Per-frame procedure

For each in-scope top-level Figma frame:

1. Call `mcp__plugin_figma_figma__get_design_context(fileKey, nodeId=frame_id)` to get structured data (layers, components, text, design tokens, annotations, Code Connect mappings).
2. Call `mcp__plugin_figma_figma__get_screenshot(fileKey, nodeId=frame_id)`.
3. Extract `InventoryItem` rows for the frame itself (`kind: "screen"`) plus each meaningful state/action/field inside it. Use stable slug IDs rooted at the frame (e.g., `appt-details.header.save-button`). Set `parent_id` to build the screen → state → action/field hierarchy. When a Figma frame has sibling light/dark (or other appearance-variant) twins of the same logical screen, emit **one** inventory item with `modes: ["light", "dark"]` — not two separate rows. This prevents the comparison matrix from doubling up on visual variants. When a frame's intent is unclear from metadata alone (e.g., it's labelled as a demo or coachmark), set `ambiguous: true` with a one-sentence `ambiguity_reason` — stage 5 will surface it in the report.
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
from skill_io import atomic_write_json, read_json

inventory = read_json(run_dir / "04-figma-inventory.json") or {"items": [], "frames": []}
# append new items + frame entry
atomic_write_json(run_dir / "04-figma-inventory.json", inventory)
```

Write incrementally — after each frame — so an interrupted session resumes without re-querying frames already processed.
