"""Resolve the paired design-coverage skill's platforms/ dir.

Scout drafts land in the paired `design-coverage` skill's `platforms/`
directory. When scout is installed via symlink (shared skills-repo
pattern), `realpath(__file__)` traverses the symlink back to the repo
clone and the sibling `design-coverage/` lives next to scout there, so
drafts land in the repo for sharing. When scout is installed via copy,
the fallback points at the user's local `~/.claude/skills/...`.

`__file__` works here because this runs in a real .py module — the
equivalent expression inside an inline `python -c` block would raise
NameError.
"""
import os
import pathlib


def resolve_target_dir() -> pathlib.Path:
    scout_root = pathlib.Path(os.path.realpath(__file__)).parent.parent
    target = scout_root.parent / "design-coverage" / "platforms"
    if not target.exists():
        target = pathlib.Path.home() / ".claude" / "skills" / "design-coverage" / "platforms"
    target.mkdir(parents=True, exist_ok=True)
    return target
