"""Tests that hint frontmatter validation catches malformed hints.

Uses SKILLS_REPO_OVERRIDE to point the validator at a tmp repo tree.
"""
from __future__ import annotations
import os
import pathlib
import subprocess
import sys
import textwrap


REPO = pathlib.Path(__file__).resolve().parents[3]


def run_validator(cwd: pathlib.Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "SKILLS_REPO_OVERRIDE": str(cwd)}
    return subprocess.run(
        [sys.executable, str(REPO / "scripts" / "validate.py")],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )


def make_skill_with_hint(root: pathlib.Path, hint_body: str) -> None:
    skill = root / "skills" / "design-tooling" / "design-coverage"
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text(textwrap.dedent("""\
        ---
        name: design-coverage
        description: Stub.
        ---
        # design-coverage
    """))
    (skill / "platforms").mkdir(exist_ok=True)
    (skill / "platforms" / "ios.md").write_text(hint_body)


def test_valid_hint_passes(tmp_path: pathlib.Path) -> None:
    make_skill_with_hint(tmp_path, textwrap.dedent("""\
        ---
        name: ios
        detect:
          - "*.xcodeproj"
        description: iOS.
        confidence: high
        ---
        ## 01 Flow locator
        ok
        ## 02 Code inventory
        ok
        ## 03 Clarification
        ok
    """))
    r = run_validator(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_missing_name_key_fails(tmp_path: pathlib.Path) -> None:
    make_skill_with_hint(tmp_path, textwrap.dedent("""\
        ---
        detect:
          - "*.xcodeproj"
        description: iOS.
        confidence: high
        ---
        ## 01 Flow locator
        x
        ## 02 Code inventory
        x
        ## 03 Clarification
        x
    """))
    r = run_validator(tmp_path)
    assert r.returncode != 0
    assert "name" in (r.stdout + r.stderr).lower()


def test_invalid_confidence_fails(tmp_path: pathlib.Path) -> None:
    make_skill_with_hint(tmp_path, textwrap.dedent("""\
        ---
        name: ios
        detect:
          - "*.xcodeproj"
        description: iOS.
        confidence: yolo
        ---
        ## 01 Flow locator
        x
        ## 02 Code inventory
        x
        ## 03 Clarification
        x
    """))
    r = run_validator(tmp_path)
    assert r.returncode != 0
    assert "confidence" in (r.stdout + r.stderr).lower()
