"""Resolve the target dir into which scout writes a generated platform hint.

Wave 2 #10c — hints are repo-local. The target is:

    <consuming-repo-root>/.claude/skills/design-coverage/platforms/

The consuming repo root is discovered by walking up from CWD looking for
a .git directory. If CWD is not inside a Git repo, fall back to CWD
itself (the user gets the hint at <cwd>/.claude/skills/...). Pre-wave-2
behavior — writing into the paired skill's install dir — is intentionally
gone: a hint tuned for one repo had no business being written into the
shared skill install.
"""
from __future__ import annotations

import pathlib


def resolve_target_dir() -> pathlib.Path:
    repo_root = _find_repo_root(pathlib.Path.cwd())
    target = repo_root / ".claude" / "skills" / "design-coverage" / "platforms"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _find_repo_root(start: pathlib.Path) -> pathlib.Path:
    """Walk up from `start` looking for a directory containing `.git`.

    If none is found, return `start`. Pure-Python keeps the helper
    importable inside test environments without a configured git binary.
    `.exists()` handles both `.git` directory (normal repos) and `.git`
    file (worktrees).
    """
    cur = start.resolve()
    for parent in (cur, *cur.parents):
        if (parent / ".git").exists():
            return parent
    return start.resolve()
