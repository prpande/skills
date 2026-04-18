#!/usr/bin/env python3
"""Structural validation for the pr-autopilot / pr-followup skill files.

Checks:
  1. Every .md file under pr-autopilot/, pr-followup/, pr-loop-lib/ parses as
     valid UTF-8 and has no placeholder strings (TBD, TODO:, 'fill in', 'XXX').
  2. Every SKILL.md starts with YAML frontmatter containing at least `name` and
     `description` fields.
  3. Relative file references inside each .md (of the form
     `steps/NN-*.md`, `references/*.md`, `platform/*.md`, or absolute
     `~/.claude/skills/...`) actually exist on disk.

Exit non-zero on any failure with a per-file diagnostic.
"""
from __future__ import annotations
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
SKILL_ROOTS = ["pr-autopilot", "pr-followup", "pr-loop-lib"]
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
REL_REF = re.compile(
    r"`((?:steps|references|platform)/[A-Za-z0-9._/-]+\.md)`"
)
HOME_REF = re.compile(
    r"`(~/\.claude/skills/[A-Za-z0-9._/-]+\.md)`"
)
FRONTMATTER = re.compile(
    r"\A---\s*\n(.*?\n)---\s*\n", re.DOTALL
)

def _mask_code_blocks(text: str) -> str:
    """Replace fenced code-block content with equivalent-length whitespace
    so offsets (line numbers) are preserved but code contents are not scanned."""
    def repl(m: re.Match) -> str:
        s = m.group(0)
        return re.sub(r"[^\n]", " ", s)
    return FENCED_BLOCK.sub(repl, text)

def check_file(path: pathlib.Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
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
    # (pr-autopilot / pr-followup / pr-loop-lib). References like
    # `steps/...`, `references/...`, `platform/...` resolve against this
    # root, not against the current file's directory.
    skill_root = None
    for ancestor in path.parents:
        if ancestor.name in SKILL_ROOTS:
            skill_root = ancestor
            break
    for m in REL_REF.finditer(text):
        rel = m.group(1)
        # Try relative to: current skill root, current file dir, and each
        # other skill root. References often point across skills (e.g.,
        # pr-autopilot referencing pr-loop-lib/references/*.md).
        candidates = []
        if skill_root is not None:
            candidates.append((skill_root / rel).resolve())
        candidates.append((path.parent / rel).resolve())
        for other_root_name in SKILL_ROOTS:
            candidates.append((REPO / other_root_name / rel).resolve())
        if not any(c.exists() for c in candidates):
            line = text[: m.start()].count("\n") + 1
            errors.append(f"{path}:{line} missing reference: {rel}")
    for m in HOME_REF.finditer(text):
        ref = m.group(1).replace("~/.claude/skills/", "")
        target = (REPO / ref).resolve()
        if not target.exists():
            line = text[: m.start()].count("\n") + 1
            errors.append(f"{path}:{line} missing home-ref: {m.group(1)}")
    return errors

def main() -> int:
    all_errors: list[str] = []
    for root_name in SKILL_ROOTS:
        root = REPO / root_name
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.md")):
            all_errors.extend(check_file(path))
    if all_errors:
        for e in all_errors:
            print(e, file=sys.stderr)
        return 1
    print("OK")
    return 0

if __name__ == "__main__":
    sys.exit(main())
