# Stage 6 — Report Generator

## Purpose

Join the Stage 5 comparison into a developer-facing report: a coverage matrix (rows = Figma frames, columns = code screens, cells = status) plus a flat summary ordered errors-first.

## Resumability

**First action:** read `<run_dir>/run.json`. Skip if `stages["6"].status == "completed"`.

## Inputs

- `<run_dir>/comparison.json` (Stage 5)
- `<run_dir>/flow_mapping.json` (Stage 1) — for framing the summary header
- `<run_dir>/figma_inventory.json` (Stage 4) — for `screenshot_cross_check` references

## Output

Write `<run_dir>/report.json`. Schema: [`schemas/report.json`](../schemas/report.json).

Shape:

```
{
  "summary": [
    { "severity": "info" | "warn" | "error", "message": "...", "screen": string | null }
  ],
  "matrix": [
    { "figma_frame": "...", "android_screen": string | null, "status": "present" | "missing" | "new-in-figma" | "restructured" }
  ]
}
```

Then regenerate `<run_dir>/report.md` via `lib/renderer.py:render_report`. The renderer orders the summary errors-first and prints the matrix as a Markdown table.

## Python environment note — `cd` before importing `lib.renderer`

Any Python snippet that imports `lib.renderer` must `cd` into `~/.claude/skills/design-coverage/` first, otherwise the module resolution will fail because `lib/` is not on the default import path from the run dir. This is an iOS review-fix carried over.

```bash
cd ~/.claude/skills/design-coverage/
```

Then:

```python
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "lib"))
from skill_io import atomic_write_json, read_json
from renderer import render_report

run_dir = Path("<absolute path to run dir>")
comparison = read_json(run_dir / "comparison.json")

report = build_report(comparison)  # join Stage 5 rows into summary + matrix

atomic_write_json(run_dir / "report.json", report)
(run_dir / "report.md").write_text(render_report(report))

run = read_json(run_dir / "run.json")
run["stages"]["6"]["status"] = "completed"
atomic_write_json(run_dir / "run.json", run)
```

## What the summary should contain

- Every Stage 5 row whose severity is `error` or `warn` becomes a summary entry, keyed by its `screen` (the code screen, or the Figma frame if code is absent).
- `info` rows are included but sorted after errors and warnings.
- Groups entries by screen within each severity bucket for readability.

## What the matrix should contain

One row per (Figma frame, code screen) pair from Stage 5 Pass 1. Missing-in-figma-only rows show `android_screen: null`; missing-in-code-only rows show the code screen and status `missing`.
