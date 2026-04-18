#!/usr/bin/env python3
"""Structural validation for the pr-autopilot / pr-followup skill files.

Checks:
  1. Every .md file under pr-autopilot/, pr-followup/, pr-loop-lib/ parses as
     valid UTF-8. Placeholder-marker scan flags unfinished section markers
     appearing at the **start of a line** (outside fenced code blocks):
     `[TBD]`, `TODO: `, `[fill in ...`, `XXX `. Inline prose mentioning
     those strings (e.g., describing what the validator rejects) is not
     flagged — the check targets markers left behind in an actual draft.
  2. Every SKILL.md starts with YAML frontmatter containing at least `name`
     and `description` fields. Frontmatter detection tolerates both LF and
     CRLF line endings (Windows checkouts).
  3. Relative file references inside each .md that look like skill-internal
     includes — `steps/NN-*.md`, `references/*.md`, `platform/*.md`, or the
     repo-relative form `pr-(autopilot|followup|loop-lib)/...` — actually
     resolve to a real file on disk, and the resolved path is contained
     within the repo root (`..` traversal that escapes the repo is a bug).
     Absolute `~/.claude/skills/...` references are validated the same way.

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
    r"`("
    r"(?:steps|references|platform)/[A-Za-z0-9._/-]+\.md"   # skill-root-relative
    r"|"
    r"pr-(?:autopilot|followup|loop-lib)/[A-Za-z0-9._/-]+\.md"  # repo-relative
    r")`"
)
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

def _mask_code_blocks(text: str) -> str:
    """Replace fenced code-block content with equivalent-length whitespace
    so offsets (line numbers) are preserved but code contents are not scanned."""
    def repl(m: re.Match) -> str:
        s = m.group(0)
        return re.sub(r"[^\n]", " ", s)
    return FENCED_BLOCK.sub(repl, text)

def check_file(path: pathlib.Path) -> list[str]:
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
    # (pr-autopilot / pr-followup / pr-loop-lib). References like
    # `steps/...`, `references/...`, `platform/...` resolve against this
    # root, not against the current file's directory.
    skill_root = None
    for ancestor in path.parents:
        if ancestor.name in SKILL_ROOTS:
            skill_root = ancestor
            break
    repo_resolved = REPO.resolve()
    def _is_within_repo(p: pathlib.Path) -> bool:
        try:
            p.relative_to(repo_resolved)
            return True
        except ValueError:
            return False
    for m in REL_REF.finditer(text):
        rel = m.group(1)
        # If the reference already starts with a skill root name, resolve it
        # from the repo root. Otherwise try relative to the current skill
        # root, the current file's dir, and each other skill root.
        candidates = []
        first_segment = rel.split("/", 1)[0]
        if first_segment in SKILL_ROOTS:
            candidates.append((REPO / rel).resolve())
        else:
            if skill_root is not None:
                candidates.append((skill_root / rel).resolve())
            candidates.append((path.parent / rel).resolve())
            for other_root_name in SKILL_ROOTS:
                candidates.append((REPO / other_root_name / rel).resolve())
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
        target = (REPO / ref).resolve()
        if not target.exists() or not _is_within_repo(target):
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
