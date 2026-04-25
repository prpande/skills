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


def test_empty_detect_block_fails(tmp_path: pathlib.Path) -> None:
    """A hint with a `detect:` key but zero glob entries should fail lint —
    otherwise it passes the required-keys check but is silently undetectable
    at runtime."""
    make_skill_with_hint(tmp_path, textwrap.dedent("""\
        ---
        name: ios
        detect:
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
    assert "detect" in (r.stdout + r.stderr).lower()


def _copy_real_schemas(tmp_path: pathlib.Path) -> None:
    """Copy the real design-coverage schemas into the fake skill tree so
    validate.py can derive sealed keys from the actual schemas."""
    real_schemas = REPO / "skills" / "design-tooling" / "design-coverage" / "schemas"
    fake_schemas = tmp_path / "skills" / "design-tooling" / "design-coverage" / "schemas"
    fake_schemas.mkdir(parents=True, exist_ok=True)
    for sf in real_schemas.glob("*.json"):
        (fake_schemas / sf.name).write_text(sf.read_text(encoding="utf-8"))


def test_hint_with_new_optional_fields_passes(tmp_path: pathlib.Path) -> None:
    make_skill_with_hint(tmp_path, textwrap.dedent("""\
        ---
        name: ios
        detect:
          - "*.xcodeproj"
        description: iOS.
        confidence: high
        multi_anchor_suffixes:
          - "New"
          - "V2"
        default_in_scope_hops: 2
        hotspot_question_overrides: {}
        sealed_enum_patterns:
          inventory_item.kind.screen:
            grep:
              - "class \\\\w+ViewController"
            description: iOS UIViewController
        ---
        ## 01 Flow locator
        ok
        ## 02 Code inventory
        ok
        ## 03 Clarification
        ok
    """))
    _copy_real_schemas(tmp_path)
    r = run_validator(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_hint_with_unknown_sealed_enum_key_fails(tmp_path: pathlib.Path) -> None:
    make_skill_with_hint(tmp_path, textwrap.dedent("""\
        ---
        name: ios
        detect:
          - "*.xcodeproj"
        description: iOS.
        confidence: high
        sealed_enum_patterns:
          inventory_item.kind.not-a-real-value:
            grep:
              - "x"
        ---
        ## 01 Flow locator
        x
        ## 02 Code inventory
        x
        ## 03 Clarification
        x
    """))
    _copy_real_schemas(tmp_path)
    r = run_validator(tmp_path)
    assert r.returncode != 0
    assert "not-a-real-value" in (r.stdout + r.stderr)


def test_hint_with_bad_default_in_scope_hops_fails(tmp_path: pathlib.Path) -> None:
    make_skill_with_hint(tmp_path, textwrap.dedent("""\
        ---
        name: ios
        detect:
          - "*.xcodeproj"
        description: iOS.
        confidence: high
        default_in_scope_hops: -3
        ---
        ## 01 Flow locator
        x
        ## 02 Code inventory
        x
        ## 03 Clarification
        x
    """))
    _copy_real_schemas(tmp_path)
    r = run_validator(tmp_path)
    assert r.returncode != 0
    assert "default_in_scope_hops" in (r.stdout + r.stderr)
