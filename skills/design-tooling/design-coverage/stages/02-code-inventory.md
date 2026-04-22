# Stage 02 — Code inventory (platform-agnostic core)

## Inputs

- `01-flow-mapping.json` from stage 1.
- The current repository.

## Preflight

```bash
cd ~/.claude/skills/design-coverage/
```

## Objective

For each screen in the flow, enumerate its inventory items — screens, states, actions, fields — and emit `02-code-inventory.json` conforming to `~/.claude/skills/design-coverage/schemas/code_inventory.json` with rows conforming to the shared `inventory_item.json` fragment.

## Method (platform-agnostic)

Use the **Discovery → Focused-reads → Cross-linking** approach:

1. **Discovery (ripgrep pass).** For each screen's code anchor, grep for the platform's screen-declaration conventions, state-container conventions, and action/event conventions. The platform hints below tell you the concrete patterns.
2. **Focused reads.** Open each candidate file and extract:
   - Screens (container units — a view controller, fragment, component, page, etc.)
   - States (distinct render modes — loading, empty, error, populated; also variant modes like compact/expanded, admin/user)
   - Actions (user-triggered events — button taps, swipes, form submissions, nav triggers)
   - Fields (data displayed to the user — labels, images, lists, charts, icons with meaning)
3. **Cross-linking.** Attach each state/action/field to its parent screen via `parent_id`. Some screens may be represented by multiple files (hybrid hosts) — the hints below describe how to identify and merge them.

## Rules

- **Preserve orphaned items.** If a state/action/field has a `parent_id` that doesn't resolve to a listed screen, keep it with its orphan `parent_id` intact. The renderer will surface these under an "Orphaned items" section. Never drop them silently.
- **One row per item.** Do not duplicate inventory items across modes; represent mode-dependence as a field on the item (`modes: ["admin", "user"]`).
- **No speculation.** Only include items present in code. If a comment references a feature that isn't implemented, do not record it.

## Output

Write `02-code-inventory.json` to the run dir, then regenerate the Markdown view:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "lib"))
from skill_io import atomic_write_json, read_json
from renderer import render_code_inventory

inventory = read_json(run_dir / "02-code-inventory.json") or {"items": [], "unwalked_destinations": []}
# ...populate inventory...
atomic_write_json(run_dir / "02-code-inventory.json", inventory)
(run_dir / "02-code-inventory.md").write_text(render_code_inventory(inventory))
```

<!-- PLATFORM_HINTS -->
