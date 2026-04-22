"""Tests that platform detection globs platforms/*.md frontmatter correctly."""
from __future__ import annotations
import pathlib
import re
import textwrap


def detect_platforms(cwd: pathlib.Path, platforms_dir: pathlib.Path) -> list[str]:
    """Replica of the detection logic from SKILL.md."""
    fm_pat = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    matches: list[str] = []
    for hint in sorted(platforms_dir.glob("*.md")):
        text = hint.read_text(encoding="utf-8")
        m = fm_pat.match(text)
        if not m:
            continue
        fm = m.group(1)
        name = ""
        detect_globs: list[str] = []
        in_detect = False
        for line in fm.splitlines():
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip()
                in_detect = False
            elif line.startswith("detect:"):
                in_detect = True
            elif in_detect:
                stripped = line.lstrip()
                if stripped.startswith("- "):
                    detect_globs.append(stripped[2:].strip().strip('"'))
                elif line and not line[0].isspace():
                    in_detect = False
        for g in detect_globs:
            if list(cwd.glob(g)):
                matches.append(name)
                break
    return matches


def make_hint(platforms_dir: pathlib.Path, name: str, detect: list[str]) -> None:
    platforms_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        f"name: {name}",
        "detect:",
    ]
    for g in detect:
        lines.append(f'  - "{g}"')
    lines += [
        f"description: Test hint for {name}.",
        "confidence: high",
        "---",
        "",
        "## 01 Flow locator",
        "test",
        "## 02 Code inventory",
        "test",
        "## 03 Clarification",
        "test",
        "",
    ]
    (platforms_dir / f"{name}.md").write_text("\n".join(lines))


def test_detects_ios(tmp_path: pathlib.Path) -> None:
    platforms = tmp_path / "platforms"
    make_hint(platforms, "ios", ["**/*.xcodeproj"])
    make_hint(platforms, "android", ["**/build.gradle"])
    repo = tmp_path / "repo"
    (repo / "MyApp.xcodeproj").mkdir(parents=True)
    assert detect_platforms(repo, platforms) == ["ios"]


def test_detects_android(tmp_path: pathlib.Path) -> None:
    platforms = tmp_path / "platforms"
    make_hint(platforms, "ios", ["**/*.xcodeproj"])
    make_hint(platforms, "android", ["**/build.gradle", "AndroidManifest.xml"])
    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    (repo / "app" / "build.gradle").write_text("")
    assert detect_platforms(repo, platforms) == ["android"]


def test_detects_multiple(tmp_path: pathlib.Path) -> None:
    platforms = tmp_path / "platforms"
    make_hint(platforms, "ios", ["**/*.xcodeproj"])
    make_hint(platforms, "android", ["**/build.gradle"])
    repo = tmp_path / "repo"
    (repo / "iOS" / "App.xcodeproj").mkdir(parents=True)
    (repo / "android").mkdir(parents=True)
    (repo / "android" / "build.gradle").write_text("")
    assert sorted(detect_platforms(repo, platforms)) == ["android", "ios"]


def test_detects_none(tmp_path: pathlib.Path) -> None:
    platforms = tmp_path / "platforms"
    make_hint(platforms, "ios", ["**/*.xcodeproj"])
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("")
    assert detect_platforms(repo, platforms) == []
