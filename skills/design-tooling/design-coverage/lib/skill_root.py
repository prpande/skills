"""Resolve the skill root (the directory containing SKILL.md) from this file's location.

Replaces hard-coded ~/.claude/skills/design-coverage/ paths in stage MDs and lib/.
Every Python snippet that needs to load schemas/, platforms/, or sibling lib/
modules should call get_skill_root() rather than constructing a path from $HOME.

Walks up at most 5 parent directories. SKILL.md must exist within that range or
RuntimeError is raised — silent fallback to a wrong root is worse than a halt.
"""
from __future__ import annotations

from pathlib import Path

_MAX_DEPTH = 5


def get_skill_root() -> Path:
    """Return the directory containing SKILL.md, walking up from this file.

    Raises RuntimeError if SKILL.md is not found within _MAX_DEPTH parents
    OR if the walk reaches the filesystem root before finding SKILL.md.
    """
    start = Path(__file__).resolve()
    here = start.parent
    for _ in range(_MAX_DEPTH):
        if (here / "SKILL.md").exists():
            return here
        if here == here.parent:  # filesystem root — going further is a no-op
            break
        here = here.parent
    raise RuntimeError(
        f"Could not locate skill root: SKILL.md not found within "
        f"{_MAX_DEPTH} parent directories of {start} (last checked: {here})"
    )
