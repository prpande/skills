"""Test the hint-frontmatter lint rule in validate.py.

Uses the `SKILLS_REPO_OVERRIDE` env var to point validate.py at a tmp dir
so tests can build isolated skill trees without touching the real repo.
"""
from __future__ import annotations
import os
import pathlib
import subprocess
import sys
import textwrap

REPO = pathlib.Path(__file__).resolve().parent.parent


def run_validator(tmpdir: pathlib.Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "SKILLS_REPO_OVERRIDE": str(tmpdir)}
    return subprocess.run(
        [sys.executable, str(REPO / "scripts" / "validate.py")],
        cwd=tmpdir,
        capture_output=True,
        text=True,
        env=env,
    )


def make_minimal_skill(root: pathlib.Path, name: str) -> None:
    skill = root / "skills" / "design-tooling" / name
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text(textwrap.dedent(f"""\
        ---
        name: {name}
        description: Stub skill for lint tests.
        ---
        # {name}
    """))


def test_valid_hint_passes(tmp_path: pathlib.Path) -> None:
    make_minimal_skill(tmp_path, "design-coverage")
    platforms = tmp_path / "skills" / "design-tooling" / "design-coverage" / "platforms"
    platforms.mkdir()
    (platforms / "ios.md").write_text(textwrap.dedent("""\
        ---
        name: ios
        detect:
          - "**/*.xcodeproj"
          - "Package.swift"
        description: iOS stack hint.
        confidence: high
        ---

        ## 01 Flow locator
        Test.

        ## 02 Code inventory
        Test.

        ## 03 Clarification
        Test.
    """))
    result = run_validator(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_missing_frontmatter_fails(tmp_path: pathlib.Path) -> None:
    make_minimal_skill(tmp_path, "design-coverage")
    platforms = tmp_path / "skills" / "design-tooling" / "design-coverage" / "platforms"
    platforms.mkdir()
    (platforms / "ios.md").write_text("No frontmatter here.\n")
    result = run_validator(tmp_path)
    assert result.returncode != 0
    assert "frontmatter" in (result.stdout + result.stderr).lower()


def test_missing_section_header_fails(tmp_path: pathlib.Path) -> None:
    make_minimal_skill(tmp_path, "design-coverage")
    platforms = tmp_path / "skills" / "design-tooling" / "design-coverage" / "platforms"
    platforms.mkdir()
    (platforms / "ios.md").write_text(textwrap.dedent("""\
        ---
        name: ios
        detect:
          - "*.xcodeproj"
        description: iOS.
        confidence: high
        ---

        ## 01 Flow locator
        Only one section.
    """))
    result = run_validator(tmp_path)
    assert result.returncode != 0
    stderr_out = (result.stdout + result.stderr).lower()
    assert "02 code inventory" in stderr_out or "03 clarification" in stderr_out
