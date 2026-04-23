---
name: design-coverage
description: >
  Compare an existing in-code UI flow against a new Figma design and produce
  an auditable, confidence-tagged discrepancy report. Runs a six-stage pipeline:
  flow locator → code inventory → interactive clarification → Figma inventory →
  two-pass comparator → report generator. Platform-agnostic core with optional
  per-platform hint files under platforms/<name>.md (ios and android shipped
  day one). Refuses loudly on unusable Figma input or unlocatable flows. Use
  when the user says "run design coverage", "/design-coverage <figma-url>",
  or wants to catch missing scenarios before implementation.
argument-hint: "<figma-url> [--old-flow <hint>] [--platform <name>] [--output-dir <path>]"
allowed-tools: Bash, Read, Edit, Write, Glob, Grep, Agent, mcp__plugin_figma_figma__get_metadata, mcp__plugin_figma_figma__get_design_context, mcp__plugin_figma_figma__get_screenshot
---

# design-coverage

Orchestrates a six-stage pipeline over the current repository and a Figma
design URL. Stages 01, 02, 03 are platform-aware (a hint file is substituted
into a `<!-- PLATFORM_HINTS -->` marker). Stages 04, 05, 06 are agnostic.

## Preflight

At the top of any Python snippet, normalize the working directory so `lib.*`
imports resolve regardless of where the skill was invoked:

```bash
cd ~/.claude/skills/design-coverage/
```

Then add `Path.cwd() / "lib"` to `sys.path` before importing.

## Argument parsing

Parse the invocation string:
- Required positional: `<figma-url>`
- Optional flags:
  - `--old-flow <hint>` — disambiguate flow detection
  - `--platform <name>` — one of `ios`, `android`, `agnostic`, or any name
    matching `platforms/<name>.md`
  - `--output-dir <path>` — override default artifact location

Store in `context.args`.

## Platform resolution (runs once, before stage 1)

1. If `--platform <name>` is provided:
   - If `name == "agnostic"`, set `context.platform = "agnostic"`,
     `context.hint_source = "flag"`, skip hint loading.
   - Else, load `~/.claude/skills/design-coverage/platforms/<name>.md`.
     If missing, refuse loudly:
     `No hint file for platform '<name>'. Available: <list glob>`.

2. Else, auto-detect by globbing each existing `platforms/*.md` frontmatter
   `detect` patterns against CWD:

```python
import sys, pathlib, re
sys.path.insert(0, str(pathlib.Path.home() / ".claude" / "skills" / "design-coverage" / "lib"))
from detect import detect_match

platforms_dir = pathlib.Path.home() / ".claude" / "skills" / "design-coverage" / "platforms"
fm_pat = re.compile(r"\A---\s*\r?\n(.*?)\r?\n---\s*\r?\n", re.DOTALL)
matches = []
for hint in sorted(platforms_dir.glob("*.md")):
    text = hint.read_text(encoding="utf-8")
    m = fm_pat.match(text)
    if not m:
        continue
    fm = m.group(1)
    name = ""
    detect_globs: list[str] = []
    in_detect = False
    for line in fm.splitlines():
        if line.startswith("name:"):
            name = line.split(":", 1)[1].strip()
            in_detect = False
        elif line.startswith("detect:"):
            in_detect = True
        elif in_detect:
            stripped = line.lstrip()
            if stripped.startswith("- "):
                detect_globs.append(stripped[2:].strip().strip('"'))
            elif line and not line[0].isspace():
                in_detect = False
    cwd = pathlib.Path.cwd()
    for g in detect_globs:
        if detect_match(cwd, g):
            matches.append(name)
            break
print(matches)
```

`detect_match` bounds the walk at a max depth and excludes common large
directories (`node_modules`, `Pods`, `DerivedData`, `build`, `.git`, …) —
see `lib/detect.py`. An unbounded `Path.cwd().glob("**/…")` would scan
the whole tree on every invocation, which is unacceptable in monorepos.

3. Branch on the match count:
   - **Exactly one** → `context.platform = matches[0]`,
     `context.hint_source = "detection"`, log to `00-run-config.json`.
   - **Multiple** → refuse loudly:
     `Multiple platform hints match CWD: {matches}. Pass --platform <name> to disambiguate.`
   - **Zero** → unknown-stack branch below.

## Unknown-stack branch (live prompt)

Ask the user, directly in this session:

> No existing platform hint matches this repository. Choose:
> (a) generate a hint now (runs design-coverage-scout)
> (b) name a platform from the shipped list
> (c) proceed agnostic (no hint file)

- **(a)** — dispatch the `Agent` tool with `subagent_type: "general-purpose"`,
  prompt: _"Follow the instructions in `~/.claude/skills/design-coverage-scout/SKILL.md`
  to generate a hint for this repo."_ Wait for scout to produce
  `platforms/<name>.md` (user approves the draft). On success, reload platform
  resolution and proceed. On scout refusal, fall through to (c).
- **(b)** — set `context.platform`, `context.hint_source = "user-prompt"`,
  load the hint.
- **(c)** — set `context.platform = "agnostic"`,
  `context.hint_source = "user-prompt"`, skip hint loading.

## Run directory

```bash
cd ~/.claude/skills/design-coverage/
# Pass the flow name via env var so apostrophes / quotes / `$` in the value
# don't break the inline `python -c` invocation.
FLOW_SLUG=$(FLOW_NAME="<flow-name>" python -c "import sys, os; sys.path.insert(0, 'lib'); from slugify import slugify; print(slugify(os.environ['FLOW_NAME']))")
RUN_DIR="<output-dir>/docs/design-coverage/$(date +%Y-%m-%d)-$FLOW_SLUG"
mkdir -p "$RUN_DIR"
```

Where `<output-dir>` is `--output-dir <path>` if provided, else the Git root
of CWD.

Write `00-run-config.json` (see spec "Run config artifact (day-one shape)" — this captures args + platform resolution; the ported `schemas/run.json` describes a stages-status file that day-one orchestrator does NOT write):

```json
{
  "figma_url": "<from args>",
  "old_flow_hint": "<from args or null>",
  "platform": "<resolved>",
  "hint_source": "<resolved>",
  "skill_version": "<git SHA of ~/.claude/skills/design-coverage/ realpath>"
}
```

## Hint injection

For each of stages 01, 02, 03, compose the stage prompt by replacing the
`<!-- PLATFORM_HINTS -->` marker with the matching section from the hint
file (or with nothing when agnostic):

```python
import pathlib
skill_root = pathlib.Path.home() / ".claude" / "skills" / "design-coverage"
stage_file = skill_root / "stages" / "01-flow-locator.md"  # or 02, 03
platform = context.platform
core = stage_file.read_text(encoding="utf-8")
if platform == "agnostic":
    composed = core.replace("<!-- PLATFORM_HINTS -->", "")
else:
    hint_file = skill_root / "platforms" / f"{platform}.md"
    hint_text = hint_file.read_text(encoding="utf-8")
    section_map = {
        "01": "## 01 Flow locator",
        "02": "## 02 Code inventory",
        "03": "## 03 Clarification",
    }
    stage_num = stage_file.stem.split("-", 1)[0]
    header = section_map[stage_num]
    lines = hint_text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip() == header)
    end = next(
        (i for i in range(start + 1, len(lines))
         if lines[i].startswith("## ") and lines[i].strip() != header),
        len(lines),
    )
    hint_section = "\n".join(lines[start + 1:end]).strip("\n")
    injected = f"\n## Platform-specific hints ({platform})\n\n{hint_section}\n"
    composed = core.replace("<!-- PLATFORM_HINTS -->", injected)
(run_dir / f"{stage_file.stem}-prompt.md").write_text(composed)
```

Dispatch a subagent with the composed prompt for each stage.

## Stage pipeline

Run stages 01 → 06 in sequence. Each stage writes its JSON artifact and
regenerates the matching Markdown view by importing the appropriate
`lib.renderer.render_*` function from inline Python (see each stage's
Output section for the exact snippet).

- **01 — Flow locator** (hint-injected): `stages/01-flow-locator.md`
- **02 — Code inventory** (hint-injected): `stages/02-code-inventory.md`
- **03 — Clarification** (hint-injected, interactive): `stages/03-clarification.md`
- **04 — Figma inventory**: `stages/04-figma-inventory.md`
- **05 — Comparator**: `stages/05-comparator.md`
- **06 — Report generator**: `stages/06-report-generator.md`

Resumable by flow-slug — on re-run, skip any stage whose artifact already
exists in the run directory.

## Final output

After stage 6 writes the deterministic `<run-dir>/06-report.md` (audit view), run the **stage-6 narrative render** in the main session — do NOT dispatch a subagent for this step. Read `<run-dir>/06-report.json` and render a verdict-first summary to `<run-dir>/06-summary.md`.

The summary is for a designer / engineer reviewer who has ~2 minutes before their next meeting. Optimize for that reader: prose-first, prioritized, collapsed where noisy. Do NOT mechanically enumerate.

### Required structure

1. **Non-deterministic banner** at the very top — a comment explaining provenance:

   ```
   <!-- Rendered by the main session from 06-report.json on <ISO-date>.
        Non-deterministic — re-running /design-coverage may produce different
        prose. The deterministic audit view is 06-report.md. -->
   ```

2. **One-line verdict** immediately after the title: `> **Verdict:** 🟢 Ready to ship` / `🟡 Caveats below` / `🔴 Not ready to ship: <one-sentence reason>`. Pick color by highest-severity summary entry (any `error` → red; any `warn` and no error → yellow; else green). The reason cites the specific gap that blocks shipping ("the Resource Picker modal has no Figma frame"), not a count ("2 errors need review").

3. **Next 5 actions** — a numbered list of the 5 most actionable rows the reader should work on first (errors before warnings, highest-severity warnings before lower). One sentence each, imperative voice, beginning with a verb ("Ask design to add…", "Confirm with product whether…", "Drop the legacy X path…"). This is what the reader reads in the first 30 seconds — it must be the top of the file, not buried after the tally.

4. **Severity tally table** — counts of 🔴/🟠/ℹ️ summary entries + counts of matrix statuses (`missing`, `new-in-figma`, `restructured`, `present`). Use the emoji in the table cells, not just the headers.

5. **Sections per severity bucket**, in this order:
   - **🔴 Errors** — each error as its own subsection. Required content per error: the row's `code_ref` / `figma_ref`, one-sentence reasoning, and a concrete "what to do" sentence that starts with a verb ("Ask design to…", "Document that…", "Drop the X branch if…"). **No ambiguity-punting prose** like "needs explicit product confirmation" without a proposed ask.
   - **🟠 Warnings** — group by **underlying design decision**, not by severity tag or by clarification Q-ID. Cluster related items: "all three cancel-with-auto-email variants trace to one dropped feature — one fix". The group name should be in reviewer-facing product language ("Bottom toolbar collapse", "Notes screen extraction", "Status-chip consolidation"), not audit shorthand ("Q10/Q11 fold"). If one design decision produces > 20 warning rows, the decision itself is a cluster worth calling out in its own subsection.
   - **🟡 Restructured** — same grouping principle (by design decision, not by Q-ID). Open with a banner reminding the reader these are intentional moves, not bugs: *"The N restructured rows below are not bugs — they are places the legacy shape is being intentionally rebuilt. Review to confirm intent; do NOT treat as defects."*
   - **⚪ New in Figma** — summarize into themed buckets (`Coachmarks`, `Milestones`, `Skeleton loading`, `Haptics`, …), counts only. Do NOT enumerate individual rows — link to `06-report.md` for the full list.

6. **Wrap long sections in `<details>`** — any section with ≥ 20 rows MUST be wrapped in `<details><summary>…</summary>…</details>` so GitHub collapses it by default. The `<summary>` must carry the bucket name AND the row count so the reader can see the scale without expanding (example: `<summary><b>Bottom toolbar collapse — 38 rows</b></summary>`).

7. **Where to start** — 3–5 numbered bullets at the bottom prioritizing errors over warnings, with concrete next actions. Separate from "Next 5 actions" at the top — that's raw-priority; this is operator-guidance ("Walk the 62 missing rows with product in one session; decide which are dropped vs oversight").

### Forbidden / pitfalls

- **Do NOT group by severity tag alone** ("🟠 Warnings" is a section header, not a group). Always cluster related rows under a design-decision name.
- **Do NOT enumerate the full matrix.** If a section would exceed ~30 bullets, collapse it with `<details>` or bucket it.
- **Do NOT paste verbatim clarifications.** They live in `03-clarifications.md`; link to that file.
- **Do NOT soften error action prose.** "Needs confirmation" is wrong. "Ask design to add a frame for the Resource Picker, or document that resource-required appointments are out of scope for the new flow" is right.

### Mechanics

Use the `Write` tool to create `06-summary.md` directly. Then print the path to both files so the user can open either:

```
Audit view:     <run-dir>/06-report.md
Narrative view: <run-dir>/06-summary.md   ← start here
```
