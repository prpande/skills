"""Bounded CWD scanner for platform-hint `detect:` glob matching.

`pathlib.Path.cwd().glob("**/…")` is unbounded and walks every directory
under CWD, which on a large monorepo with `node_modules/`, `Pods/`,
`DerivedData/`, etc. can scan millions of entries before returning. This
helper walks with `os.walk`, excludes common large directories, caps
depth, and short-circuits on the first match.
"""
import fnmatch
import os
from pathlib import Path
from typing import Iterable

EXCLUDES = frozenset({
    ".git", ".hg", ".svn",
    "node_modules", "bower_components",
    "Pods", "Carthage", "DerivedData",
    "build", "out", "dist", "target",
    ".gradle", ".idea", ".vscode",
    "venv", ".venv", "env", ".env",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".next", ".nuxt", ".cache",
})

MAX_DEPTH = 6


def detect_match(root: Path, glob_pat: str, max_depth: int = MAX_DEPTH,
                 excludes: Iterable[str] = EXCLUDES) -> bool:
    """Return True if any entry under `root` matches `glob_pat`.

    `glob_pat` follows the pathlib glob syntax used in hint `detect:`
    entries. A leading `**/` means "at any depth"; the remainder of the
    pattern is matched against a candidate's basename (files and dirs).
    Patterns without `**/` are matched anchored at `root`.
    """
    excludes = frozenset(excludes)
    pat = glob_pat
    anchored = not pat.startswith("**/")
    if not anchored:
        pat = pat[3:]
    # Handle nested patterns like `*/build.gradle` — split on the final `/`
    # and match each candidate path's trailing components.
    pat_parts = pat.split("/")
    root = Path(root)
    for curpath, dirs, files in os.walk(root):
        rel = Path(curpath).relative_to(root).parts
        depth = len(rel)
        if depth > max_depth:
            dirs.clear()
            continue
        dirs[:] = [d for d in dirs if d not in excludes]
        # Single-segment anchored patterns match only at root; descending
        # doesn't help. Multi-segment anchored patterns like `app/build.gradle`
        # MUST descend to check the nested path, but only within the first
        # pat-part's subtree.
        if anchored and len(pat_parts) == 1 and depth > 0:
            dirs.clear()
            continue
        for name in list(files) + list(dirs):
            if len(pat_parts) == 1:
                if fnmatch.fnmatch(name, pat_parts[0]):
                    return True
            else:
                candidate_parts = rel + (name,)
                if anchored:
                    if len(candidate_parts) != len(pat_parts):
                        continue
                    test_parts = candidate_parts
                else:
                    if len(candidate_parts) < len(pat_parts):
                        continue
                    test_parts = candidate_parts[-len(pat_parts):]
                if all(fnmatch.fnmatch(t, p) for t, p in zip(test_parts, pat_parts)):
                    return True
    return False
