# design-coverage platform-agnostic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship two user-level Claude Code skills — `design-coverage` (platform-agnostic Figma-vs-code audit) and `design-coverage-scout` (companion skill that bootstraps per-platform hint files) — under `skills/design-tooling/`, superseding the platform-specific iOS (#5349) and Android (#5190) PRs.

**Architecture:** Thin Python orchestration + LLM-led stage subagents. Main skill has a 6-stage pipeline with marker-substituted platform hints at stages 1–3. Scout has a 3-stage pipeline that emits a hint file conforming to a shared structural template. All artifacts are JSON source-of-truth with regenerated Markdown views carrying DO-NOT-EDIT banners and sha256 headers.

**Tech Stack:** Python 3.11+ (stdlib only — no external deps), pytest, hand-rolled JSON-Schema validator, Claude Code skill format (`SKILL.md` frontmatter + `stages/*.md` subagent prompts).

---

## Setup

### Pre-task 0: Fetch source content from the two existing PRs

**Why:** Tasks T9, T10, and many test ports depend on content from PRs #5349 (MindBodyPOS) and #5190 (Express-Android). Fetch these into a temporary reference tree once, then discard after porting is done.

- [ ] **Step 1: Create temp reference dir outside the worktree**

```bash
mkdir -p /tmp/design-coverage-refs/ios
mkdir -p /tmp/design-coverage-refs/android
```

- [ ] **Step 2: Fetch iOS PR (#5349) files needed**

```bash
cd /tmp/design-coverage-refs/ios
for f in \
  ".claude/skills/design-coverage/SKILL.md" \
  ".claude/skills/design-coverage/README.md" \
  ".claude/skills/design-coverage/lib/validator.py" \
  ".claude/skills/design-coverage/lib/renderer.py" \
  ".claude/skills/design-coverage/lib/rundir.py" \
  ".claude/skills/design-coverage/lib/retry.py" \
  ".claude/skills/design-coverage/lib/inventory.py" \
  ".claude/skills/design-coverage/stages/01-flow-locator.md" \
  ".claude/skills/design-coverage/stages/02-code-inventory.md" \
  ".claude/skills/design-coverage/stages/04-figma-inventory.md" \
  ".claude/skills/design-coverage/stages/05-comparator.md" \
  ".claude/skills/design-coverage/stages/06-report-generator.md" \
  ".claude/skills/design-coverage/schemas/00-run-config.schema.json" \
  ".claude/skills/design-coverage/schemas/01-flow-mapping.schema.json" \
  ".claude/skills/design-coverage/schemas/02-code-inventory.schema.json" \
  ".claude/skills/design-coverage/schemas/03-clarifications.schema.json" \
  ".claude/skills/design-coverage/schemas/04-figma-inventory.schema.json" \
  ".claude/skills/design-coverage/schemas/05-comparison-matrix.schema.json" \
  ".claude/skills/design-coverage/schemas/06-coverage-matrix.schema.json" \
  ".claude/skills/design-coverage/schemas/inventory-item.schema.json"; do
    mkdir -p "$(dirname "$f")"
    gh api "repos/mindbody/MindBodyPOS/contents/$f?ref=refs/pull/5349/head" \
      --jq '.content' | base64 -d > "$f"
done
```

- [ ] **Step 3: Fetch Android PR (#5190) files needed**

```bash
cd /tmp/design-coverage-refs/android
for f in \
  ".claude/skills/design-coverage/SKILL.md" \
  ".claude/skills/design-coverage/README.md" \
  ".claude/skills/design-coverage/lib/validator.py" \
  ".claude/skills/design-coverage/lib/renderer.py" \
  ".claude/skills/design-coverage/lib/skill_io.py" \
  ".claude/skills/design-coverage/lib/slugify.py" \
  ".claude/skills/design-coverage/stages/01-flow-locator.md" \
  ".claude/skills/design-coverage/stages/02-code-inventory/2a-discovery.md" \
  ".claude/skills/design-coverage/stages/02-code-inventory/2b-focused-reads.md" \
  ".claude/skills/design-coverage/stages/02-code-inventory/2c-cross-linking.md" \
  ".claude/skills/design-coverage/stages/03-clarification.md" \
  ".claude/skills/design-coverage/stages/04-figma-inventory.md" \
  ".claude/skills/design-coverage/stages/05-comparator.md" \
  ".claude/skills/design-coverage/stages/06-report-generator.md" \
  ".claude/skills/design-coverage/schemas/run.json" \
  ".claude/skills/design-coverage/schemas/inventory_item.json" \
  ".claude/skills/design-coverage/schemas/flow_mapping.json" \
  ".claude/skills/design-coverage/schemas/code_inventory.json" \
  ".claude/skills/design-coverage/schemas/clarifications.json" \
  ".claude/skills/design-coverage/schemas/figma_inventory.json" \
  ".claude/skills/design-coverage/schemas/comparison.json" \
  ".claude/skills/design-coverage/schemas/report.json"; do
    mkdir -p "$(dirname "$f")"
    gh api "repos/mindbody/Express-Android/contents/$f?ref=refs/pull/5190/head" \
      --jq '.content' | base64 -d > "$f"
done
```

- [ ] **Step 4: Fetch all Android PR test files**

```bash
cd /tmp/design-coverage-refs/android
gh api "repos/mindbody/Express-Android/contents/skill-tests/design-coverage?ref=refs/pull/5190/head" \
  --jq '.[] | .path' | while read f; do
    mkdir -p "$(dirname "$f")"
    gh api "repos/mindbody/Express-Android/contents/$f?ref=refs/pull/5190/head" \
      --jq '.content' | base64 -d > "$f"
  done
# Recursively walk subdirs:
find skill-tests/design-coverage -type d | while read d; do
    gh api "repos/mindbody/Express-Android/contents/$d?ref=refs/pull/5190/head" \
      --jq '.[] | select(.type == "file") | .path' 2>/dev/null | while read f; do
        mkdir -p "$(dirname "$f")"
        gh api "repos/mindbody/Express-Android/contents/$f?ref=refs/pull/5190/head" \
          --jq '.content' | base64 -d > "$f"
    done
done
```

- [ ] **Step 5: Verify fetches**

```bash
ls -R /tmp/design-coverage-refs/ios/.claude/skills/design-coverage/
ls -R /tmp/design-coverage-refs/android/.claude/skills/design-coverage/
ls -R /tmp/design-coverage-refs/android/skill-tests/
```
Expected: all files listed above exist and are non-empty.

---

## Task 1: Extend `scripts/validate.py` with hint-frontmatter rule

**Files:**
- Modify: `scripts/validate.py`
- Test: `scripts/test_validate_hints.py` (new)

**Rationale:** The existing validator auto-discovers skill roots under `skills/**`, so no walker changes needed. We only add a rule that lints any Markdown file under `skills/*/design-coverage/platforms/*.md` for required frontmatter (`name`, `detect`, `description`, `confidence`) and required section headers (`## 01 Flow locator`, `## 02 Code inventory`, `## 03 Clarification`).

- [ ] **Step 1: Write the failing test**

Create `scripts/test_validate_hints.py`:

```python
"""Test the hint-frontmatter lint rule in validate.py."""
from __future__ import annotations
import pathlib
import subprocess
import sys
import textwrap

REPO = pathlib.Path(__file__).resolve().parent.parent


def run_validator(tmpdir: pathlib.Path) -> subprocess.CompletedProcess:
    """Run validate.py from tmpdir (which acts as a fake repo root)."""
    return subprocess.run(
        [sys.executable, str(REPO / "scripts" / "validate.py")],
        cwd=tmpdir,
        capture_output=True,
        text=True,
    )


def make_minimal_skill(root: pathlib.Path, name: str) -> None:
    skill = root / "skills" / "design-tooling" / name
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text(textwrap.dedent(f"""\
        ---
        name: {name}
        description: Stub skill for lint tests.
        ---
        # {name}
    """))


def test_valid_hint_passes(tmp_path: pathlib.Path) -> None:
    make_minimal_skill(tmp_path, "design-coverage")
    platforms = tmp_path / "skills" / "design-tooling" / "design-coverage" / "platforms"
    platforms.mkdir()
    (platforms / "ios.md").write_text(textwrap.dedent("""\
        ---
        name: ios
        detect:
          - "**/*.xcodeproj"
          - "Package.swift"
        description: iOS stack hint.
        confidence: high
        ---

        ## 01 Flow locator
        Test.

        ## 02 Code inventory
        Test.

        ## 03 Clarification
        Test.
    """))
    result = run_validator(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_missing_frontmatter_fails(tmp_path: pathlib.Path) -> None:
    make_minimal_skill(tmp_path, "design-coverage")
    platforms = tmp_path / "skills" / "design-tooling" / "design-coverage" / "platforms"
    platforms.mkdir()
    (platforms / "ios.md").write_text("No frontmatter here.\n")
    result = run_validator(tmp_path)
    assert result.returncode != 0
    assert "frontmatter" in (result.stdout + result.stderr).lower()


def test_missing_section_header_fails(tmp_path: pathlib.Path) -> None:
    make_minimal_skill(tmp_path, "design-coverage")
    platforms = tmp_path / "skills" / "design-tooling" / "design-coverage" / "platforms"
    platforms.mkdir()
    (platforms / "ios.md").write_text(textwrap.dedent("""\
        ---
        name: ios
        detect: ["*.xcodeproj"]
        description: iOS.
        confidence: high
        ---

        ## 01 Flow locator
        Only one section.
    """))
    result = run_validator(tmp_path)
    assert result.returncode != 0
    assert "02 code inventory" in (result.stdout + result.stderr).lower() \
        or "03 clarification" in (result.stdout + result.stderr).lower()
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `cd /c/src/skills-worktrees/design-coverage-platform-agnostic && python -m pytest scripts/test_validate_hints.py -v`

Expected: 3 FAIL (rule not implemented yet).

- [ ] **Step 3: Add the rule to validate.py**

At the top of `scripts/validate.py`, add imports:

```python
import yaml  # stdlib? no — use our own minimal parser
```

Actually stdlib has no YAML. Use a minimal ad-hoc parser since our frontmatter is simple. Add this function after the `discover_skill_roots` function:

```python
REQUIRED_HINT_SECTIONS = [
    "## 01 Flow locator",
    "## 02 Code inventory",
    "## 03 Clarification",
]
REQUIRED_HINT_FM_KEYS = {"name", "detect", "description", "confidence"}
VALID_CONFIDENCE = {"high", "medium", "low"}


def validate_hint_file(path: pathlib.Path) -> list[str]:
    """Return list of error strings for a platforms/*.md hint file."""
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER.match(text)
    if not m:
        return [f"{path}: missing frontmatter block"]
    fm_text = m.group(1)
    body = text[m.end():]
    # Minimal frontmatter key extraction.
    keys: dict[str, str] = {}
    current_key: str | None = None
    for line in fm_text.splitlines():
        if line.startswith(("  ", "\t", "-")):
            continue  # list-value continuation
        if ":" in line:
            k, _, v = line.partition(":")
            k = k.strip()
            v = v.strip()
            if k:
                keys[k] = v
                current_key = k
    missing = REQUIRED_HINT_FM_KEYS - set(keys)
    if missing:
        errors.append(
            f"{path}: frontmatter missing keys: {sorted(missing)}"
        )
    if keys.get("confidence") and keys["confidence"] not in VALID_CONFIDENCE:
        errors.append(
            f"{path}: frontmatter 'confidence' must be one of {sorted(VALID_CONFIDENCE)}, got {keys['confidence']!r}"
        )
    for section in REQUIRED_HINT_SECTIONS:
        if section not in body:
            errors.append(
                f"{path}: missing required section header {section!r}"
            )
    return errors
```

Then in the main validation loop (search for `errors: list[str] = []` near the bottom), after the existing SKILL.md / placeholder / reference checks, add:

```python
    # Hint-frontmatter lint rule: any .md under platforms/ inside a
    # design-coverage skill root must satisfy the hint contract.
    for root in roots.values():
        platforms = root / "platforms"
        if not platforms.is_dir():
            continue
        for hint_file in platforms.glob("*.md"):
            errors.extend(validate_hint_file(hint_file))
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `python -m pytest scripts/test_validate_hints.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Run the full validator to confirm no regressions**

Run: `python scripts/validate.py`
Expected: `OK` on stdout, exit 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/validate.py scripts/test_validate_hints.py
git commit -m "validate: add hint-frontmatter lint for design-coverage platforms/*.md"
```

---

## Task 2: Port `lib/` (validator, skill_io, renderer, slugify)

**Files:**
- Create: `skills/design-tooling/design-coverage/lib/__init__.py`
- Create: `skills/design-tooling/design-coverage/lib/validator.py`
- Create: `skills/design-tooling/design-coverage/lib/skill_io.py`
- Create: `skills/design-tooling/design-coverage/lib/renderer.py`
- Create: `skills/design-tooling/design-coverage/lib/slugify.py`

**Rationale:** Port the Android PR's library files verbatim. They are stronger than the iOS PR's (validator fixes a `$ref` bug, `skill_io` renamed from `io` to avoid pytest stdlib collision, renderer uses deterministic JSON serialization for sha256 stability).

- [ ] **Step 1: Create the directory and copy files**

```bash
DEST=/c/src/skills-worktrees/design-coverage-platform-agnostic/skills/design-tooling/design-coverage/lib
SRC=/tmp/design-coverage-refs/android/.claude/skills/design-coverage/lib
mkdir -p "$DEST"
touch "$DEST/__init__.py"
cp "$SRC/validator.py" "$DEST/validator.py"
cp "$SRC/skill_io.py" "$DEST/skill_io.py"
cp "$SRC/renderer.py" "$DEST/renderer.py"
cp "$SRC/slugify.py" "$DEST/slugify.py"
```

- [ ] **Step 2: Verify file contents are non-empty and match Android PR**

Run: `wc -l skills/design-tooling/design-coverage/lib/*.py`
Expected:
- `validator.py` ≈79 lines
- `skill_io.py` ≈48 lines
- `renderer.py` ≈106 lines
- `slugify.py` ≈11 lines

- [ ] **Step 3: Commit**

```bash
git add skills/design-tooling/design-coverage/lib/
git commit -m "design-coverage: port lib/ (validator, skill_io, renderer, slugify) from Android PR #5190"
```

---

## Task 3: Port schemas

**Files:**
- Create: `skills/design-tooling/design-coverage/schemas/inventory_item.json`
- Create: `skills/design-tooling/design-coverage/schemas/flow_mapping.json`
- Create: `skills/design-tooling/design-coverage/schemas/code_inventory.json`
- Create: `skills/design-tooling/design-coverage/schemas/clarifications.json`
- Create: `skills/design-tooling/design-coverage/schemas/figma_inventory.json`
- Create: `skills/design-tooling/design-coverage/schemas/comparison.json`
- Create: `skills/design-tooling/design-coverage/schemas/report.json`
- Create/Modify: `skills/design-tooling/design-coverage/schemas/run.json` (adds `platform`, `hint_source`, `skill_version`)

- [ ] **Step 1: Copy schemas verbatim from Android PR**

```bash
DEST=/c/src/skills-worktrees/design-coverage-platform-agnostic/skills/design-tooling/design-coverage/schemas
SRC=/tmp/design-coverage-refs/android/.claude/skills/design-coverage/schemas
mkdir -p "$DEST"
cp "$SRC"/*.json "$DEST/"
```

- [ ] **Step 2: Extend `run.json` with new top-level fields**

Read the ported `run.json` and add the three new required fields. Open `skills/design-tooling/design-coverage/schemas/run.json` and add to the `required` array and `properties` block:

```jsonc
{
  "properties": {
    // ...existing...
    "platform": {
      "type": "string",
      "minLength": 1
    },
    "hint_source": {
      "type": "string",
      "enum": ["detection", "flag", "user-prompt", "scout-generated", "agnostic"]
    },
    "skill_version": {
      "type": "string",
      "minLength": 1
    }
  },
  "required": [
    // ...existing...,
    "platform",
    "hint_source",
    "skill_version"
  ]
}
```

- [ ] **Step 3: Verify all schemas parse as valid JSON**

Run:
```bash
python -c "import json, pathlib; [json.loads(p.read_text()) for p in pathlib.Path('skills/design-tooling/design-coverage/schemas').glob('*.json')]; print('OK')"
```
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add skills/design-tooling/design-coverage/schemas/
git commit -m "design-coverage: port schemas from Android PR, extend run.json with platform/hint_source/skill_version"
```

---

## Task 4: Port stages 04, 05, 06 verbatim

**Files:**
- Create: `skills/design-tooling/design-coverage/stages/04-figma-inventory.md`
- Create: `skills/design-tooling/design-coverage/stages/05-comparator.md`
- Create: `skills/design-tooling/design-coverage/stages/06-report-generator.md`

**Rationale:** These three stages are platform-agnostic in both existing PRs. Lifted verbatim from Android PR.

- [ ] **Step 1: Copy stage files**

```bash
DEST=/c/src/skills-worktrees/design-coverage-platform-agnostic/skills/design-tooling/design-coverage/stages
SRC=/tmp/design-coverage-refs/android/.claude/skills/design-coverage/stages
mkdir -p "$DEST"
cp "$SRC/04-figma-inventory.md" "$DEST/04-figma-inventory.md"
cp "$SRC/05-comparator.md" "$DEST/05-comparator.md"
cp "$SRC/06-report-generator.md" "$DEST/06-report-generator.md"
```

- [ ] **Step 2: Adjust any path references**

In any of the three files, search for `.claude/skills/design-coverage/` and replace with `~/.claude/skills/design-coverage/` (since the skill now installs via symlink at user level, not checked into target repo).

```bash
cd /c/src/skills-worktrees/design-coverage-platform-agnostic
for f in skills/design-tooling/design-coverage/stages/0{4,5,6}*.md; do
  sed -i 's|\.claude/skills/design-coverage/|~/.claude/skills/design-coverage/|g' "$f"
done
```

- [ ] **Step 3: Commit**

```bash
git add skills/design-tooling/design-coverage/stages/04-figma-inventory.md \
        skills/design-tooling/design-coverage/stages/05-comparator.md \
        skills/design-tooling/design-coverage/stages/06-report-generator.md
git commit -m "design-coverage: port stages 04/05/06 verbatim from Android PR"
```

---

## Task 5: Write core stages 01, 02, 03 with `<!-- PLATFORM_HINTS -->` markers

**Files:**
- Create: `skills/design-tooling/design-coverage/stages/01-flow-locator.md`
- Create: `skills/design-tooling/design-coverage/stages/02-code-inventory.md`
- Create: `skills/design-tooling/design-coverage/stages/03-clarification.md`

**Rationale:** These are the platform-agnostic cores. Read the Android and iOS versions for reference, then write neutral-voice prompts that end with `<!-- PLATFORM_HINTS -->`.

- [ ] **Step 1: Write stage 01 — Flow locator (agnostic core)**

Write `skills/design-tooling/design-coverage/stages/01-flow-locator.md`:

````markdown
# Stage 01 — Flow locator (platform-agnostic core)

## Inputs

- `00-run-config.json` — contains `figma_url`, `old_flow_hint` (optional), `platform`, `hint_source`.
- The current repository (CWD).
- Figma MCP access via `mcp__plugin_figma_figma__get_metadata` and `mcp__plugin_figma_figma__get_design_context`.

## Preflight: working-directory normalization

At the top of any Python snippet you run, normalize the working directory so `lib.*` imports resolve regardless of where the skill was invoked:

```bash
cd ~/.claude/skills/design-coverage/
```

Then add `Path.cwd() / "lib"` to `sys.path` before importing.

## Objective

Produce `01-flow-mapping.json` conforming to `~/.claude/skills/design-coverage/schemas/flow_mapping.json`. It must contain:
- `entry_screen` — the starting screen's code anchor
- `destinations[]` — each reachable screen with `figma_frame_id`, `figma_frame_name`, `code_anchor`, and `match_confidence`
- `unwalked[]` — Figma frames we could not match in code (and why, briefly)

## Method (platform-agnostic)

1. **Read Figma frames.** Use Figma MCP to list all frames in the target file/node. Record their `id`, `name`, and any absolute-position hints.
2. **Refuse loudly on unusable Figma.** If every frame is default-named (e.g., `Frame 1`, `Rectangle 2`, `Group 15`, `Ellipse 7`), halt stage 1 with a clear message pointing the user to rename frames before retrying. Do not attempt a best-effort match.
3. **Locate the entry screen in code** by name correspondence:
   - Strongest signal: exact class/file/component name match on the Figma entry frame's name.
   - Secondary signal: fuzzy token overlap (e.g., Figma frame "Appointment Details" matches a code anchor `AppointmentDetailsViewModel`).
   - If `old_flow_hint` is set, weigh it above fuzzy matches.
4. **Walk the navigation structure** to enumerate reachable destinations. The navigation mechanism varies by stack — see the platform-specific hints below for how it looks here.
5. **Name-only fallback.** If navigation walking is inconclusive, fall back to matching every Figma frame name against code anchors and record `match_confidence: "name-only"` on any that resolve only by name.
6. **Refuse loudly on no locatable entry.** If you cannot locate the entry screen with at least `match_confidence: "name-only"`, halt stage 1 and suggest the user rerun with `--old-flow <hint>`.

## Output

Write `01-flow-mapping.json` to the run directory. Regenerate the Markdown view with `python -m lib.renderer --render 1 <run-dir>`.

<!-- PLATFORM_HINTS -->
````

- [ ] **Step 2: Write stage 02 — Code inventory (agnostic core)**

Write `skills/design-tooling/design-coverage/stages/02-code-inventory.md`:

````markdown
# Stage 02 — Code inventory (platform-agnostic core)

## Inputs

- `01-flow-mapping.json` from stage 1.
- The current repository.

## Preflight

```bash
cd ~/.claude/skills/design-coverage/
```

## Objective

For each screen in the flow, enumerate its inventory items — screens, states, actions, fields — and emit `02-code-inventory.json` conforming to `~/.claude/skills/design-coverage/schemas/code_inventory.json` with rows conforming to the shared `inventory_item.json` fragment.

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
- **One row per item.** Do not duplicate inventory items across modes; represent mode-dependence as a field on the item (`modes: ["admin", "user"]`).
- **No speculation.** Only include items present in code. If a comment references a feature that isn't implemented, do not record it.

## Output

Write `02-code-inventory.json` and regenerate the Markdown view via `python -m lib.renderer --render 2 <run-dir>`.

<!-- PLATFORM_HINTS -->
````

- [ ] **Step 3: Write stage 03 — Clarification (agnostic core)**

Write `skills/design-tooling/design-coverage/stages/03-clarification.md`:

````markdown
# Stage 03 — Clarification (platform-agnostic core)

## Inputs

- `02-code-inventory.json` from stage 2.
- Live interactive session with the user.

## Preflight

```bash
cd ~/.claude/skills/design-coverage/
```

## Objective

Resolve hotspots — decision points whose rendered UI depends on runtime data that stage 2 cannot fully inspect statically (feature flags, permissions, server-driven content, responsive branches, user roles, etc.). Ask the human live, in-session, one question at a time. Write answers to `03-clarifications.json`.

**This stage runs in the main session. Do not hand off a file for the user to edit — ask directly.**

## Method (platform-agnostic)

1. **Identify hotspots** from the code inventory:
   - States whose entry condition depends on a flag / permission / role / server-driven response.
   - Fields whose visibility is conditional on the above.
   - Screens that branch by responsive config or device capability.
   - Lists whose item types vary by runtime data.
   - Any component annotated or named in a way that suggests runtime variance.
2. **Short-circuit on empty.** If the hotspot list is empty, write `{"resolved": []}` to `03-clarifications.json` immediately and exit. Do not enter a dialogue with no questions.
3. **Ask sequentially.** For each hotspot, pose a single concrete question to the user. Record the answer and its impact on the inventory (if any — e.g., a flag confirmation may promote a state from "speculative" to "real").

## Output

Write `03-clarifications.json` conforming to `~/.claude/skills/design-coverage/schemas/clarifications.json`. Regenerate via `python -m lib.renderer --render 3 <run-dir>`.

<!-- PLATFORM_HINTS -->
````

- [ ] **Step 4: Commit**

```bash
git add skills/design-tooling/design-coverage/stages/01-flow-locator.md \
        skills/design-tooling/design-coverage/stages/02-code-inventory.md \
        skills/design-tooling/design-coverage/stages/03-clarification.md
git commit -m "design-coverage: write core stages 01/02/03 with PLATFORM_HINTS marker"
```

---

## Task 6: Write main SKILL.md orchestrator

**Files:**
- Create: `skills/design-tooling/design-coverage/SKILL.md`
- Create: `skills/design-tooling/design-coverage/README.md`

- [ ] **Step 1: Write SKILL.md**

Create `skills/design-tooling/design-coverage/SKILL.md`:

````markdown
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

Orchestrates a six-stage pipeline over the current repository and a Figma design URL.

## Preflight

At the top of any Python snippet, normalize CWD:

```bash
cd ~/.claude/skills/design-coverage/
```

## Argument parsing

Parse the invocation string:
- Required positional: `<figma-url>`
- Optional flags: `--old-flow <hint>`, `--platform <name>`, `--output-dir <path>`

Store in `context.args`.

## Platform resolution (runs once, before stage 1)

1. If `--platform <name>` is provided:
   - If `name == "agnostic"`, set `context.platform = "agnostic"`, `context.hint_source = "flag"`, skip hint loading.
   - Else, load the hint file at `~/.claude/skills/design-coverage/platforms/<name>.md`. If missing, refuse loudly: "No hint file for platform '<name>'. Available: ios, android, agnostic."
2. Else, auto-detect by globbing each existing `platforms/*.md` frontmatter `detect` patterns against CWD. Use this Python snippet:

```python
import pathlib, re
platforms_dir = pathlib.Path.home() / ".claude" / "skills" / "design-coverage" / "platforms"
fm_pat = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
matches = []
for hint in platforms_dir.glob("*.md"):
    text = hint.read_text(encoding="utf-8")
    m = fm_pat.match(text)
    if not m:
        continue
    fm = m.group(1)
    name_line = next((l for l in fm.splitlines() if l.startswith("name:")), "")
    name = name_line.split(":", 1)[1].strip()
    detect_globs = []
    in_detect = False
    for l in fm.splitlines():
        if l.startswith("detect:"):
            in_detect = True
            continue
        if in_detect:
            if l.startswith("- "):
                detect_globs.append(l[2:].strip().strip('"'))
            elif l and not l.startswith(" "):
                in_detect = False
    for g in detect_globs:
        if list(pathlib.Path.cwd().glob(g)):
            matches.append(name)
            break
print(matches)
```

3. Branch on the match count:
   - **Exactly one** → set `context.platform = matches[0]`, `context.hint_source = "detection"`, log to `run.json`.
   - **Multiple** → refuse loudly: `"Multiple platform hints match CWD: {matches}. Pass --platform <name> to disambiguate."`
   - **Zero** → unknown-stack branch below.

## Unknown-stack branch (live prompt)

Ask the user, directly in this session:

> "No existing platform hint matches this repository. Choose:
> (a) generate a hint now (runs design-coverage-scout)
> (b) name a platform from [ios, android]
> (c) proceed agnostic (no hint file)"

- **(a)** — dispatch the `Agent` tool with `subagent_type: "general-purpose"`, prompt: "Follow the instructions in `~/.claude/skills/design-coverage-scout/SKILL.md` to generate a hint for this repo." Wait for scout to produce `platforms/<name>.md` (user approves the draft). On success, reload platform resolution and proceed. On scout refusal, fall through to (c).
- **(b)** — set `context.platform`, `context.hint_source = "user-prompt"`, load the hint.
- **(c)** — set `context.platform = "agnostic"`, `context.hint_source = "user-prompt"`, skip hint loading.

## Run directory

```bash
RUN_DIR="<output-dir>/docs/design-coverage/$(date +%Y-%m-%d)-$(python -m lib.slugify <flow-name>)"
mkdir -p "$RUN_DIR"
```

Where `<output-dir>` is `--output-dir <path>` if provided, else the Git root of CWD.

Write `00-run-config.json`:

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

For each of stages 01, 02, 03:

```python
import pathlib
skill_root = pathlib.Path.home() / ".claude" / "skills" / "design-coverage"
stage_file = skill_root / "stages" / "01-flow-locator.md"  # or 02, 03
platform = context.platform  # or "agnostic"
core = stage_file.read_text(encoding="utf-8")
if platform == "agnostic":
    composed = core.replace("<!-- PLATFORM_HINTS -->", "")
else:
    hint_file = skill_root / "platforms" / f"{platform}.md"
    hint_text = hint_file.read_text(encoding="utf-8")
    # Extract the section matching this stage's number from the hint.
    # Section headers: "## 01 Flow locator", "## 02 Code inventory", "## 03 Clarification"
    section_map = {"01": "## 01 Flow locator", "02": "## 02 Code inventory", "03": "## 03 Clarification"}
    stage_num = stage_file.stem.split("-", 1)[0]
    header = section_map[stage_num]
    lines = hint_text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip() == header)
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ") and lines[i].strip() != header), len(lines))
    hint_section = "\n".join(lines[start + 1:end]).strip()
    injected = f"\n## Platform-specific hints ({platform})\n\n{hint_section}\n"
    composed = core.replace("<!-- PLATFORM_HINTS -->", injected)
(run_dir / f"{stage_file.stem}-prompt.md").write_text(composed)
```

Dispatch a subagent with the composed prompt for each stage.

## Stage pipeline

Run stages 01 → 06 in sequence. Each stage writes its JSON artifact and Markdown view. Resumable by flow-slug — on re-run, skip any stage whose artifact already exists.

Stages 04, 05, 06 are platform-agnostic; no hint injection.

## Final output

After stage 6, print the path to `<run-dir>/06-summary.md` to the user.
````

- [ ] **Step 2: Write README.md**

Create `skills/design-tooling/design-coverage/README.md`:

```markdown
# design-coverage

A platform-agnostic Claude Code skill that compares an existing in-code UI flow
against a new Figma design and produces an auditable, confidence-tagged
discrepancy report.

## Quick start

```bash
# Install
ln -s "$PWD/skills/design-tooling/design-coverage" "$HOME/.claude/skills/design-coverage"
# Restart Claude Code session.

# Run from inside a target repo worktree:
/design-coverage <figma-url>
```

## Arguments

- `<figma-url>` — required, e.g. `https://figma.com/design/<fileKey>/...?node-id=<nodeId>`
- `--old-flow <hint>` — optional string to disambiguate flow detection
- `--platform <name>` — one of `ios`, `android`, `agnostic`
- `--output-dir <path>` — override default artifact location

## Platform hints

Day-one hints shipped under `platforms/`:
- `ios.md` — ported from MindBodyPOS #5349
- `android.md` — ported from Express-Android #5190

For unknown stacks, run `design-coverage-scout` to generate a new hint, or pass
`--platform agnostic` to run without platform-specific guidance.

## Artifacts

Runs land at `<target-repo>/docs/design-coverage/<YYYY-MM-DD>-<flow-slug>/`:
- `00-run-config.json` + 01…06 stage artifacts (JSON source of truth)
- Regenerated Markdown views with `DO-NOT-EDIT` banners

## Design & plan

- [Design](../../../docs/superpowers/specs/2026-04-22-design-coverage-platform-agnostic-design.md)
- [Implementation plan](../../../docs/superpowers/plans/2026-04-22-design-coverage-platform-agnostic.md)
```

- [ ] **Step 3: Run the validator**

Run: `python scripts/validate.py`
Expected: `OK`. If it fails with a frontmatter or reference error in the new files, fix and re-run.

- [ ] **Step 4: Commit**

```bash
git add skills/design-tooling/design-coverage/SKILL.md \
        skills/design-tooling/design-coverage/README.md
git commit -m "design-coverage: orchestrator SKILL.md with platform resolution + README"
```

---

## Task 7: Port test harness (conftest + Android PR tests)

**Files:**
- Create: `skill-tests/design-coverage/conftest.py`
- Create: `skill-tests/design-coverage/tests/test_*.py` (all ported from Android PR)
- Create: `skill-tests/design-coverage/fixtures/**` (all ported from Android PR)

- [ ] **Step 1: Copy tests + fixtures**

```bash
DEST=/c/src/skills-worktrees/design-coverage-platform-agnostic/skill-tests/design-coverage
SRC=/tmp/design-coverage-refs/android/skill-tests/design-coverage
mkdir -p "$DEST"
cp -r "$SRC"/* "$DEST/"
```

- [ ] **Step 2: Adjust `conftest.py` path to point at new skill location**

The Android PR's conftest reaches back to `.claude/skills/design-coverage/lib` via `Path.parents[N]`. Our layout has the lib at `<repo>/skills/design-tooling/design-coverage/lib`. Edit `skill-tests/design-coverage/conftest.py`:

Replace the path computation with:

```python
import sys
from pathlib import Path

# skill-tests/design-coverage/ -> <repo>/skill-tests/design-coverage
# <repo>/skills/design-tooling/design-coverage/lib
REPO = Path(__file__).resolve().parents[2]
LIB = REPO / "skills" / "design-tooling" / "design-coverage" / "lib"
sys.path.insert(0, str(LIB.parent))  # so `import lib.validator` works
```

- [ ] **Step 3: Run the ported tests as-is**

Run: `cd skill-tests/design-coverage && python -m pytest tests/ -v`
Expected: most pass; a few may fail due to:
  - `run.json` schema changes (new required fields).
  - Run-directory path references inside fixtures.
Note which tests fail and move to the next step.

- [ ] **Step 4: Update fixture `run.json` files to include new required fields**

Any fixture `run.json` file that was valid under the old schema must now include `platform`, `hint_source`, and `skill_version`. Bulk-patch:

```bash
cd /c/src/skills-worktrees/design-coverage-platform-agnostic
find skill-tests/design-coverage/fixtures -name "run.json" | while read f; do
  python - <<PY
import json, pathlib
p = pathlib.Path("$f")
data = json.loads(p.read_text())
data.setdefault("platform", "agnostic")
data.setdefault("hint_source", "agnostic")
data.setdefault("skill_version", "test-sha")
p.write_text(json.dumps(data, indent=2) + "\n")
PY
done
```

- [ ] **Step 5: Re-run tests; fix any remaining failures**

Run: `cd skill-tests/design-coverage && python -m pytest tests/ -v`
Expected: all PASS. If any fail with "import lib.X", adjust conftest path. If any fail with "run.json schema", double-check the fixture patch applied cleanly.

- [ ] **Step 6: Commit**

```bash
git add skill-tests/design-coverage/
git commit -m "design-coverage: port test harness + fixtures from Android PR, update for new run.json fields"
```

---

## Task 8: Write new tests — platform detection, hint injection, agnostic mode, hint frontmatter, multi-hint refuse

**Files:**
- Create: `skill-tests/design-coverage/tests/test_platform_detection.py`
- Create: `skill-tests/design-coverage/tests/test_hint_injection.py`
- Create: `skill-tests/design-coverage/tests/test_agnostic_mode.py`
- Create: `skill-tests/design-coverage/tests/test_hint_frontmatter.py`
- Create: `skill-tests/design-coverage/tests/test_multi_hint_refuse.py`

- [ ] **Step 1: Write `test_platform_detection.py`**

```python
"""Tests that platform detection globs platforms/*.md frontmatter correctly."""
from __future__ import annotations
import pathlib
import textwrap
import pytest


def detect_platforms(cwd: pathlib.Path, platforms_dir: pathlib.Path) -> list[str]:
    """Replica of the detection logic from SKILL.md — glob each hint's detect
    patterns against cwd and return matching platform names."""
    import re
    fm_pat = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
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
                if line.startswith("- "):
                    detect_globs.append(line[2:].strip().strip('"'))
                elif line and not line[0].isspace():
                    in_detect = False
        for g in detect_globs:
            if list(cwd.glob(g)):
                matches.append(name)
                break
    return matches


def make_hint(platforms_dir: pathlib.Path, name: str, detect: list[str]) -> None:
    platforms_dir.mkdir(parents=True, exist_ok=True)
    detect_yaml = "\n".join(f'  - "{g}"' for g in detect)
    (platforms_dir / f"{name}.md").write_text(textwrap.dedent(f"""\
        ---
        name: {name}
        detect:
        {detect_yaml}
        description: Test hint for {name}.
        confidence: high
        ---

        ## 01 Flow locator
        test
        ## 02 Code inventory
        test
        ## 03 Clarification
        test
    """))


def test_detects_ios(tmp_path: pathlib.Path) -> None:
    platforms = tmp_path / "platforms"
    make_hint(platforms, "ios", ["**/*.xcodeproj"])
    make_hint(platforms, "android", ["**/build.gradle"])
    repo = tmp_path / "repo"
    (repo / "MyApp.xcodeproj").mkdir(parents=True)
    assert detect_platforms(repo, platforms) == ["ios"]


def test_detects_android(tmp_path: pathlib.Path) -> None:
    platforms = tmp_path / "platforms"
    make_hint(platforms, "ios", ["**/*.xcodeproj"])
    make_hint(platforms, "android", ["**/build.gradle", "AndroidManifest.xml"])
    repo = tmp_path / "repo"
    (repo / "app" / "build.gradle").parent.mkdir(parents=True)
    (repo / "app" / "build.gradle").write_text("")
    assert detect_platforms(repo, platforms) == ["android"]


def test_detects_multiple(tmp_path: pathlib.Path) -> None:
    platforms = tmp_path / "platforms"
    make_hint(platforms, "ios", ["**/*.xcodeproj"])
    make_hint(platforms, "android", ["**/build.gradle"])
    repo = tmp_path / "repo"
    (repo / "iOS" / "App.xcodeproj").mkdir(parents=True)
    (repo / "android" / "build.gradle").parent.mkdir(parents=True)
    (repo / "android" / "build.gradle").write_text("")
    assert sorted(detect_platforms(repo, platforms)) == ["android", "ios"]


def test_detects_none(tmp_path: pathlib.Path) -> None:
    platforms = tmp_path / "platforms"
    make_hint(platforms, "ios", ["**/*.xcodeproj"])
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("")
    assert detect_platforms(repo, platforms) == []
```

- [ ] **Step 2: Write `test_hint_injection.py`**

```python
"""Tests that <!-- PLATFORM_HINTS --> substitution extracts the right section."""
from __future__ import annotations
import pathlib
import textwrap


def inject_hint(core_prompt: str, hint_text: str, platform: str, stage_num: str) -> str:
    """Replica of the injection logic from SKILL.md."""
    if platform == "agnostic":
        return core_prompt.replace("<!-- PLATFORM_HINTS -->", "")
    section_map = {"01": "## 01 Flow locator", "02": "## 02 Code inventory", "03": "## 03 Clarification"}
    header = section_map[stage_num]
    lines = hint_text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip() == header)
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ") and lines[i].strip() != header), len(lines))
    hint_section = "\n".join(lines[start + 1:end]).strip()
    injected = f"\n## Platform-specific hints ({platform})\n\n{hint_section}\n"
    return core_prompt.replace("<!-- PLATFORM_HINTS -->", injected)


HINT_FIXTURE = textwrap.dedent("""\
    ---
    name: ios
    detect: ["**/*.xcodeproj"]
    description: iOS.
    confidence: high
    ---

    ## 01 Flow locator
    iOS flow content.

    ## 02 Code inventory
    iOS inventory content.

    ## 03 Clarification
    iOS clarification content.
""")


def test_injects_stage_01() -> None:
    core = "Body before.\n\n<!-- PLATFORM_HINTS -->\n"
    out = inject_hint(core, HINT_FIXTURE, "ios", "01")
    assert "iOS flow content" in out
    assert "iOS inventory content" not in out
    assert "## Platform-specific hints (ios)" in out


def test_injects_stage_02() -> None:
    core = "Body.\n<!-- PLATFORM_HINTS -->\n"
    out = inject_hint(core, HINT_FIXTURE, "ios", "02")
    assert "iOS inventory content" in out
    assert "iOS flow content" not in out


def test_agnostic_removes_marker() -> None:
    core = "Body.\n<!-- PLATFORM_HINTS -->\n"
    out = inject_hint(core, HINT_FIXTURE, "agnostic", "01")
    assert "<!-- PLATFORM_HINTS -->" not in out
    assert "Platform-specific hints" not in out
```

- [ ] **Step 3: Write `test_agnostic_mode.py`**

```python
"""Tests that agnostic mode produces a composed prompt with no platform section."""
from __future__ import annotations
import pathlib
from .test_hint_injection import inject_hint


def test_agnostic_prompt_has_no_hint_section() -> None:
    core_prompt_path = pathlib.Path(__file__).resolve().parents[3] / \
        "skills" / "design-tooling" / "design-coverage" / "stages" / "01-flow-locator.md"
    core = core_prompt_path.read_text(encoding="utf-8")
    composed = inject_hint(core, "", "agnostic", "01")
    assert "<!-- PLATFORM_HINTS -->" not in composed
    assert "Platform-specific hints" not in composed
```

- [ ] **Step 4: Write `test_hint_frontmatter.py`**

```python
"""Tests that hint frontmatter validation catches malformed hints."""
from __future__ import annotations
import pathlib
import subprocess
import sys
import textwrap


REPO = pathlib.Path(__file__).resolve().parents[3]


def run_validator(cwd: pathlib.Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO / "scripts" / "validate.py")],
        cwd=cwd,
        capture_output=True, text=True,
    )


def make_skill_with_hint(root: pathlib.Path, hint_body: str) -> None:
    skill = root / "skills" / "design-tooling" / "design-coverage"
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text(textwrap.dedent("""\
        ---
        name: design-coverage
        description: Stub.
        ---
        # design-coverage
    """))
    (skill / "platforms").mkdir(exist_ok=True)
    (skill / "platforms" / "ios.md").write_text(hint_body)


def test_valid_hint_passes(tmp_path: pathlib.Path) -> None:
    make_skill_with_hint(tmp_path, textwrap.dedent("""\
        ---
        name: ios
        detect: ["*.xcodeproj"]
        description: iOS.
        confidence: high
        ---
        ## 01 Flow locator
        ok
        ## 02 Code inventory
        ok
        ## 03 Clarification
        ok
    """))
    assert run_validator(tmp_path).returncode == 0


def test_missing_name_key_fails(tmp_path: pathlib.Path) -> None:
    make_skill_with_hint(tmp_path, textwrap.dedent("""\
        ---
        detect: ["*.xcodeproj"]
        description: iOS.
        confidence: high
        ---
        ## 01 Flow locator
        x
        ## 02 Code inventory
        x
        ## 03 Clarification
        x
    """))
    r = run_validator(tmp_path)
    assert r.returncode != 0
    assert "name" in (r.stdout + r.stderr).lower()


def test_invalid_confidence_fails(tmp_path: pathlib.Path) -> None:
    make_skill_with_hint(tmp_path, textwrap.dedent("""\
        ---
        name: ios
        detect: ["*.xcodeproj"]
        description: iOS.
        confidence: yolo
        ---
        ## 01 Flow locator
        x
        ## 02 Code inventory
        x
        ## 03 Clarification
        x
    """))
    r = run_validator(tmp_path)
    assert r.returncode != 0
    assert "confidence" in (r.stdout + r.stderr).lower()
```

- [ ] **Step 5: Write `test_multi_hint_refuse.py`**

```python
"""Tests that multi-match platform detection produces an explicit refusal."""
from __future__ import annotations
import pathlib
from .test_platform_detection import detect_platforms, make_hint


def test_multi_match_returns_all(tmp_path: pathlib.Path) -> None:
    platforms = tmp_path / "platforms"
    make_hint(platforms, "ios", ["*.xcodeproj"])
    make_hint(platforms, "android", ["build.gradle"])
    repo = tmp_path / "repo"
    (repo / "App.xcodeproj").mkdir(parents=True)
    (repo / "build.gradle").write_text("")
    # In SKILL.md, a multi-match triggers a refuse-loud. The detection function
    # itself just returns the list; the refuse-loud is the orchestrator's
    # responsibility. This test pins the detection contract: it must surface
    # all matches so the orchestrator can refuse correctly.
    assert sorted(detect_platforms(repo, platforms)) == ["android", "ios"]
```

- [ ] **Step 6: Run the new tests**

Run: `cd skill-tests/design-coverage && python -m pytest tests/test_platform_detection.py tests/test_hint_injection.py tests/test_agnostic_mode.py tests/test_hint_frontmatter.py tests/test_multi_hint_refuse.py -v`
Expected: all PASS.

- [ ] **Step 7: Run the full test suite**

Run: `cd skill-tests/design-coverage && python -m pytest tests/ -v`
Expected: all PASS (including the previously-ported Android tests).

- [ ] **Step 8: Commit**

```bash
git add skill-tests/design-coverage/tests/test_platform_detection.py \
        skill-tests/design-coverage/tests/test_hint_injection.py \
        skill-tests/design-coverage/tests/test_agnostic_mode.py \
        skill-tests/design-coverage/tests/test_hint_frontmatter.py \
        skill-tests/design-coverage/tests/test_multi_hint_refuse.py
git commit -m "design-coverage: add tests for platform detection, hint injection, agnostic mode, frontmatter lint, multi-hint refuse"
```

---

## Task 9: Port `platforms/ios.md` from MindBodyPOS #5349

**Files:**
- Create: `skills/design-tooling/design-coverage/platforms/ios.md`

**Rationale:** The iOS PR's stage 1–3 content is the day-one iOS hint. Reshape it into the hint-file format (frontmatter + three sections, no `<!-- PLATFORM_HINTS -->` marker since this IS the hint content).

- [ ] **Step 1: Read the iOS PR's three stage files**

```bash
cat /tmp/design-coverage-refs/ios/.claude/skills/design-coverage/stages/01-flow-locator.md
cat /tmp/design-coverage-refs/ios/.claude/skills/design-coverage/stages/02-code-inventory.md
# Stage 03 not present in iOS PR — it's handled inline in SKILL.md.
cat /tmp/design-coverage-refs/ios/.claude/skills/design-coverage/SKILL.md | grep -A 100 "Stage 3"
```

- [ ] **Step 2: Write `platforms/ios.md`**

Create `skills/design-tooling/design-coverage/platforms/ios.md` with this skeleton; fill each section with content extracted and condensed from the iOS PR's stages. Keep the content iOS-specific only — remove any platform-agnostic preamble.

```markdown
---
name: ios
detect:
  - "**/*.xcodeproj"
  - "**/*.xcworkspace"
  - "Package.swift"
description: iOS (UIKit + SwiftUI + ObjC) hint. Ported from MindBodyPOS #5349.
confidence: high
---

## 01 Flow locator

<!--
EXTRACT FROM /tmp/design-coverage-refs/ios/.../stages/01-flow-locator.md
the iOS-specific guidance:
  - How to find flow entry: look for Coordinator / ViewModel / ViewController by name
  - How to walk navigation: UINavigationController pushes, SwiftUI NavigationStack,
    storyboard segues, programmatic presentations.
  - iOS-specific refuse conditions unique to this stack (e.g., storyboard-only
    flows with no code anchors).
Condense to platform-specific guidance. Drop any agnostic preamble.
-->

[content from iOS PR stage 1, iOS-specific only]

## 02 Code inventory

<!--
EXTRACT FROM /tmp/design-coverage-refs/ios/.../stages/02-code-inventory.md
iOS-specific discovery patterns:
  - grep for `class .*: UIViewController`, `struct .*: View`, `class .*Coordinator`
  - state: @Published properties, @State/@Binding, ViewModel properties
  - actions: @IBAction, SwiftUI .onTapGesture / Button action closures, target-action
  - fields: IBOutlets, SwiftUI body content, Table/Collection data sources
  - hybrid hosts: UIHostingController, SwiftUI inside UIKit (note cross-refs)
Condense to platform-specific guidance.
-->

[content from iOS PR stage 2, iOS-specific only]

## 03 Clarification

<!--
Derive iOS-specific hotspot topics from the iOS PR's stage-3 handling and
spec doc, typically:
  - Feature flags (FeatureFlagType enum + FeatureFlagManager)
  - Server-driven content
  - Permission gates (push, camera, location)
  - Device/size-class branches
  - A/B tests
-->

Hotspot topics to ask about when present in the inventory:
- **Feature flags** — search for `FeatureFlagType`, `FeatureFlagManager`, `ImplementationSwitch`; for each flagged branch, confirm current default.
- **Server-driven content** — lists/screens populated from network payloads; confirm expected shape.
- **Permission gates** — push, camera, microphone, location, photo-library; confirm the permission-denied path has a design.
- **Device/size-class branches** — compact vs regular horizontal size class; iPhone vs iPad; confirm intended behaviors on each.
- **A/B test hooks** — if present; confirm which variant the Figma represents.
```

Fill the inline sections by extracting the iOS-specific prose from the iOS PR's stage files. Aim for ~150–250 lines total.

- [ ] **Step 3: Run the validator**

Run: `python scripts/validate.py`
Expected: `OK` (hint frontmatter is valid, sections all present).

- [ ] **Step 4: Run the full test suite**

Run: `cd skill-tests/design-coverage && python -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/design-tooling/design-coverage/platforms/ios.md
git commit -m "design-coverage: add platforms/ios.md (ported from MindBodyPOS #5349)"
```

---

## Task 10: Port `platforms/android.md` from Express-Android #5190

**Files:**
- Create: `skills/design-tooling/design-coverage/platforms/android.md`

- [ ] **Step 1: Read the Android PR's three stage files**

```bash
cat /tmp/design-coverage-refs/android/.claude/skills/design-coverage/stages/01-flow-locator.md
cat /tmp/design-coverage-refs/android/.claude/skills/design-coverage/stages/02-code-inventory/2a-discovery.md
cat /tmp/design-coverage-refs/android/.claude/skills/design-coverage/stages/02-code-inventory/2b-focused-reads.md
cat /tmp/design-coverage-refs/android/.claude/skills/design-coverage/stages/02-code-inventory/2c-cross-linking.md
cat /tmp/design-coverage-refs/android/.claude/skills/design-coverage/stages/03-clarification.md
```

- [ ] **Step 2: Write `platforms/android.md`**

Same structure as ios.md:

```markdown
---
name: android
detect:
  - "**/build.gradle"
  - "**/build.gradle.kts"
  - "**/AndroidManifest.xml"
description: Android (Compose + Fragment/XML + hybrid ComposeView) hint. Ported from Express-Android #5190.
confidence: high
---

## 01 Flow locator

<!--
EXTRACT from Android PR stage 1:
  - nav-graph-first: res/navigation/*.xml
  - Compose-Nav: NavHost, composable() destinations, route-constant resolution for sealed classes
  - name-search fallback
  - refuse conditions (unnamed frames, ambiguous nav)
-->

[content]

## 02 Code inventory

<!--
EXTRACT from Android PR stage 2 (2a-discovery, 2b-focused-reads, 2c-cross-linking):
  - Discovery patterns: @Composable, AndroidView, class .*Fragment, class .*Activity
  - Fragment + XML layout pairing; hybrid ComposeView hosts (two rows, cross-ref via hybrid-host:<id>)
  - State containers: ViewModel, StateFlow, SavedStateHandle
  - Actions: onClick lambdas, OnClickListeners, Compose .clickable, swipes
  - Fields: TextViews, RecyclerView ViewHolders, Compose content
-->

[content]

## 03 Clarification

<!--
EXTRACT Android-specific hotspot topics:
  - Feature flags
  - Runtime permissions
  - Server-driven content
  - Config qualifiers (values-night, RTL, sw600dp)
  - Phone/tablet branches
  - Process-death restore
  - RecyclerView view types
  - ViewPager2 tabs
  - BottomSheet/Dialog state variants
-->

Hotspot topics to ask about when present in the inventory:
- **Feature flags** — flag pattern names; for each flagged branch, confirm current default.
- **Runtime permissions** — camera, mic, location, notifications; confirm permission-denied paths.
- **Server-driven content** — list/screen content from network; confirm expected shape.
- **Config qualifiers** — `values-night/` (dark mode), RTL (`values-ldrtl/`), `sw600dp/` (tablets), density qualifiers.
- **Phone/tablet branches** — confirm both layouts are in the Figma.
- **Process-death restore** — SavedStateHandle survives; confirm restore state matches Figma.
- **RecyclerView view types** — each item type; confirm design covers them all.
- **ViewPager2 tabs** — each tab page; confirm Figma covers all.
- **BottomSheet/Dialog state variants** — collapsed vs expanded, loading vs loaded; confirm design covers each.
```

Fill inline sections by extracting Android-specific content from the Android PR's stage files. ~200–300 lines total (Android has more surface area than iOS due to Compose + Fragment + hybrid).

- [ ] **Step 3: Run the validator**

Run: `python scripts/validate.py`
Expected: `OK`.

- [ ] **Step 4: Run the full test suite**

Run: `cd skill-tests/design-coverage && python -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/design-tooling/design-coverage/platforms/android.md
git commit -m "design-coverage: add platforms/android.md (ported from Express-Android #5190)"
```

---

## Task 11: Write scout's `hint-template.md`

**Files:**
- Create: `skills/design-tooling/design-coverage-scout/hint-template.md`

- [ ] **Step 1: Write the template**

```bash
mkdir -p skills/design-tooling/design-coverage-scout
```

Create `skills/design-tooling/design-coverage-scout/hint-template.md`:

````markdown
# Platform hint template

Every `platforms/<name>.md` file inside `design-coverage/` must conform to the
shape below. The main skill's hint-injection logic and the repo's structural
validator both enforce this.

## Required frontmatter

```yaml
---
name: <short-lowercase-platform-name>          # Required. Lowercase, hyphen-separated.
detect:                                         # Required. At least one glob.
  - "<glob>"                                    #   e.g. "**/*.xcodeproj", "Package.swift"
description: <one-line summary>                 # Required.
confidence: high | medium | low                 # Required.
---
```

**`detect` globs.** The main skill matches each glob against the current working
directory. If ANY glob matches, the platform is considered detected. If
multiple hints detect, the orchestrator refuses and asks the user to pass
`--platform <name>`.

**`confidence: low` or `medium`** signals the hint was auto-generated and may
miss platform-specific patterns. Scout emits `confidence: medium` by default;
a human curator should review and promote to `high` after validation.

## Required sections

### `## 01 Flow locator`

Platform-specific guidance for stage 1 of design-coverage. Explain:
- The platform's navigation mechanism (nav graph, router config, stack-based,
  coordinator-based, etc.).
- How the entry screen of a flow is typically named/declared.
- Refuse-loud conditions specific to this stack (e.g., storyboard-only flows
  with no code anchors).

### `## 02 Code inventory`

Platform-specific guidance for stage 2:
- How screens are declared (framework-specific class/decorator/component
  patterns).
- How state is held (state containers, hooks, observables, etc.).
- How actions are attached (event handlers, closures, decorators).
- How fields are rendered (text views, bindings, JSX, etc.).
- How hybrid hosts are detected and represented (if the platform has any —
  e.g., UIHostingController on iOS, ComposeView on Android).

### `## 03 Clarification`

A list of hotspot topics stage 3 should ask the human about. Each should be
one line describing what to look for and what to confirm.

## Optional sections

### `## Unresolved questions`

If `confidence < high`, scout emits this section with bullet-list items the
hint author was unsure about. A human curator resolves these and removes the
section before promoting confidence.

## Style

- **Imperative voice.** "Grep for X," "Check Y," not "The developer should
  look at X."
- **Concrete patterns, not abstract advice.** "Grep for `@Composable` fun
  declarations" beats "look for composable components."
- **Link to code.** Reference the actual tokens the stack uses, not
  paraphrased equivalents.
- **Keep each section focused.** If it grows past ~100 lines, split into
  clearly labeled sub-sections.
````

- [ ] **Step 2: Verify the template itself passes the hint lint rule**

The template is inside `design-coverage-scout/`, not `design-coverage/platforms/`, so the validator will ignore it. Confirm by running:

```bash
python scripts/validate.py
```
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add skills/design-tooling/design-coverage-scout/hint-template.md
git commit -m "design-coverage-scout: add structural hint-template.md"
```

---

## Task 12: Write scout's schemas

**Files:**
- Create: `skills/design-tooling/design-coverage-scout/schemas/hint_draft.json`

- [ ] **Step 1: Write the schema**

```bash
mkdir -p skills/design-tooling/design-coverage-scout/schemas
```

Create `skills/design-tooling/design-coverage-scout/schemas/hint_draft.json`:

```json
{
  "type": "object",
  "required": ["name", "detect", "description", "confidence", "sections"],
  "properties": {
    "name": {
      "type": "string",
      "minLength": 1
    },
    "detect": {
      "type": "array",
      "minItems": 1,
      "items": { "type": "string", "minLength": 1 }
    },
    "description": {
      "type": "string",
      "minLength": 1
    },
    "confidence": {
      "type": "string",
      "enum": ["high", "medium", "low"]
    },
    "sections": {
      "type": "object",
      "required": ["flow_locator", "code_inventory", "clarification"],
      "properties": {
        "flow_locator":   { "type": "string", "minLength": 1 },
        "code_inventory": { "type": "string", "minLength": 1 },
        "clarification":  { "type": "string", "minLength": 1 }
      }
    },
    "unresolved_questions": {
      "type": "array",
      "items": { "type": "string", "minLength": 1 }
    }
  }
}
```

- [ ] **Step 2: Verify JSON parses**

```bash
python -c "import json; json.loads(open('skills/design-tooling/design-coverage-scout/schemas/hint_draft.json').read()); print('OK')"
```
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add skills/design-tooling/design-coverage-scout/schemas/hint_draft.json
git commit -m "design-coverage-scout: add hint_draft.json schema"
```

---

## Task 13: Write scout's stage prompts

**Files:**
- Create: `skills/design-tooling/design-coverage-scout/stages/01-stack-profile.md`
- Create: `skills/design-tooling/design-coverage-scout/stages/02-pattern-extraction.md`
- Create: `skills/design-tooling/design-coverage-scout/stages/03-hint-rendering.md`

- [ ] **Step 1: Write stage 01**

```bash
mkdir -p skills/design-tooling/design-coverage-scout/stages
```

Create `skills/design-tooling/design-coverage-scout/stages/01-stack-profile.md`:

````markdown
# Scout Stage 01 — Stack profile

## Inputs
- The current repository (CWD).

## Objective
Emit `stack-profile.json` characterizing the UI stack of this repo. The downstream
stage-2 prompt uses it to decide which patterns to harvest.

## Method

1. **Identify the primary language(s).** File extension tallies — `.swift`, `.kt`, `.java`,
   `.tsx/.ts/.jsx/.js`, `.dart`, `.vue`. If it's a monorepo with multiple UI trees,
   REFUSE LOUDLY and list the candidates; ask the user to scope to one.
2. **Identify the build system.** `Package.swift`, `build.gradle(.kts)`, `package.json`,
   `pubspec.yaml`, `Podfile`, `.xcodeproj`.
3. **Identify the UI framework.**
   - iOS: UIKit (UIViewController) vs SwiftUI (`: View`) vs mixed.
   - Android: Jetpack Compose (`@Composable`) vs Fragment/XML vs hybrid (ComposeView).
   - Web: React / Vue / Angular / Svelte; SSR vs CSR; meta-framework (Next, Nuxt, SvelteKit).
   - Cross-platform: React Native (`@react-navigation`), Flutter (MaterialApp),
     Compose Multiplatform.
4. **Identify the navigation style.**
   - Graph-based (Android nav graph, TanStack Router).
   - Router-config (React Router, Vue Router).
   - Stack-based imperative (UIKit).
   - Declarative (SwiftUI NavigationStack, Compose Navigation).
   - Coordinator pattern.
5. **Identify the state-container convention.**
   - ViewModel + observable (Android, SwiftUI `@ObservableObject`).
   - Store pattern (Redux, Pinia, Zustand).
   - Hooks (React `useState`/`useContext`).
   - BLoC (Flutter).
6. **Identify hybrid-host patterns** if any exist
   (UIHostingController, ComposeView, React-in-Angular bridges).

## Refuse conditions

- **Multi-UI monorepo** — refuse, list candidate sub-trees, ask user to re-run in a sub-tree.
- **No UI detected at all** — refuse, point user at `hint-template.md` for manual authoring.

## Output

Write `<run-dir>/stack-profile.json`:

```jsonc
{
  "primary_language": "kotlin",
  "build_system": "gradle",
  "ui_framework": "compose + fragment/xml",
  "navigation_style": "nav-graph + compose-nav",
  "state_container": "viewmodel + stateflow",
  "hybrid_hosts": true,
  "confidence": "high"
}
```
````

- [ ] **Step 2: Write stage 02**

Create `skills/design-tooling/design-coverage-scout/stages/02-pattern-extraction.md`:

````markdown
# Scout Stage 02 — Pattern extraction

## Inputs
- `stack-profile.json` from stage 1.
- The current repository.

## Objective
For each of the three required hint sections (`01 Flow locator`, `02 Code inventory`,
`03 Clarification`), harvest concrete patterns from this repo that will be rendered
into `platforms/<name>.md` in stage 3. Write `hint-draft.json` conforming to
`~/.claude/skills/design-coverage-scout/schemas/hint_draft.json`.

## Method

### For `flow_locator` section
- Find 1–2 concrete examples of how flows are declared (the file glob, the class/decorator
  name, the route-constant pattern).
- Identify the navigation walker approach (how destinations are listed from a starting
  point).
- Note any refuse-loud conditions specific to this stack.

### For `code_inventory` section
- Identify the screen-declaration glob (e.g., `class .*Fragment` OR `@Composable fun <PascalCase>Screen`).
- Identify the state-container glob (e.g., `class .*ViewModel`).
- Identify the action pattern (e.g., `.clickable { ... }`, `@IBAction`).
- Identify the field-rendering pattern (e.g., `Text(`, `TextView`).
- Identify hybrid-host pattern if one exists.

### For `clarification` section
- Grep for feature-flag usage pattern name(s).
- Grep for permission-check patterns (`checkSelfPermission`, `AVCaptureDevice.authorizationStatus`).
- Grep for server-driven-content markers (network-layer references from UI code).
- Grep for responsive/config-branch patterns (`values-night/`, size-class checks, media queries).
- Grep for A/B-test hooks.
- Compile a list of topics to ask the human about (what the `03 Clarification` section
  will list).

## Confidence rules
- All three sections harvest ≥ 1 concrete pattern → `confidence: "high"`.
- Some sections empty → `confidence: "medium"` AND add items to `unresolved_questions`.
- No section harvests anything → stop, tell user to author the hint manually from
  `hint-template.md`.

## Output

Write `<run-dir>/hint-draft.json` conforming to the schema. Include a
`sections.flow_locator`, `sections.code_inventory`, `sections.clarification`
string body (prose written in hint-file style — imperative voice, concrete
patterns, links to actual tokens in the repo). If any section is below
confidence, populate `unresolved_questions`.
````

- [ ] **Step 3: Write stage 03**

Create `skills/design-tooling/design-coverage-scout/stages/03-hint-rendering.md`:

````markdown
# Scout Stage 03 — Hint rendering

## Inputs
- `hint-draft.json` from stage 2.
- `~/.claude/skills/design-coverage-scout/hint-template.md` as the shape reference.

## Objective
Render `<design-coverage-install>/platforms/<name>.md.draft`, preview it to the user
in the live session, and on explicit approval move `.draft` → `<name>.md`.

## Method

1. **Resolve target path.**
   ```python
   import os, pathlib
   scout_realpath = pathlib.Path(os.path.realpath(__file__)).parent.parent
   target_dir = scout_realpath.parent / "design-coverage" / "platforms"
   if not target_dir.exists():
       # Fallback — user installed via copy instead of symlink.
       target_dir = pathlib.Path.home() / ".claude" / "skills" / "design-coverage" / "platforms"
   target_dir.mkdir(parents=True, exist_ok=True)
   ```

2. **Refuse-overwrite.** If `<target_dir>/<name>.md` exists and `--force` was not
   passed, refuse and tell user to pass `--force` or choose a different `--platform-name`.

3. **Render to draft.** Read `hint-draft.json`. Emit `<name>.md.draft`:

   ```markdown
   ---
   name: <name>
   detect:
     - "<detect glob 1>"
     - "<detect glob 2>"
   description: <description>
   confidence: <confidence>
   ---

   ## 01 Flow locator
   <sections.flow_locator>

   ## 02 Code inventory
   <sections.code_inventory>

   ## 03 Clarification
   <sections.clarification>

   ## Unresolved questions
   <unresolved_questions bullets, if any>
   ```

   Drop the `## Unresolved questions` section if the array is empty.

4. **Live preview.** Print the drafted file to the user with a header:
   ```
   === DRAFT PLATFORM HINT ===
   <full file content>
   === END DRAFT ===
   Approve writing this to platforms/<name>.md? (yes / no / edit)
   ```

5. **Branch on response:**
   - `yes` → move `.draft` → `<name>.md`; run `python scripts/validate.py` to sanity-check;
     print success message including the final path; tell user to commit and push.
   - `no` → delete `.draft`; exit.
   - `edit` → ask user what to change, apply, re-preview.

6. **Post-rendering sanity check.** Run `python scripts/validate.py` on the parent repo
   (resolved from target_dir). If it fails, print the validator errors and refuse to
   finalize.
````

- [ ] **Step 4: Commit**

```bash
git add skills/design-tooling/design-coverage-scout/stages/
git commit -m "design-coverage-scout: write stages 01 (stack profile), 02 (pattern extraction), 03 (hint rendering)"
```

---

## Task 14: Write scout's SKILL.md and README

**Files:**
- Create: `skills/design-tooling/design-coverage-scout/SKILL.md`
- Create: `skills/design-tooling/design-coverage-scout/README.md`

- [ ] **Step 1: Write SKILL.md**

Create `skills/design-tooling/design-coverage-scout/SKILL.md`:

````markdown
---
name: design-coverage-scout
description: >
  Companion skill to design-coverage that inspects an unfamiliar repository
  and emits a new platforms/<name>.md hint file conforming to the shared
  template. Runs a three-stage pipeline: stack profile → pattern extraction
  → hint rendering with explicit draft/approve gating. Writes drafts only;
  never auto-commits. Use when the user says "/design-coverage-scout", runs
  design-coverage on an unknown stack and picks "generate a hint", or asks to
  "bootstrap a new platform for design-coverage".
argument-hint: "[--platform-name <name>] [--force]"
allowed-tools: Bash, Read, Edit, Write, Glob, Grep, Agent
---

# design-coverage-scout

Three-stage pipeline that characterizes an unfamiliar UI repo and emits a
platform hint file for design-coverage.

## Preflight

```bash
cd ~/.claude/skills/design-coverage-scout/
```

## Argument parsing

- `--platform-name <name>` — override the name used in the hint frontmatter and
  filename. If omitted, derived from the detected stack (e.g., `ios`, `android`,
  `react-native`).
- `--force` — overwrite an existing `platforms/<name>.md` without draft gating.
  **Use with care** — bypass is not recommended; prefer reviewing the draft.

## Run directory

```bash
RUN_DIR="$HOME/.claude/design-coverage-scout-runs/$(date +%Y-%m-%d)-<name>"
mkdir -p "$RUN_DIR"
```

## Stage pipeline

1. **Stage 01 — Stack profile.** Dispatch subagent with
   `stages/01-stack-profile.md`. Output: `<run-dir>/stack-profile.json`.
   On refuse-loud (multi-UI monorepo, no UI detected), exit with the
   refusal message.

2. **Stage 02 — Pattern extraction.** Dispatch subagent with
   `stages/02-pattern-extraction.md`. Output: `<run-dir>/hint-draft.json`.
   If `confidence == "low"` and no patterns harvested, exit and tell user
   to author manually from `hint-template.md`.

3. **Stage 03 — Hint rendering.** Dispatch subagent with
   `stages/03-hint-rendering.md`. This stage is **interactive** — it
   prompts the user to approve the draft live in the session.

## Final output

On successful rendering, print:

```
Hint written to <absolute-path>.

To share with other users:
  1. cd into the skills-repo clone that contains this file.
  2. git add <relative-path>
  3. git commit -m "design-coverage: add platforms/<name>.md (scout-generated)"
  4. git push and open a PR.
```

If the fallback path (`~/.claude/skills/design-coverage/platforms/`) was used,
additionally print:
```
NOTE: You installed via copy, not symlink. The hint file is in your local
install directory only. Copy it to your C:/src/skills/ clone to share.
```
````

- [ ] **Step 2: Write README.md**

Create `skills/design-tooling/design-coverage-scout/README.md`:

```markdown
# design-coverage-scout

Companion skill to `design-coverage` that inspects an unfamiliar UI repository
and emits a new `platforms/<name>.md` hint file.

## When to use

- `design-coverage` detected an unknown stack and the user picked "generate
  a hint" from the live prompt.
- A user wants to pre-build a hint for a new stack before running coverage.

## Invocation

```bash
/design-coverage-scout [--platform-name <name>] [--force]
```

## Output

- Draft at `<design-coverage-install>/platforms/<name>.md.draft`
- On approval, moved to `<design-coverage-install>/platforms/<name>.md`
- Never auto-commits. User commits and pushes to share.

## Methodology

Three-stage pipeline mirrors design-coverage's scaffolding:

1. **Stack profile** (`stages/01-stack-profile.md`)
2. **Pattern extraction** (`stages/02-pattern-extraction.md`)
3. **Hint rendering** (`stages/03-hint-rendering.md`) — interactive draft/approve

See [`hint-template.md`](./hint-template.md) for the required shape of any
hint file (scout output conforms to it automatically).

## Design & plan

- [Design](../../../docs/superpowers/specs/2026-04-22-design-coverage-platform-agnostic-design.md)
- [Implementation plan](../../../docs/superpowers/plans/2026-04-22-design-coverage-platform-agnostic.md)
```

- [ ] **Step 3: Run the validator**

Run: `python scripts/validate.py`
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add skills/design-tooling/design-coverage-scout/SKILL.md \
        skills/design-tooling/design-coverage-scout/README.md
git commit -m "design-coverage-scout: orchestrator SKILL.md + README"
```

---

## Task 15: Scout tests

**Files:**
- Create: `skill-tests/design-coverage-scout/conftest.py`
- Create: `skill-tests/design-coverage-scout/tests/test_hint_template_shape.py`
- Create: `skill-tests/design-coverage-scout/tests/test_refuse_overwrite.py`
- Create: `skill-tests/design-coverage-scout/tests/test_hint_draft_schema.py`
- Create: `skill-tests/design-coverage-scout/tests/test_render_draft.py`

- [ ] **Step 1: Write conftest**

```bash
mkdir -p skill-tests/design-coverage-scout/tests
```

Create `skill-tests/design-coverage-scout/conftest.py`:

```python
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DC_LIB = REPO / "skills" / "design-tooling" / "design-coverage" / "lib"
sys.path.insert(0, str(DC_LIB.parent))  # so `import lib.validator` works
```

- [ ] **Step 2: Write `test_hint_draft_schema.py`**

```python
"""Verify hint_draft.json schema parses and accepts valid/rejects invalid drafts."""
from __future__ import annotations
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
SCHEMA = REPO / "skills" / "design-tooling" / "design-coverage-scout" / "schemas" / "hint_draft.json"
sys.path.insert(0, str(REPO / "skills" / "design-tooling" / "design-coverage"))
from lib.validator import validate


def test_schema_parses() -> None:
    schema = json.loads(SCHEMA.read_text())
    assert schema["type"] == "object"


def test_valid_draft_passes() -> None:
    schema = json.loads(SCHEMA.read_text())
    draft = {
        "name": "react-native",
        "detect": ["metro.config.js"],
        "description": "React Native hint.",
        "confidence": "medium",
        "sections": {
            "flow_locator": "Look for App.tsx or navigation config.",
            "code_inventory": "Grep for `export const` components.",
            "clarification": "Ask about runtime permissions via react-native-permissions."
        }
    }
    errors = validate(draft, schema)
    assert errors == [], errors


def test_missing_section_fails() -> None:
    schema = json.loads(SCHEMA.read_text())
    draft = {
        "name": "react-native",
        "detect": ["metro.config.js"],
        "description": "RN.",
        "confidence": "medium",
        "sections": {"flow_locator": "x"}
    }
    errors = validate(draft, schema)
    assert errors, "expected validation errors"
```

- [ ] **Step 3: Write `test_hint_template_shape.py`**

```python
"""Verify hint-template.md describes the exact shape that validator enforces."""
from __future__ import annotations
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[3]
TEMPLATE = REPO / "skills" / "design-tooling" / "design-coverage-scout" / "hint-template.md"


def test_template_mentions_all_required_sections() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "## 01 Flow locator" in text
    assert "## 02 Code inventory" in text
    assert "## 03 Clarification" in text


def test_template_mentions_all_required_frontmatter_keys() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    for key in ("name", "detect", "description", "confidence"):
        assert f"{key}:" in text, f"template missing {key}"


def test_template_mentions_confidence_values() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    for v in ("high", "medium", "low"):
        assert v in text
```

- [ ] **Step 4: Write `test_render_draft.py`**

```python
"""Verify that a drafted hint, when written to disk, satisfies the validator."""
from __future__ import annotations
import pathlib
import subprocess
import sys
import textwrap

REPO = pathlib.Path(__file__).resolve().parents[3]


def render_hint_from_draft(draft: dict) -> str:
    """Replica of the rendering logic from scout stage 3."""
    lines = [
        "---",
        f"name: {draft['name']}",
        "detect:",
    ]
    for g in draft["detect"]:
        lines.append(f'  - "{g}"')
    lines += [
        f"description: {draft['description']}",
        f"confidence: {draft['confidence']}",
        "---",
        "",
        "## 01 Flow locator",
        draft["sections"]["flow_locator"],
        "",
        "## 02 Code inventory",
        draft["sections"]["code_inventory"],
        "",
        "## 03 Clarification",
        draft["sections"]["clarification"],
    ]
    if draft.get("unresolved_questions"):
        lines += ["", "## Unresolved questions"]
        for q in draft["unresolved_questions"]:
            lines.append(f"- {q}")
    return "\n".join(lines) + "\n"


def test_rendered_hint_satisfies_validator(tmp_path: pathlib.Path) -> None:
    # Set up a stub repo containing the rendered hint under the expected path.
    skill = tmp_path / "skills" / "design-tooling" / "design-coverage"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(textwrap.dedent("""\
        ---
        name: design-coverage
        description: Stub.
        ---
        # design-coverage
    """))
    (skill / "platforms").mkdir()
    draft = {
        "name": "react-native",
        "detect": ["metro.config.js"],
        "description": "React Native.",
        "confidence": "medium",
        "sections": {
            "flow_locator": "Grep react-navigation config.",
            "code_inventory": "Grep functional components with JSX.",
            "clarification": "Ask about permissions.",
        },
        "unresolved_questions": ["How are deep links wired?"]
    }
    rendered = render_hint_from_draft(draft)
    (skill / "platforms" / "react-native.md").write_text(rendered)
    r = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "validate.py")],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
```

- [ ] **Step 5: Write `test_refuse_overwrite.py`**

```python
"""Tests the refuse-overwrite contract for scout stage 3 rendering."""
from __future__ import annotations
import pathlib


def would_overwrite(target: pathlib.Path, force: bool) -> bool:
    """Replica of the scout stage-3 overwrite check."""
    return target.exists() and not force


def test_refuses_when_target_exists_and_no_force(tmp_path: pathlib.Path) -> None:
    target = tmp_path / "ios.md"
    target.write_text("existing content")
    assert would_overwrite(target, force=False) is True


def test_allows_when_force(tmp_path: pathlib.Path) -> None:
    target = tmp_path / "ios.md"
    target.write_text("existing content")
    assert would_overwrite(target, force=True) is False


def test_allows_when_target_missing(tmp_path: pathlib.Path) -> None:
    target = tmp_path / "ios.md"
    assert would_overwrite(target, force=False) is False
```

- [ ] **Step 6: Run scout tests**

Run: `cd skill-tests/design-coverage-scout && python -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add skill-tests/design-coverage-scout/
git commit -m "design-coverage-scout: add tests (draft schema, template shape, rendering, refuse overwrite)"
```

---

## Task 16: Update root README.md

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Read current README**

```bash
cat README.md
```

- [ ] **Step 2: Add two new rows to the Skills table**

Edit `README.md` — in the Skills table, after the `pr-followup` row, add:

```markdown
| [`design-coverage`](./skills/design-tooling/design-coverage/SKILL.md) | Compare an existing in-code UI flow against a new Figma design and produce an auditable discrepancy report. |
| [`design-coverage-scout`](./skills/design-tooling/design-coverage-scout/SKILL.md) | Companion skill that inspects an unfamiliar repo and emits a new `platforms/<name>.md` hint file for `design-coverage`. |
```

- [ ] **Step 3: Add to Installation section**

In the Installation section, after the `pr-loop-lib` line, add:

```bash
ln -s "$PWD/skills/design-tooling/design-coverage"        "$HOME/.claude/skills/design-coverage"
ln -s "$PWD/skills/design-tooling/design-coverage-scout"  "$HOME/.claude/skills/design-coverage-scout"
```

And in the Windows cmd block:

```bash
cp -r skills/design-tooling/design-coverage        "$HOME/.claude/skills/design-coverage"
cp -r skills/design-tooling/design-coverage-scout  "$HOME/.claude/skills/design-coverage-scout"
```

- [ ] **Step 4: Add to Design docs section**

In the Design docs section, append:

```markdown
- [2026-04-22 design-coverage platform-agnostic design](./docs/superpowers/specs/2026-04-22-design-coverage-platform-agnostic-design.md)
- [2026-04-22 design-coverage platform-agnostic implementation plan](./docs/superpowers/plans/2026-04-22-design-coverage-platform-agnostic.md)
```

- [ ] **Step 5: Run validator**

Run: `python scripts/validate.py`
Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "readme: add design-coverage + design-coverage-scout skills"
```

---

## Task 17: Full validation sweep

**Files:** none modified; verification only.

- [ ] **Step 1: Run validator**

```bash
cd /c/src/skills-worktrees/design-coverage-platform-agnostic
python scripts/validate.py
```
Expected: `OK`.

- [ ] **Step 2: Run full design-coverage test suite**

```bash
cd skill-tests/design-coverage && python -m pytest tests/ -v
```
Expected: ~60 tests, all PASS.

- [ ] **Step 3: Run scout test suite**

```bash
cd /c/src/skills-worktrees/design-coverage-platform-agnostic/skill-tests/design-coverage-scout
python -m pytest tests/ -v
```
Expected: all PASS.

- [ ] **Step 4: Run scripts/test_validate_hints.py**

```bash
cd /c/src/skills-worktrees/design-coverage-platform-agnostic
python -m pytest scripts/test_validate_hints.py -v
```
Expected: 3 PASS.

- [ ] **Step 5: If anything fails, fix inline and re-run** until all green.

- [ ] **Step 6: No commit** — this task is verification only.

---

## Task 18: Install skills locally and smoke-test scout against `C:/src/MindBodyPOS`

**Files:** none modified; external verification.

**Rationale:** Quality gate for the scout skill. Run it against a real iOS repo and compare the generated hint against the planned `platforms/ios.md`.

- [ ] **Step 1: Install both skills via symlink**

```bash
# From C:/src/skills-worktrees/design-coverage-platform-agnostic (Git Bash):
cmd //c mklink /D "$USERPROFILE/.claude/skills/design-coverage" \
  "$(cygpath -w $PWD/skills/design-tooling/design-coverage)"
cmd //c mklink /D "$USERPROFILE/.claude/skills/design-coverage-scout" \
  "$(cygpath -w $PWD/skills/design-tooling/design-coverage-scout)"
```

- [ ] **Step 2: Restart Claude Code session**

Tell user: "Restart Claude Code so the new skills appear in `/<list>`."

- [ ] **Step 3: Run scout against MindBodyPOS**

In a fresh Claude Code session, from `C:/src/MindBodyPOS`:

```
/design-coverage-scout --platform-name ios-test
```

Expected behavior:
1. Stage 01 detects iOS stack (UIKit + SwiftUI, ObjC mixed, stack-based + SwiftUI nav).
2. Stage 02 harvests patterns from the real MindBodyPOS tree (RequestAgents, Scenes, ViewModels).
3. Stage 03 shows a draft preview. User inspects.

- [ ] **Step 4: Diff the generated hint against planned `platforms/ios.md`**

```bash
diff "$HOME/.claude/skills/design-coverage/platforms/ios-test.md.draft" \
     "/c/src/skills-worktrees/design-coverage-platform-agnostic/skills/design-tooling/design-coverage/platforms/ios.md"
```

**Quality gates:**
- Both hints detect iOS via at least one shared pattern (`**/*.xcodeproj` or `Package.swift`).
- Generated hint's `02 Code inventory` section mentions: UIViewController OR SwiftUI `View` OR a real class pattern present in MindBodyPOS.
- Generated hint's `03 Clarification` section lists at least: feature flags, permissions.
- `confidence` on the generated hint is at least `medium`.

If the generated hint meets all four gates → scout quality is acceptable. If not → file a follow-up issue with the specific gap (don't block the PR; scout is a new skill and can iterate).

- [ ] **Step 5: Cleanup**

```bash
rm "$HOME/.claude/skills/design-coverage/platforms/ios-test.md.draft"
# Optionally keep the diff in the run log for the PR description.
```

- [ ] **Step 6: Write a short note** in the PR description summarizing:
  - Quality gates passed / failed.
  - Any follow-up issues to file.

---

## Task 19: Open the PR via `/pr-autopilot`

**Files:** none modified; external workflow.

- [ ] **Step 1: Confirm all commits are on the branch**

```bash
cd /c/src/skills-worktrees/design-coverage-platform-agnostic
git log --oneline main..HEAD
```
Expected: ~18 commits for tasks T1–T18 plus the spec commit.

- [ ] **Step 2: Confirm tests pass cleanly**

```bash
python scripts/validate.py && \
  cd skill-tests/design-coverage && python -m pytest tests/ -q && \
  cd ../../skill-tests/design-coverage-scout && python -m pytest tests/ -q
```
Expected: all OK.

- [ ] **Step 3: Invoke pr-autopilot**

Tell the user:
> "Everything local is green. Invoking `/pr-autopilot` to push the branch, open the PR with a filled template, and drive it through the reviewer-bot loop until CI is green."

Then:

```
/pr-autopilot
```

Let pr-autopilot handle:
- Preflight self-review
- Spec/plan alignment
- Opening the PR
- Wait-cycle loop
- Final CI gate

- [ ] **Step 4: When pr-autopilot reports CI green, surface the PR URL to the user.**

---

## Self-Review

**1. Spec coverage check.** Every spec section maps to at least one task:

| Spec section                                | Task(s)          |
|---------------------------------------------|------------------|
| Architecture — pipeline + hint injection    | T4, T5, T6       |
| Repository layout                           | T2, T3, T11      |
| D1 Hybrid architecture                      | T5, T6           |
| D2 Day-one hints: iOS + Android             | T9, T10          |
| D3 Unknown stack live prompt + flag         | T6               |
| D4 Output dir default/override              | T6               |
| D5 Close both PRs                           | T18 note only; external |
| D6 One hint file per platform               | T9, T10          |
| D7 Scout peer skill                         | T11–T15          |
| D8 Scout methodology inline                 | T13              |
| D9 Scout drafts with approval               | T13, T15         |
| D10 Tests at skill-tests/                   | T7, T8, T15      |
| Hint contract (frontmatter + sections)      | T1, T11          |
| `run.json` additions                        | T3, T7           |
| Refuse triggers — multi-hint, bad frontmatter, scout overwrite | T8, T15 |
| Testing strategy                            | T7, T8, T15, T17 |
| Installation                                | T16, T18         |
| Rollout sequence                            | Task order itself |
| Scout symlink-aware write                   | T13              |

**2. Placeholder scan.** No `[TBD]`, `TODO:`, or `[fill in`. Code blocks in every step that writes code. Commands with expected output in every verify step.

**3. Type consistency.** `run.json` new fields used consistently: `platform`, `hint_source`, `skill_version`. `hint_draft.json` keys used consistently in schema, tests, and rendering logic. `<!-- PLATFORM_HINTS -->` marker literal used consistently across stages, SKILL.md, and tests. Section headers (`## 01 Flow locator`, `## 02 Code inventory`, `## 03 Clarification`) used consistently.

---

## Execution choice

Plan complete. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task with review between tasks. Good for 18 tasks with varied complexity.
2. **Inline Execution** — execute in this session with batch checkpoints.
