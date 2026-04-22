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
import os
import pathlib
import re
import sys

# Tests can point the validator at a temporary repo tree via this env var.
# Without it, REPO is resolved from this file's location.
_REPO_OVERRIDE = os.environ.get("SKILLS_REPO_OVERRIDE")
REPO = (
    pathlib.Path(_REPO_OVERRIDE).resolve()
    if _REPO_OVERRIDE
    else pathlib.Path(__file__).resolve().parent.parent
)
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


REQUIRED_HINT_SECTIONS = [
    "## 01 Flow locator",
    "## 02 Code inventory",
    "## 03 Clarification",
]
REQUIRED_HINT_FM_KEYS = {"name", "detect", "description", "confidence"}
VALID_CONFIDENCE = {"high", "medium", "low"}


def validate_hint_file(path: pathlib.Path) -> list[str]:
    """Return list of error strings for a platforms/*.md hint file.

    Enforces: frontmatter present with required keys (name, detect,
    description, confidence); `confidence` is one of high/medium/low;
    body contains the three required section headers.
    """
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER.match(text)
    if not m:
        return [f"{path}: missing frontmatter block"]
    fm_text = m.group(1)
    body = text[m.end():]
    # Minimal frontmatter key extraction — only scalar keys at column 0.
    keys: dict[str, str] = {}
    for line in fm_text.splitlines():
        if not line or line[0].isspace() or line.startswith("-"):
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            k = k.strip()
            v = v.strip()
            if k:
                keys[k] = v
    missing = REQUIRED_HINT_FM_KEYS - set(keys)
    if missing:
        errors.append(
            f"{path}: frontmatter missing keys: {sorted(missing)}"
        )
    conf = keys.get("confidence", "")
    if conf and conf not in VALID_CONFIDENCE:
        errors.append(
            f"{path}: frontmatter 'confidence' must be one of "
            f"{sorted(VALID_CONFIDENCE)}, got {conf!r}"
        )
    # Mask fenced code blocks so a hint can't satisfy the lint by mentioning
    # `## 01 Flow locator` inside ```…``` without an actual header outside.
    body_for_headers = _mask_code_blocks(body)
    body_lines = {line.strip() for line in body_for_headers.splitlines()}
    for section in REQUIRED_HINT_SECTIONS:
        if section not in body_lines:
            errors.append(
                f"{path}: missing required section header {section!r}"
            )
    return errors


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
    # Hint-frontmatter lint: any .md under platforms/ inside a skill root
    # (conventionally the design-coverage skill) must satisfy the hint contract.
    for root_path in skill_roots.values():
        platforms = root_path / "platforms"
        if not platforms.is_dir():
            continue
        for hint_file in sorted(platforms.glob("*.md")):
            all_errors.extend(validate_hint_file(hint_file))
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
