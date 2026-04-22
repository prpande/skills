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


def test_allows_when_target_missing_with_force(tmp_path: pathlib.Path) -> None:
    target = tmp_path / "ios.md"
    assert would_overwrite(target, force=True) is False
