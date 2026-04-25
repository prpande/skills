# Stage 01 — Flow locator (platform-agnostic core)

## Inputs

- `00-run-config.json` — contains `figma_url`, `old_flow_hint` (optional), `platform`, `hint_source`.
- The current repository (CWD).
- Figma MCP access via `mcp__plugin_figma_figma__get_metadata` and `mcp__plugin_figma_figma__get_design_context`.

## Preflight: working-directory normalization

At the top of any Python snippet you run, normalize the working directory so `lib.*` imports resolve regardless of where the skill was invoked. Resolve the skill root portably by walking up from CWD to find `SKILL.md`:

```bash
# Resolve the skill root portably: walk up from CWD to find SKILL.md.
cd "$(python -c 'from pathlib import Path; p=Path.cwd(); print(next(q for q in [p, *p.parents] if (q/"SKILL.md").exists()))')"
```

Then add `Path.cwd() / "lib"` to `sys.path` before importing.

## Objective

Produce `01-flow-mapping.json` conforming to the skill's `schemas/flow_mapping.json`. Required shape:

```
{
  "figma_url": "<figma-url>",
  "locator_method": "nav-graph" | "name-search" | "refused",
  "confidence": "high" | "medium" | "low",
  "refused_reason": string | null,
  "mappings": [
    { "figma_frame_id": "...", "android_destination": "...", "score": int }
  ]
}
```

The `mappings[].android_destination` key name is inherited from the Android port; iOS and agnostic runs populate it with the platform's destination identifier (coordinator/view-controller name for iOS, etc.). See the spec's "Known limitations" for planned rename.

## Method (platform-agnostic)

1. **Read Figma frames.** Use Figma MCP to list all frames in the target file/node. Record their `id`, `name`, and any absolute-position hints.
2. **Refuse loudly on unusable Figma.** If every frame is default-named (e.g., `Frame 1`, `Rectangle 2`, `Group 15`, `Ellipse 7`), halt stage 1: write `01-flow-mapping.json` with `locator_method: "refused"`, a descriptive `refused_reason`, and `mappings: []`. Do not attempt a best-effort match.
3. **Pass 1 — nav-graph match (preferred).** Walk the platform's navigation structure (see platform hints below) to enumerate reachable destinations. Tokenize Figma frame names and any `--old-flow` hint; score destinations by distinct token overlap. If the top-scoring mapping exceeds a medium-confidence threshold, set `locator_method: "nav-graph"` and record mappings with their scores.
4. **Pass 2 — name-search fallback (only if Pass 1 yields no medium-confidence match).** Tokenize Figma frame names + hint. Grep against the platform's screen-unit anchors (see hints). Rank by distinct-anchor count. Set `locator_method: "name-search"`.
5. **Refuse loudly on no locatable entry.** If neither pass produces at least one high-or-medium-confidence mapping, write `locator_method: "refused"` with a `refused_reason` suggesting `--old-flow <hint>` and exit.

## Output

Write `01-flow-mapping.json` to the run dir, then regenerate the Markdown view:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "lib"))
from skill_io import atomic_write_json
from renderer import render_flow_mapping

atomic_write_json(run_dir / "01-flow-mapping.json", flow_mapping)
(run_dir / "01-flow-mapping.md").write_text(render_flow_mapping(flow_mapping))
```

<!-- PLATFORM_HINTS -->
