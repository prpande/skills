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

After stage 6, print the path to `<run-dir>/06-report.md` to the user.
