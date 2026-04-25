# Stage 02 — Code inventory (platform-agnostic core)

## Inputs

- `01-flow-mapping.json` from stage 1.
- The current repository.

## Preflight

```bash
# Resolve the skill root portably: walk up from CWD to find SKILL.md.
cd "$(python -c 'from pathlib import Path; p=Path.cwd(); print(next(q for q in [p, *p.parents] if (q/"SKILL.md").exists()))')"
```

## Objective

For each screen in the flow, enumerate its inventory items — screens, states, actions, fields — and emit `02-code-inventory.json` conforming to the skill's `schemas/code_inventory.json` with rows conforming to the shared `inventory_item.json` fragment.

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
- **One row per item.** Do not duplicate inventory items across visual modes; represent mode-dependence via the optional `modes: [...]` list on the item. For a screen that exists only in light + dark modes at the code level, emit one row with `modes: ["light", "dark"]` — not two separate rows. For a screen with a role-based variant, use `modes: ["admin", "user"]`.
- **Tag ambiguity loudly.** When a state/action/field's presence or behavior can't be determined statically (e.g., only visible in a demo harness, shown as deprecated but not removed), set `ambiguous: true` and a one-sentence `ambiguity_reason` so stage 5's comparator can cite it.
- **No speculation.** Only include items present in code. If a comment references a feature that isn't implemented, do not record it.

## Closed-enum reasons for `unwalked_destinations`

Stage 02 emits `unwalked_destinations` for navigation targets it does NOT
walk. The `reason` field is now a **closed enum** with values:

- `adapter-hosted` — the destination is reached through an adapter/bridge whose
  internals are not in scope (e.g., `*Adapter.*`, `*Bridge.*` calls).
- `external-module` — the destination lives in a separate module/package not
  part of this audit's source tree.
- `swiftui-bridge` — UIKit-to-SwiftUI or SwiftUI-to-UIKit bridge whose wrapped
  destination is reached through a hosting controller or representable.
- `dynamic-identifier` — the destination identifier is computed at runtime
  (e.g., `instantiateViewControllerWithIdentifier:` with a runtime string,
  selectors built from data).
- `platform-bridge` — platform-specific bridge that crosses framework boundaries
  (e.g., React Native bridge call into native, Flutter MethodChannel).
- `unresolved-class` — the destination references a class name (e.g., from a
  nav-graph XML `android:name=` attribute) that does not exist in the walked
  source tree. Distinct from `external-module`: an external module is known
  to live elsewhere; an unresolved class might be a typo, a deleted file, or
  generated code not on disk.

**The string `"out-of-scope-destination"` is no longer valid.** If you would
have written that, emit the destination to `candidate_destinations` instead
(see below) so stage 03 can ask the user to confirm scope.

## Candidate destinations (judgment-call escapes)

Anything that's reachable from the entry but the agent judges as "maybe in
scope, not sure" goes to `candidate_destinations: [...]`. Each entry:

```json
{
  "parent_screen": "MBOApptDetailViewController",
  "symbol": "MBOApptQuickBookViewController",
  "file": "MindBodyPOS/Legacy/.../QuickBook.m",
  "hop_distance": 1,
  "why_not_walked": "Modify-appointment full screen; agent unsure if part of appointment-details audit scope."
}
```

`parent_screen` is the symbol of the screen the candidate is reachable
from — stage 03 groups candidates by `parent_screen` for the
multi-select scope question.

Stage 03 will surface these to the user as a multi-select question per parent
screen, defaulting all to in-scope (uncheck to exclude). Do NOT silently
in-scope or out-of-scope these on your own.

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
