"""Verify hint-template.md describes the exact shape that the validator enforces."""
from __future__ import annotations
import pathlib


REPO = pathlib.Path(__file__).resolve().parents[3]
TEMPLATE = REPO / "skills" / "design-tooling" / "design-coverage-scout" / "hint-template.md"


def test_template_exists() -> None:
    assert TEMPLATE.exists()


def test_template_mentions_all_required_sections() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "## 01 Flow locator" in text
    assert "## 02 Code inventory" in text
    assert "## 03 Clarification" in text


def test_template_mentions_all_required_frontmatter_keys() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    for key in ("name", "detect", "description", "confidence"):
        assert f"{key}:" in text, f"template missing {key}"


def test_template_mentions_confidence_values() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    for v in ("high", "medium", "low"):
        assert v in text
