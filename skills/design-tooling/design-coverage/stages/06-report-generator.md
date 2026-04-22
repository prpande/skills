# Stage 6 — Report Generator

## Purpose

Join the Stage 5 comparison into a developer-facing report: a coverage matrix (rows = Figma frames, columns = code screens, cells = status) plus a flat summary ordered errors-first.

## Resumability

**First action:** check whether `<run_dir>/06-report.json` already exists. If it does, skip (day-one stage resume is artifact-based; see spec "Run config artifact").

## Inputs

- `<run_dir>/05-comparison.json` (Stage 5)
- `<run_dir>/01-flow-mapping.json` (Stage 1) — for framing the summary header
- `<run_dir>/04-figma-inventory.json` (Stage 4) — for `screenshot_cross_check` references

## Output

Write `<run_dir>/06-report.json`. Schema: [`schemas/report.json`](../schemas/report.json).

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

Then regenerate `<run_dir>/06-report.md` via `lib/renderer.py:render_report`. The renderer orders the summary errors-first and prints the matrix as a Markdown table.

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
comparison = read_json(run_dir / "05-comparison.json")

report = build_report(comparison)  # join Stage 5 rows into summary + matrix

atomic_write_json(run_dir / "06-report.json", report)
(run_dir / "06-report.md").write_text(render_report(report))
```

## What the summary should contain

- Every Stage 5 row whose severity is `error` or `warn` becomes a summary entry, keyed by its `screen` (the code screen, or the Figma frame if code is absent).
- `info` rows are included but sorted after errors and warnings.
- Groups entries by screen within each severity bucket for readability.

## What the matrix should contain

The matrix is **keyed by Figma frame** (schema requires `figma_frame` to be a non-null string). It contains one row per Figma frame appearing in Stage 5 Pass 1. Mapping from Stage 5 statuses:

- `status: "present"` — `figma_frame` + matching `android_screen`.
- `status: "new-in-figma"` (Figma frame has no matching code screen) — `figma_frame` filled, `android_screen: null`.
- `status: "restructured"` — `figma_frame` + the matched `android_screen`; status preserves the Stage 5 judgment about structural change.
- `status: "missing"` (code screen has no matching Figma frame) — **not represented in the matrix**, since there is no `figma_frame` to key on. These appear in the `summary` section only (with `screen: <the code screen>` and a severity per Stage 5's rules).

If a deployment needs `missing` rows on a matrix (e.g., for a code-first coverage view), that is a follow-up schema change; day one is Figma-keyed only.

## Narrative summary (NOT this stage)

This stage writes the deterministic audit view (`06-report.md`). The verdict-first narrative summary at `06-report.json` → `06-summary.md` is rendered by the **main session**, not a subagent, once this stage returns. See SKILL.md § "Final output" for the required structure. Keeping the narrative render out-of-stage means this stage stays deterministic and testable; the narrative is explicitly labeled non-deterministic.
