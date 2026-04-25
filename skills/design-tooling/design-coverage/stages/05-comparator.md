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
`severity_matrix.lookup(...)`. The `clarification_answer` comes from
`03-clarifications.json` joined on `hotspot_id`; the canonical
`hotspot_id` format is `f"{hotspot_type}:{symbol}"` and MUST match the
format stage 03 uses when persisting to `clarifications.resolved[]`.

`kind` and `hotspot_type` are NOT carried on the comparator row itself
(`schemas/comparison.json` keeps rows minimal — `pass`, `status`, `severity`,
`code_ref`, `figma_ref`, `evidence`). Both fields are derived by joining
`row.code_ref` against the stage-2 inventory's `items[].id`. The join is
ephemeral — do NOT persist `code_kind` or `inventory_item_hotspot` onto
the comparison row, only the resulting `severity`.

For `pass: "screen"` rows whose `code_ref` is a sub-screen item (state /
action / field) and whose hotspot lives on the parent screen, walk up
through `parent_id` until a hotspot is found or `parent_id` is null —
this propagates the screen-level clarification to its descendants.

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "lib"))
from skill_root import get_skill_root
from severity_matrix import lookup, flush_misses, reset_misses
from skill_io import read_json

# Start of stage: clear miss buffer to keep audit per-run.
reset_misses()

# Load clarifications and build hotspot_id -> answer map.
# hotspot_id format is "<hotspot_type>:<symbol>" (must match stage 03's write).
clarifications = read_json(run_dir / "03-clarifications.json") or {"resolved": []}
hotspot_answers = {r["hotspot_id"]: r["answer"] for r in clarifications.get("resolved", [])}

# Load stage-2 inventory and index by id for the join.
inventory = read_json(run_dir / "02-code-inventory.json") or {"items": []}
items_by_id = {i["id"]: i for i in inventory.get("items", [])}

def _hotspot_for(item: dict | None) -> dict | None:
    """Walk up parent_id until a hotspot is found or the chain ends."""
    cur = item
    while cur is not None:
        if cur.get("hotspot"):
            return cur["hotspot"]
        cur = items_by_id.get(cur.get("parent_id")) if cur.get("parent_id") else None
    return None

# For each comparator row, join into stage-2 inventory and look up severity.
for row in rows:
    item = items_by_id.get(row.get("code_ref")) if row.get("code_ref") else None
    code_kind = item.get("kind") if item else None
    hotspot = _hotspot_for(item)
    hotspot_type = hotspot.get("type") if hotspot else None
    if hotspot:
        hotspot_id = f"{hotspot_type}:{hotspot['symbol']}"
        clarification_answer = hotspot_answers.get(hotspot_id)
    else:
        clarification_answer = None

    severity = lookup(
        status=row["status"],
        kind=code_kind,
        hotspot_type=hotspot_type,
        clarification_answer=clarification_answer,
    )
    row["severity"] = severity

# End of stage: flush misses for audit (call ONCE).
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
# Resolve the skill root portably: walk up from CWD to find SKILL.md, with
# fallback to the standard install location when CWD is outside the skill tree.
cd "$(python -c 'import sys; from pathlib import Path; p=Path.cwd(); fb=Path.home()/".claude"/"skills"/"design-tooling"/"design-coverage"; cands=[q for q in [p,*p.parents,fb] if (q/"SKILL.md").exists()]; print(cands[0]) if cands else sys.exit("design-coverage skill not found")')"
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
