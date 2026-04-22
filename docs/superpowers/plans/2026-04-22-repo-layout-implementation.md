# Repo layout: type-first reorganization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `pr-autopilot/`, `pr-followup/`, and `pr-loop-lib/` under `skills/pr-tooling/`, and update the validator and README to match the type-first top-level layout described in `docs/superpowers/specs/2026-04-22-repo-layout-design.md`.

**Architecture:** Two commits.
1. Atomic `git mv` of the three skill folders into `skills/pr-tooling/` together with the `scripts/validate.py` rewrite to dynamic skill discovery under `skills/**`. The move and the validator update must land together or the validator breaks on backticked repo-relative references like `` `pr-loop-lib/references/*.md` `` found in docs files.
2. `README.md` update (install commands + skills table paths).

**Tech Stack:** Python 3 (validator), Git (for history-preserving moves), Bash (for validation commands).

**Note on TDD:** `scripts/validate.py` has no unit-test harness in this repo. The spec's acceptance criterion is that `python scripts/validate.py` prints `OK` with all current content. Each task uses that run as the red/green signal: observe expected failure, make the change, observe pass.

---

## File Structure

Files touched by this plan:

- Create (directory): `skills/` — new top-level type bucket.
- Create (directory): `skills/pr-tooling/` — umbrella folder grouping the three PR tooling artifacts.
- Move: `pr-autopilot/` → `skills/pr-tooling/pr-autopilot/` (directory, tracked by git, history preserved)
- Move: `pr-followup/`  → `skills/pr-tooling/pr-followup/`
- Move: `pr-loop-lib/`  → `skills/pr-tooling/pr-loop-lib/`
- Modify: `scripts/validate.py` — switch hardcoded `SKILL_ROOTS` list to dynamic discovery under `skills/**`.
- Modify: `README.md` — update install commands (Unix + Windows) and the skills/lib table paths to reflect the new locations.

No skill-internal files (`SKILL.md`, files under `steps/`, `references/`, `platform/`) are edited. They use skill-root-relative or home-ref paths, both of which survive the move.

---

### Task 1: Move the three skill folders under `skills/pr-tooling/` and rewrite the validator to dynamic skill discovery

**Why atomic:** `docs/superpowers/plans/2026-04-18-pr-autopilot-improvements-implementation.md` (and others under `docs/`) contain many backticked repo-relative references such as `` `pr-loop-lib/references/context-schema.md` ``. The validator scans `docs/**` for these and currently resolves them against `REPO / <skill-root-name>`. After the move those resolve against `REPO / "pr-loop-lib" / ...`, which no longer exists. If the move is committed without the validator update, `python scripts/validate.py` fails loudly on dozens of doc-side references.

**Files:**
- Create: `skills/pr-tooling/` (directory; git will create it on the first `git mv`)
- Move: `pr-autopilot/` → `skills/pr-tooling/pr-autopilot/`
- Move: `pr-followup/`  → `skills/pr-tooling/pr-followup/`
- Move: `pr-loop-lib/`  → `skills/pr-tooling/pr-loop-lib/`
- Modify: `scripts/validate.py` (entire file — small rewrite, shown below)

- [ ] **Step 1: Confirm a clean baseline — validator passes before any change**

Run: `python scripts/validate.py`
Expected: prints `OK`, exits 0.

If this does not pass, stop and investigate before making any changes — the rest of this plan assumes a clean baseline.

- [ ] **Step 2: Create the `skills/pr-tooling/` parent directory**

```bash
mkdir -p skills/pr-tooling
```

No commit yet. The directory will be populated by the next step.

- [ ] **Step 3: Move the three skill folders with `git mv` (preserves history)**

Run each move individually so git records the rename correctly:

```bash
git mv pr-autopilot  skills/pr-tooling/pr-autopilot
git mv pr-followup   skills/pr-tooling/pr-followup
git mv pr-loop-lib   skills/pr-tooling/pr-loop-lib
```

Verify the structure:

```bash
ls skills/pr-tooling
# expected output (3 entries, no trailing slashes in bare ls):
# pr-autopilot  pr-followup  pr-loop-lib
```

Also confirm the old paths are gone:

```bash
ls -d pr-autopilot pr-followup pr-loop-lib 2>&1 | head -5
# expected: three "No such file or directory" lines
```

- [ ] **Step 4: Run the validator to observe the EXPECTED failure**

Run: `python scripts/validate.py`
Expected: **non-zero exit** with many `missing reference:` errors pointing at `docs/superpowers/plans/2026-04-18-pr-autopilot-improvements-implementation.md` and friends. The errors reference paths like `pr-loop-lib/references/state-protocol.md` — correct, because the validator is still trying to resolve them at the old repo-root location. This confirms the need for the validator rewrite in the next step.

If instead the validator prints `OK`, something is wrong (files not actually moved, or validator was already rewritten). Stop and investigate.

- [ ] **Step 5: Rewrite `scripts/validate.py` for dynamic skill discovery under `skills/**`**

Replace the entire contents of `scripts/validate.py` with:

```python
#!/usr/bin/env python3
"""Structural validation for the installable skill files in this repo.

Checks:
  1. Every .md file under every discovered skill root parses as valid UTF-8.
     Placeholder-marker scan flags unfinished section markers appearing at
     the **start of a line** (outside fenced code blocks): `[TBD]`, `TODO: `,
     `[fill in ...`, `XXX `. Inline prose mentioning those strings
     (e.g., describing what the validator rejects) is not flagged — the
     check targets markers left behind in an actual draft.
  2. Every SKILL.md starts with YAML frontmatter containing at least `name`
     and `description` fields. Frontmatter detection tolerates both LF and
     CRLF line endings (Windows checkouts).
  3. Relative file references inside each .md that look like skill-internal
     includes — `steps/NN-*.md`, `references/*.md`, `platform/*.md`, or the
     repo-relative form `<skill-root-name>/...` — actually resolve to a real
     file on disk, and the resolved path is contained within the repo root
     (`..` traversal that escapes the repo is a bug). Absolute
     `~/.claude/skills/...` references are validated the same way.

Skill roots are discovered dynamically: any directory under `skills/**` that
contains at least one `.md` file *directly* (not only in subdirectories) is
a skill root. Umbrella directories that only contain subdirectories (like
`skills/pr-tooling/`) are transparent — the walk descends through them.
This covers both real skills (which have `SKILL.md` plus step/reference
files) and skill-support libs like `pr-loop-lib` (which have step/reference
files but no `SKILL.md`). Adding a new skill requires zero validator edits.

Exit non-zero on any failure with a per-file diagnostic.
"""
from __future__ import annotations
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO / "skills"
# Spec/plan documents are also scanned for placeholder and reference rot.
# They do not have SKILL.md frontmatter requirements but share the same
# placeholder and relative-reference checks.
DOC_ROOTS = ["docs"]
# Placeholder patterns should only fire on *unfinished section markers*,
# not on the strings when they appear as literal content being discussed
# (e.g., "PR Author TODO:" is a repo convention we reject, not a placeholder
# in the skill file itself).
PLACEHOLDER_PATTERNS = [
    re.compile(r"(?m)^\s*\[TBD\]"),
    re.compile(r"(?m)^\s*TODO:\s"),        # Only "TODO: " at start of line
    re.compile(r"(?m)^\s*\[fill in\b", re.IGNORECASE),
    re.compile(r"(?m)^\s*XXX\s"),
]
# Exclude matches inside fenced code blocks (``` ... ```).
FENCED_BLOCK = re.compile(r"```.*?```", re.DOTALL)
HOME_REF = re.compile(
    r"`(~/\.claude/skills/[A-Za-z0-9._/-]+\.md)`"
)
FRONTMATTER = re.compile(
    # Tolerates:
    #   - LF or CRLF line endings throughout (\r?\n)
    #   - no content after the closing --- (file ends immediately, or
    #     ends with the delimiter followed only by whitespace / EOF)
    r"\A---\s*\r?\n(.*?\r?\n)---\s*(?:\r?\n|\Z)", re.DOTALL
)


def discover_skill_roots() -> dict[str, pathlib.Path]:
    """Walk `skills/**` and return a mapping of skill-root-name -> absolute path.

    A skill root is the topmost directory under `skills/` that directly
    contains at least one `.md` file. Umbrella dirs (only subdirs, no
    `.md` files directly) are transparent — the walk descends through
    them. Once a directory qualifies as a skill root, the walk does NOT
    descend into it — subdirectories like `steps/`, `references/`, and
    `platform/` belong to the skill, they are not peer skills.
    """
    roots: dict[str, pathlib.Path] = {}
    if not SKILLS_DIR.exists():
        return roots

    def walk(path: pathlib.Path) -> None:
        if any(c.suffix == ".md" and c.is_file() for c in path.iterdir()):
            # Ambiguity guard: two skills with the same basename would
            # shadow each other in repo-relative reference resolution.
            # That is a layout bug, not a validator bug — refuse to
            # silently pick one.
            if path.name in roots and roots[path.name] != path:
                raise SystemExit(
                    f"duplicate skill-root name {path.name!r}: "
                    f"{roots[path.name]} and {path}"
                )
            roots[path.name] = path
            return
        for child in path.iterdir():
            if child.is_dir():
                walk(child)

    for child in SKILLS_DIR.iterdir():
        if child.is_dir():
            walk(child)
    return roots


def _mask_code_blocks(text: str) -> str:
    """Replace fenced code-block content with equivalent-length whitespace
    so offsets (line numbers) are preserved but code contents are not scanned."""
    def repl(m: re.Match) -> str:
        s = m.group(0)
        return re.sub(r"[^\n]", " ", s)
    return FENCED_BLOCK.sub(repl, text)


def build_rel_ref_pattern(skill_root_names: list[str]) -> re.Pattern[str]:
    """Build the REL_REF regex from the discovered skill-root names."""
    # Alternation must be regex-safe; sort longest-first so "pr-loop-lib"
    # wins over a hypothetical prefix match. Escape for literal matching.
    alternation = "|".join(
        re.escape(n) for n in sorted(skill_root_names, key=len, reverse=True)
    )
    if not alternation:
        # No skills discovered — match nothing rather than `(?:)/...` which
        # would accidentally match any path.
        alternation = "(?!x)x"  # never matches
    return re.compile(
        r"`("
        r"(?:steps|references|platform)/[A-Za-z0-9._/-]+\.md"   # skill-root-relative
        r"|"
        rf"(?:{alternation})/[A-Za-z0-9._/-]+\.md"              # repo-relative
        r")`"
    )


def check_file(
    path: pathlib.Path,
    skill_roots: dict[str, pathlib.Path],
    rel_ref: re.Pattern[str],
) -> list[str]:
    errors: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as e:
        errors.append(f"{path}: cannot read as UTF-8 ({type(e).__name__}: {e})")
        return errors
    scan_text = _mask_code_blocks(text)
    for pat in PLACEHOLDER_PATTERNS:
        for m in pat.finditer(scan_text):
            line = text[: m.start()].count("\n") + 1
            errors.append(f"{path}:{line} placeholder: {m.group(0)!r}")
    if path.name == "SKILL.md":
        m = FRONTMATTER.match(text)
        if not m:
            errors.append(f"{path}: missing YAML frontmatter")
        else:
            fm = m.group(1)
            if "name:" not in fm:
                errors.append(f"{path}: frontmatter missing `name`")
            if "description:" not in fm:
                errors.append(f"{path}: frontmatter missing `description`")
    # Walk up from the current file to find the nearest skill-root
    # directory (by name). References like `steps/...`, `references/...`,
    # `platform/...` resolve against this root, not against the current
    # file's directory.
    skill_root = None
    for ancestor in path.parents:
        if ancestor.name in skill_roots and skill_roots[ancestor.name] == ancestor:
            skill_root = ancestor
            break
    repo_resolved = REPO.resolve()
    def _is_within_repo(p: pathlib.Path) -> bool:
        try:
            p.relative_to(repo_resolved)
            return True
        except ValueError:
            return False
    for m in rel_ref.finditer(text):
        rel = m.group(1)
        # If the reference already starts with a skill-root name, resolve it
        # against that skill's actual location under `skills/**`. Otherwise
        # try relative to the current skill root, the current file's dir,
        # and each other skill root.
        candidates = []
        first_segment, _, remainder = rel.partition("/")
        if first_segment in skill_roots:
            candidates.append((skill_roots[first_segment] / remainder).resolve())
        else:
            if skill_root is not None:
                candidates.append((skill_root / rel).resolve())
            candidates.append((path.parent / rel).resolve())
            for other_root_path in skill_roots.values():
                candidates.append((other_root_path / rel).resolve())
        # Only accept a candidate that both exists AND lives inside the repo.
        # References with enough `..` segments to escape the repo root are
        # always rejected as an out-of-tree reference.
        valid = [c for c in candidates if c.exists() and _is_within_repo(c)]
        if not valid:
            line = text[: m.start()].count("\n") + 1
            if any(c.exists() and not _is_within_repo(c) for c in candidates):
                errors.append(
                    f"{path}:{line} reference escapes repo root (..): {rel}"
                )
            else:
                errors.append(f"{path}:{line} missing reference: {rel}")
    for m in HOME_REF.finditer(text):
        ref = m.group(1).replace("~/.claude/skills/", "")
        first_segment, _, remainder = ref.partition("/")
        if first_segment in skill_roots:
            target = (skill_roots[first_segment] / remainder).resolve()
        else:
            # Not a name we know about — report as missing rather than
            # silently accepting.
            target = (REPO / ref).resolve()
        if not target.exists() or not _is_within_repo(target):
            line = text[: m.start()].count("\n") + 1
            errors.append(f"{path}:{line} missing home-ref: {m.group(1)}")
    return errors


def main() -> int:
    skill_roots = discover_skill_roots()
    rel_ref = build_rel_ref_pattern(list(skill_roots.keys()))
    all_errors: list[str] = []
    for root_path in skill_roots.values():
        for path in sorted(root_path.rglob("*.md")):
            all_errors.extend(check_file(path, skill_roots, rel_ref))
    for root_name in DOC_ROOTS:
        root = REPO / root_name
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.md")):
            all_errors.extend(check_file(path, skill_roots, rel_ref))
    if all_errors:
        for e in all_errors:
            print(e, file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Key differences from the pre-move version:

- `SKILL_ROOTS = [...]` hardcoded list is gone. `discover_skill_roots()` walks `skills/**` and builds a `{name: absolute_path}` mapping for every directory that directly contains `.md` files.
- Ambiguity guard: two skill roots with the same basename anywhere under `skills/**` raise `SystemExit` at discovery time — that's a layout bug, not a validator bug.
- `REL_REF` is built dynamically from the discovered names via `build_rel_ref_pattern()`. An empty skill set degrades to a pattern that never matches (safer than a blank alternation).
- Repo-relative reference resolution uses the discovered absolute path (`skill_roots[first_segment]`) rather than `REPO / first_segment`. This is the single functional change that makes references survive the umbrella folder.
- `HOME_REF` resolution now also routes through `skill_roots`, so `~/.claude/skills/pr-loop-lib/steps/01-wait-cycle.md` resolves to `skills/pr-tooling/pr-loop-lib/steps/01-wait-cycle.md` on disk.
- The skill-root ancestor walk compares `ancestor.name in skill_roots and skill_roots[ancestor.name] == ancestor` so a directory merely named `pr-loop-lib` elsewhere in the tree does not accidentally match.

- [ ] **Step 6: Run the validator to observe it now PASSES after the rewrite**

Run: `python scripts/validate.py`
Expected: prints `OK`, exits 0.

If any `missing reference:` or `missing home-ref:` errors appear, the discovery or resolution logic is wrong — do not proceed. Re-read the `discover_skill_roots()` and reference-resolution diffs and fix before committing.

- [ ] **Step 7: Spot-check that git recorded the moves as renames, not as delete+add**

Run:

```bash
git status --short
```

Expected: entries starting with `R` (renamed) for the three skill folders and `M` for `scripts/validate.py`. Example (exact names vary):

```
R  pr-autopilot/SKILL.md -> skills/pr-tooling/pr-autopilot/SKILL.md
R  pr-autopilot/steps/01-detect-context.md -> skills/pr-tooling/pr-autopilot/steps/01-detect-context.md
...
M  scripts/validate.py
```

If any file shows as `D` + `A` instead of `R`, run `git diff -M50 --stat --cached HEAD` — git's rename detection sometimes needs a lower similarity threshold to catch heavily-edited moves, but in this case each moved file is byte-identical, so `R` is expected.

- [ ] **Step 8: Commit the move + validator rewrite as a single commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
refactor: move PR tooling skills under skills/pr-tooling/, switch validator to dynamic discovery

Per docs/superpowers/specs/2026-04-22-repo-layout-design.md:

- git mv pr-autopilot -> skills/pr-tooling/pr-autopilot
- git mv pr-followup  -> skills/pr-tooling/pr-followup
- git mv pr-loop-lib  -> skills/pr-tooling/pr-loop-lib
- scripts/validate.py: replace hardcoded SKILL_ROOTS with a walker
  over skills/** that treats any dir directly containing .md files as
  a skill root. Repo-relative references (e.g. pr-loop-lib/steps/01-wait-cycle.md)
  resolve against the discovered absolute path so the umbrella folder
  is transparent.

Skill internals and the installed layout under ~/.claude/skills/ are
unchanged. References inside skill files use skill-root-relative or
home-ref paths, both of which survive the move.
EOF
)"
```

Verify the commit landed:

```bash
git log --oneline -1
```

Expected: the new commit message SHA at the top, and `git status` now clean.

---

### Task 2: Update `README.md` install commands and skills table

**Files:**
- Modify: `README.md` (whole-file rewrite of the Skills table, Supporting library link, and both Installation blocks)

- [ ] **Step 1: Edit `README.md` to reflect the new repo paths**

Replace the entire contents of `README.md` with:

```markdown
# skills

User-level Claude Code skills maintained by @prpande.

## Skills

| Skill | Purpose |
|---|---|
| [`pr-autopilot`](./skills/pr-tooling/pr-autopilot/SKILL.md) | Autonomously publish a PR and drive it through the reviewer-bot feedback loop until CI is green. |
| [`pr-followup`](./skills/pr-tooling/pr-followup/SKILL.md) | Re-enter the same comment loop later when human or late bot comments arrive. |

## Supporting library

[`pr-loop-lib/`](./skills/pr-tooling/pr-loop-lib/README.md) — shared per-step markdown
library imported by both skills. Not a skill itself (no `SKILL.md`).

## Prompts

Standalone prompts you can paste into a Claude conversation — no install step.

| Prompt | Purpose |
|---|---|
| [`attention-status-page`](./prompts/attention-status-page.md) | Build a live "What needs your attention" HTML artifact that pulls from your connected tools (Slack, Notion, Asana, Linear, Jira, email) and groups items by work item. |

## Design docs

- [2026-04-17 pr-autopilot skill design](./docs/superpowers/specs/2026-04-17-pr-autopilot-skill-design.md)
- [2026-04-17 pr-autopilot skill implementation plan](./docs/superpowers/plans/2026-04-17-pr-autopilot-skill-implementation.md)

## Installation

Symlink (or copy) each skill folder into `~/.claude/skills/`:

```bash
ln -s "$PWD/skills/pr-tooling/pr-autopilot"  "$HOME/.claude/skills/pr-autopilot"
ln -s "$PWD/skills/pr-tooling/pr-followup"   "$HOME/.claude/skills/pr-followup"
ln -s "$PWD/skills/pr-tooling/pr-loop-lib"   "$HOME/.claude/skills/pr-loop-lib"
```

On Windows with Git Bash, use `cmd //c mklink /D` or copy:

```bash
cp -r skills/pr-tooling/pr-autopilot   "$HOME/.claude/skills/pr-autopilot"
cp -r skills/pr-tooling/pr-followup    "$HOME/.claude/skills/pr-followup"
cp -r skills/pr-tooling/pr-loop-lib    "$HOME/.claude/skills/pr-loop-lib"
```

After installation, restart your Claude Code session. The skills appear in
`/<list>` under `pr-autopilot` and `pr-followup`.

## Validation

Run the structural validator before committing changes:

```bash
python scripts/validate.py
```

Exits 0 with `OK` on success; non-zero with per-file diagnostics on
failure.

## Smoke test

1. In any GitHub repo, make a trivial change on a feature branch.
2. Run `/pr-autopilot 2` (cap at 2 iterations for a quick test).
3. Verify: PR opens, template filled, first wait cycle begins.
4. Wait for at least one reviewer-bot cycle (10 min), observe that comments
   are addressed in the next iteration.
5. Observe the final report.
```

Only the paths under `Skills`, `Supporting library`, and both `Installation` code blocks change. The rest of the README is preserved verbatim.

- [ ] **Step 2: Verify the validator still passes after the README edit**

Run: `python scripts/validate.py`
Expected: `OK`. (The README is not scanned by the validator directly — it lives at the repo root, outside `skills/**` and `docs/`. But running the validator here is cheap insurance that the commit is well-formed.)

- [ ] **Step 3: Verify each README install path exists on disk**

Run:

```bash
ls -d skills/pr-tooling/pr-autopilot skills/pr-tooling/pr-followup skills/pr-tooling/pr-loop-lib
```

Expected: all three print as directories, no errors. If any path is missing, the README is lying about install targets.

- [ ] **Step 4: Commit the README update**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs(readme): point install commands and tables at skills/pr-tooling/

Per docs/superpowers/specs/2026-04-22-repo-layout-design.md D5:
each install line shows the full repo-side path explicitly. Three
skills do not justify a helper script; revisit if the count crosses
6-8.
EOF
)"
```

Verify:

```bash
git log --oneline -2
```

Expected: the README commit on top, the move+validator commit below it.

---

### Task 3: End-to-end validation after both commits land

**Files:** none (validation only, no edits).

- [ ] **Step 1: Run the structural validator from a clean tree**

Run:

```bash
git status --short
python scripts/validate.py
```

Expected: first line prints nothing (clean tree); second prints `OK` and exits 0.

- [ ] **Step 2: Grep for any lingering repo-root-relative skill references that should have been updated**

The install targets in `~/.claude/skills/` are flat — skill-to-skill references use `~/.claude/skills/<name>/...`, which the validator handles via `HOME_REF`. The only spots where the literal prefix `pr-tooling/` should appear in markdown are the README's install/table entries. Confirm:

```bash
grep -rn "pr-tooling" README.md scripts/ skills/ docs/
```

Expected: matches only in `README.md` (install commands + skills table + supporting-library link). No matches inside `skills/**` (skill internals never speak the umbrella name) and no matches inside `scripts/validate.py` (the validator uses the generic `SKILLS_DIR` walker, not a hardcoded `pr-tooling` string).

- [ ] **Step 3: Sanity-check install instructions manually (dry run)**

Confirm the three install-source paths resolve to real directories and that each contains the entrypoint expected by `~/.claude/skills/`:

```bash
ls skills/pr-tooling/pr-autopilot/SKILL.md
ls skills/pr-tooling/pr-followup/SKILL.md
ls skills/pr-tooling/pr-loop-lib/README.md
```

Expected: all three paths print with no errors. `pr-loop-lib` has `README.md` but no `SKILL.md` by design (it is a skill-support lib, not a skill).

- [ ] **Step 4: Skill-internal reference grep — confirm no unresolved forms remain**

Spot-check that step files still reference `pr-loop-lib/...` (repo-relative) and `~/.claude/skills/pr-loop-lib/...` (home-ref) forms as before, and both still validate:

```bash
grep -rn "pr-loop-lib/" skills/pr-tooling/pr-autopilot/ | head -5
grep -rn "~/.claude/skills/pr-loop-lib/" skills/pr-tooling/pr-autopilot/ | head -5
```

Expected: both return hits (the skills have not been rewired). If the previous step (validator) passed, those references already resolve correctly against the new umbrella layout — this grep is just a visibility check for the human reviewing the change.

- [ ] **Step 5: No commit needed for Task 3**

Task 3 is observational. If all four checks pass, the implementation is complete and ready for PR.

---

## Self-review checklist (completed before publishing this plan)

- **Spec coverage:**
  - Target layout (§Target layout): covered by Task 1 Steps 2–3.
  - D1 (types now = skills + prompts): no code change; already the state.
  - D2 (`pr-tooling/` umbrella): Task 1 Step 3.
  - D3 (`docs/superpowers/` stays central): no change; already correct.
  - D4 (dynamic `skills/**` discovery): Task 1 Step 5 (validator rewrite).
  - D5 (verbose README install paths): Task 2 Step 1.
  - Migration mechanics (`git mv`, preserves history): Task 1 Step 3.
  - Files not to edit (skill internals): the plan does not touch them.
  - Validation after move (validator `OK`, install paths exist, references resolve): Task 3.
- **Placeholder scan:** no `TBD`, `TODO:` (at line start), `[fill in`, or `XXX` markers in this plan.
- **Type consistency:** `SKILLS_DIR`, `skill_roots`, `discover_skill_roots()`, `build_rel_ref_pattern()`, `check_file(path, skill_roots, rel_ref)` signatures match between the validator rewrite and the places they are called from `main()`. `HOME_REF` / `REL_REF` / `FRONTMATTER` pattern names preserved.
