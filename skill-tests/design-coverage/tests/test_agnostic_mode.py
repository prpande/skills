"""Tests that agnostic mode produces a composed prompt with no platform section."""
from __future__ import annotations
import pathlib

from test_hint_injection import inject_hint


def test_agnostic_prompt_has_no_hint_section() -> None:
    core_prompt_path = pathlib.Path(__file__).resolve().parents[3] / \
        "skills" / "design-tooling" / "design-coverage" / "stages" / "01-flow-locator.md"
    core = core_prompt_path.read_text(encoding="utf-8")
    composed = inject_hint(core, "", "agnostic", "01")
    assert "<!-- PLATFORM_HINTS -->" not in composed
    assert "Platform-specific hints" not in composed


def test_agnostic_prompt_preserves_core_content() -> None:
    core_prompt_path = pathlib.Path(__file__).resolve().parents[3] / \
        "skills" / "design-tooling" / "design-coverage" / "stages" / "01-flow-locator.md"
    core = core_prompt_path.read_text(encoding="utf-8")
    composed = inject_hint(core, "", "agnostic", "01")
    assert "Stage 01" in composed
    assert "Flow locator" in composed
