# Stage 5 — Two-Pass Comparator

## Purpose

Compare the code inventory (from Stage 2, clarified by Stage 3) against the Figma inventory (from Stage 4) in two passes — flow-level for missing / new screens, and screen-level for restructured content.

## Resumability

**First action:** check whether `<run_dir>/05-comparison.json` already exists. If it does, skip (day-one stage resume is artifact-based; see spec "Run config artifact").

## Inputs

- `<run_dir>/02-code-inventory.json` (Stage 2)
- `<run_dir>/03-clarifications.json` (Stage 3)
- `<run_dir>/04-figma-inventory.json` (Stage 4)

## Output

Write `<run_dir>/05-comparison.json`. Schema: [`schemas/comparison.json`](../schemas/comparison.json).

Shape:

```
{
  "rows": [
    {
      "pass": "flow" | "screen",
      "status": "present" | "missing" | "new-in-figma" | "restructured",
      "severity": "info" | "warn" | "error",
      "code_ref": string | null,
      "figma_ref": string | null,
      "evidence": string | null
    }
  ]
}
```

Then regenerate `<run_dir>/05-comparison.md` via the inline pattern shown in "Atomic write pattern" below.

## Pass 1 — flow-level

Match Figma frames (screens) to code screens at the flow level. Emit one row per Figma frame and one row per code screen:

- Code screen has a matching Figma frame → `status: "present"`, `pass: "flow"`.
- Code screen has no matching Figma frame → `status: "missing"` (entirely missing from the design), `pass: "flow"`.
- Figma frame has no matching code screen → `status: "new-in-figma"`, `pass: "flow"`.

## Pass 2 — screen-level

For each Pass 1 `present` pair, compare the states / actions / fields inside the matched screens:

- Every state/action/field matches → emit `status: "present"`, `pass: "screen"`.
- Content exists in code but not in Figma (or vice versa), or moved between states → `status: "restructured"`, `pass: "screen"`.

## Severity rules

Severity **must** be set on every row (including `present` and `new-in-figma`). This is a regression the iOS skill shipped with; we fix it up front.

- `error` — `missing` or `restructured` with a confirmed action or field loss.
- `warn` — `restructured` without loss, or `missing` where a Stage 3 clarification says the branch is out of scope (record that justification in `evidence`).
- `info` — `present` and `new-in-figma`.

**Cross-check bump:** if the row references a Figma frame with `screenshot_cross_check: "disagreed"` in `04-figma-inventory.json`, bump severity one level (`info` → `warn`, `warn` → `error`).

**Stage 1 low-confidence downgrade:** if `01-flow-mapping.json.confidence == "low"`, every row's severity downgrades one step toward `warn` **only when the locator's low confidence could plausibly be the cause** — prefer over-reporting to silence.

## Atomic write pattern

```bash
# Resolve the skill root portably: walk up from CWD to find SKILL.md.
cd "$(python -c 'from pathlib import Path; p=Path.cwd(); print(next(q for q in [p, *p.parents] if (q/"SKILL.md").exists()))')"
```

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "lib"))
from skill_io import atomic_write_json
from renderer import render_comparison

atomic_write_json(run_dir / "05-comparison.json", comparison)
(run_dir / "05-comparison.md").write_text(render_comparison(comparison))
```
