# Stage 01 — Flow locator (platform-agnostic core)

## Inputs

- `00-run-config.json` — contains `figma_url`, `old_flow_hint` (optional), `platform`, `hint_source`.
- The current repository (CWD).
- Figma MCP access via `mcp__plugin_figma_figma__get_metadata` and `mcp__plugin_figma_figma__get_design_context`.

## Preflight: working-directory normalization

At the top of any Python snippet you run, normalize the working directory so `lib.*` imports resolve regardless of where the skill was invoked. Resolve the skill root portably by walking up from CWD to find `SKILL.md`:

```bash
# Resolve the skill root portably: walk up from CWD to find SKILL.md, with
# fallback to the standard install location when CWD is outside the skill tree.
cd "$(python -c 'import sys; from pathlib import Path; p=Path.cwd(); fb=Path.home()/".claude"/"skills"/"design-coverage"; cands=[q for q in [p,*p.parents,fb] if (q/"SKILL.md").exists()]; print(cands[0]) if cands else sys.exit("design-coverage skill not found")')"
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

## Multi-anchor disambiguation (wave 3 #4)

After the candidate-class grep loop (Pass 1 and/or Pass 2) has produced candidates,
run multi-anchor detection **before** writing `01-flow-mapping.json`.

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "lib"))
from hint_frontmatter import parse_hint_frontmatter

# multi_anchor_suffixes comes from the platform hint's frontmatter.
# Default to [] when the field is absent (hint has no ambiguous-suffix pairs).
hint_text = (PLATFORMS_DIR / f"{context.platform}.md").read_text(encoding="utf-8")
fm = parse_hint_frontmatter(hint_text)
multi_anchor_suffixes: list[str] = fm.get("multi_anchor_suffixes", [])


def _strip_suffix(name: str, suffixes: list[str]) -> str:
    """Return name with the first matching suffix removed; original name if none match."""
    for sfx in suffixes:
        if name.endswith(sfx):
            return name[: -len(sfx)]
    return name


# Group candidates by their stripped base name.
from collections import defaultdict
groups: dict[str, list[dict]] = defaultdict(list)
for candidate in candidates:  # each dict has at least "class_name", "file", "mtime", "lines"
    base = _strip_suffix(candidate["class_name"], multi_anchor_suffixes)
    groups[base].append(candidate)

# For each group with N ≥ 2 members, ask the user which to use.
for base_name, group in sorted(groups.items()):
    if len(group) < 2:
        continue
    # Build a choice list for AskUserQuestion.
    choices = [
        f"{c['class_name']} ({c['file']}, last modified {c['mtime']}, {c['lines']} lines)"
        for c in group
    ]
    question = (
        f"Found multiple anchors sharing base `{base_name}`:\n"
        + "".join(f"  - {ch}\n" for ch in choices)
        + "\nWhich should anchor the audit?"
    )
    # Ask interactively — never a file handoff.
    answer = AskUserQuestion(question, choices)
    selected_class = next(
        c["class_name"] for c in group if answer.startswith(c["class_name"])
    )
    # Remove non-selected candidates from the list.
    candidates = [c for c in candidates if c["class_name"] not in
                  [g["class_name"] for g in group] or c["class_name"] == selected_class]
    # Record the choice in run-config.
    run_config["selected_anchor"] = selected_class
    run_config["selected_anchor_reason"] = "user-picked-multi-anchor"
    # Persist the updated run-config.
    import json
    (run_dir / "00-run-config.json").write_text(
        json.dumps(run_config, indent=2), encoding="utf-8"
    )
```

> **Invariant:** Multi-anchor disambiguation is **interactive in-session** (via the
> live `AskUserQuestion` interface). Never write the question to a file for the user
> to edit offline. If `multi_anchor_suffixes` is empty or no group has N ≥ 2
> candidates, this block is a no-op and the run proceeds normally.

## Output

Write `01-flow-mapping.json` to the run dir, then regenerate the Markdown view:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "lib"))
from skill_io import validate_and_write_json
from renderer import render_flow_mapping
from skill_root import get_skill_root

validate_and_write_json(
    run_dir / "01-flow-mapping.json",
    flow_mapping,
    "flow_mapping.json",
    get_skill_root() / "schemas",
)
(run_dir / "01-flow-mapping.md").write_text(render_flow_mapping(flow_mapping))
```

> Scratch reminder: any intermediate file produced by this stage (debug
> dumps, classification scratch) goes to `<run_dir>/.scratch/`, never the
> run-dir top level.

<!-- PLATFORM_HINTS -->
