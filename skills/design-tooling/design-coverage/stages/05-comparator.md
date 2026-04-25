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

## Severity assignment (deterministic — wave 1)

Severity is no longer agent judgment. For each comparator row, compute the
tuple `(status, kind, hotspot_type, clarification_answer)` and call
`severity_matrix.lookup(...)`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "lib"))
from skill_root import get_skill_root
from severity_matrix import lookup, flush_misses

# At start of stage 05: clear any stale per-process miss buffer.
import severity_matrix
severity_matrix._MISS_BUFFER.clear()

# For each row being assembled:
severity = lookup(
    status=row["status"],            # "present" | "missing" | "new-in-figma" | "restructured"
    kind=row.get("code_kind"),       # "screen" | "state" | "action" | "field" | None
    hotspot_type=row.get("hotspot_type"),  # one of hotspot.type enum values, or None
    clarification_answer=row.get("clarification_answer"),  # from 03-clarifications.json or None
)
row["severity"] = severity

# At end of stage, flush any unknown-tuple misses for audit (call ONCE):
flush_misses(run_dir / "_severity_lookup_misses.json")
```

Unknown tuples fall back to `"warn"` and are recorded to
`_severity_lookup_misses.json` at the run-dir top level so the matrix can be
grown over time. The miss file is the ONE allowed `_*.json` file at the top
level of the run-dir.

The previous prose-based severity rules are removed entirely. If a row's
severity looks wrong, the fix is to add an entry to `lib/severity_matrix.py`'s
`SEVERITY_MATRIX` dict, NOT to override the call site.

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
