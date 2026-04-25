"""Wave 2 #10c — scout writes the hint into the consuming repo, not the
skill install dir.
"""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCOUT_LIB = REPO / "skills" / "design-tooling" / "design-coverage-scout" / "lib"
sys.path.insert(0, str(SCOUT_LIB))


def _git_init(d: Path) -> None:
    subprocess.run(["git", "init", "-q", str(d)], check=True)


def test_writes_into_consuming_repo_root_when_inside_a_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    consuming = tmp_path / "consuming-repo"
    consuming.mkdir()
    _git_init(consuming)
    monkeypatch.chdir(consuming)
    from target_path import resolve_target_dir
    target = resolve_target_dir()
    assert target == consuming / ".claude" / "skills" / "design-coverage" / "platforms"
    assert target.is_dir()


def test_falls_back_to_cwd_when_not_in_a_git_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    consuming = tmp_path / "loose-dir"
    consuming.mkdir()
    monkeypatch.chdir(consuming)
    from target_path import resolve_target_dir
    target = resolve_target_dir()
    assert target == consuming / ".claude" / "skills" / "design-coverage" / "platforms"
    assert target.is_dir()


def test_walks_up_to_git_root_from_subdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    consuming = tmp_path / "consuming-repo"
    consuming.mkdir()
    _git_init(consuming)
    sub = consuming / "src" / "deep" / "subdir"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    from target_path import resolve_target_dir
    target = resolve_target_dir()
    assert target == consuming / ".claude" / "skills" / "design-coverage" / "platforms"
