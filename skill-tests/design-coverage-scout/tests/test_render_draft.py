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


def render_hint_from_draft(draft: dict) -> str:
    """Replica of the rendering logic from scout stage 3."""
    lines = [
        "---",
        f"name: {draft['name']}",
        "detect:",
    ]
    for g in draft["detect"]:
        lines.append(f'  - "{g}"')
    lines += [
        f"description: {draft['description']}",
        f"confidence: {draft['confidence']}",
        "---",
        "",
        "## 01 Flow locator",
        draft["sections"]["flow_locator"],
        "",
        "## 02 Code inventory",
        draft["sections"]["code_inventory"],
        "",
        "## 03 Clarification",
        draft["sections"]["clarification"],
    ]
    if draft.get("unresolved_questions"):
        lines += ["", "## Unresolved questions"]
        for q in draft["unresolved_questions"]:
            lines.append(f"- {q}")
    return "\n".join(lines) + "\n"


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
    rendered = render_hint_from_draft(draft)
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
    rendered = render_hint_from_draft(draft)
    assert "## Unresolved questions" not in rendered
