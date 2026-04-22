"""Tests that multi-match platform detection produces an explicit refusal contract.

The detection function itself returns the full list of matches; the orchestrator
(SKILL.md) is responsible for refusing loudly when the list has >1 entry. This
test pins the detection contract so SKILL.md can rely on it.
"""
from __future__ import annotations
import pathlib

from test_platform_detection import detect_platforms, make_hint


def test_multi_match_returns_all(tmp_path: pathlib.Path) -> None:
    platforms = tmp_path / "platforms"
    make_hint(platforms, "ios", ["*.xcodeproj"])
    make_hint(platforms, "android", ["build.gradle"])
    repo = tmp_path / "repo"
    (repo / "App.xcodeproj").mkdir(parents=True)
    (repo / "build.gradle").write_text("")
    assert sorted(detect_platforms(repo, platforms)) == ["android", "ios"]


def test_single_match_returns_one(tmp_path: pathlib.Path) -> None:
    platforms = tmp_path / "platforms"
    make_hint(platforms, "ios", ["*.xcodeproj"])
    make_hint(platforms, "android", ["build.gradle"])
    repo = tmp_path / "repo"
    (repo / "App.xcodeproj").mkdir(parents=True)
    assert detect_platforms(repo, platforms) == ["ios"]
