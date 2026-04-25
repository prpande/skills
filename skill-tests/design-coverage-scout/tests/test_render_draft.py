"""Verify that a drafted hint, when written to disk, satisfies the validator.

Uses SKILLS_REPO_OVERRIDE to point validate.py at a tmp repo tree.
"""
from __future__ import annotations
import os
import pathlib
import subprocess
import sys
import textwrap

REPO = pathlib.Path(__file__).resolve().parents[3]

SCOUT_LIB = REPO / "skills" / "design-tooling" / "design-coverage-scout" / "lib"
if str(SCOUT_LIB) not in sys.path:
    sys.path.insert(0, str(SCOUT_LIB))
from render_draft import render_draft_to_md  # noqa: E402


def test_rendered_hint_satisfies_validator(tmp_path: pathlib.Path) -> None:
    skill = tmp_path / "skills" / "design-tooling" / "design-coverage"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(textwrap.dedent("""\
        ---
        name: design-coverage
        description: Stub.
        ---
        # design-coverage
    """))
    (skill / "platforms").mkdir()
    draft = {
        "name": "react-native",
        "detect": ["metro.config.js"],
        "description": "React Native.",
        "confidence": "medium",
        "sections": {
            "flow_locator": "Grep react-navigation config.",
            "code_inventory": "Grep functional components with JSX.",
            "clarification": "Ask about permissions.",
        },
        "unresolved_questions": ["How are deep links wired?"],
    }
    rendered = render_draft_to_md(draft)
    (skill / "platforms" / "react-native.md").write_text(rendered)

    env = {**os.environ, "SKILLS_REPO_OVERRIDE": str(tmp_path)}
    r = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "validate.py")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=env,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_rendered_hint_omits_unresolved_when_empty(tmp_path: pathlib.Path) -> None:
    draft = {
        "name": "rn",
        "detect": ["metro.config.js"],
        "description": "RN.",
        "confidence": "high",
        "sections": {
            "flow_locator": "x",
            "code_inventory": "x",
            "clarification": "x",
        },
    }
    rendered = render_draft_to_md(draft)
    assert "## Unresolved questions" not in rendered


def test_render_includes_sealed_enum_patterns_block(tmp_path: pathlib.Path) -> None:
    """A draft with sealed_enum_patterns must render those into the .md
    frontmatter so the consuming-repo hint carries the data the runtime
    validator looks for.
    """
    draft = {
        "name": "test-repo",
        "detect": ["*.xcodeproj"],
        "description": "Test.",
        "confidence": "high",
        "sections": {
            "flow_locator": "x", "code_inventory": "x", "clarification": "x",
        },
        "sealed_enum_patterns": {
            "inventory_item.kind.screen": {
                "grep": ["class \\w+ViewController"],
                "description": "iOS UIViewController",
            },
        },
        "default_in_scope_hops": 3,
        "multi_anchor_suffixes": ["New", "V2"],
        "hotspot_question_overrides": {},
    }
    rendered = render_draft_to_md(draft)
    assert "sealed_enum_patterns:" in rendered
    assert "inventory_item.kind.screen:" in rendered
    # Backslashes are doubled in the YAML output for round-trip safety
    assert "class \\\\w+ViewController" in rendered
    assert "default_in_scope_hops: 3" in rendered
    assert "multi_anchor_suffixes:" in rendered
    assert "hotspot_question_overrides: {}" in rendered


def test_description_with_special_chars_is_quoted() -> None:
    """description values containing ':' or '"' must be emitted as double-quoted
    YAML scalars so the frontmatter remains valid YAML."""
    draft = {
        "name": "tricky",
        "detect": ["*.swift"],
        "description": 'Has: colon and "quotes"',
        "confidence": "medium",
        "sections": {
            "flow_locator": "x",
            "code_inventory": "x",
            "clarification": "x",
        },
    }
    rendered = render_draft_to_md(draft)
    assert 'description: "Has: colon and \\"quotes\\""' in rendered
