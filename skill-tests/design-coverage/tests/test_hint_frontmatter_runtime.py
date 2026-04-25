"""Wave 2 #10a — runtime validator for hint frontmatter.

Validates the four new optional fields (multi_anchor_suffixes,
default_in_scope_hops, hotspot_question_overrides, sealed_enum_patterns)
and rejects sealed_enum_patterns keys that are not in the schema-derived
registry.
"""
from __future__ import annotations
import textwrap

import pytest

from hint_frontmatter import parse_hint_frontmatter, validate_hint_frontmatter


def test_parses_simple_frontmatter() -> None:
    text = textwrap.dedent("""\
        ---
        name: ios
        detect:
          - "*.xcodeproj"
        description: iOS hint.
        confidence: high
        ---
        body
    """)
    fm = parse_hint_frontmatter(text)
    assert fm["name"] == "ios"
    assert fm["detect"] == ["*.xcodeproj"]
    assert fm["confidence"] == "high"


def test_parses_default_in_scope_hops_as_int() -> None:
    text = textwrap.dedent("""\
        ---
        name: ios
        detect:
          - "*.xcodeproj"
        description: iOS hint.
        confidence: high
        default_in_scope_hops: 3
        ---
    """)
    fm = parse_hint_frontmatter(text)
    assert fm["default_in_scope_hops"] == 3


def test_validate_passes_minimal_legacy_hint() -> None:
    fm = {
        "name": "ios",
        "detect": ["*.xcodeproj"],
        "description": "iOS hint.",
        "confidence": "high",
    }
    errors = validate_hint_frontmatter(fm, sealed_keys=["x.y.z"])
    assert errors == []


def test_validate_passes_with_new_optional_fields() -> None:
    fm = {
        "name": "ios",
        "detect": ["*.xcodeproj"],
        "description": "iOS hint.",
        "confidence": "high",
        "multi_anchor_suffixes": ["New", "V2"],
        "default_in_scope_hops": 3,
        "hotspot_question_overrides": {"feature-flag": "Treat ON"},
        "sealed_enum_patterns": {
            "inventory_item.kind.screen": {
                "grep": ["class \\w+ViewController"],
                "description": None,
            }
        },
    }
    errors = validate_hint_frontmatter(
        fm, sealed_keys=["inventory_item.kind.screen"]
    )
    assert errors == []


def test_validate_rejects_unknown_sealed_enum_pattern_key() -> None:
    fm = {
        "name": "ios",
        "detect": ["*.xcodeproj"],
        "description": "iOS hint.",
        "confidence": "high",
        "sealed_enum_patterns": {
            "inventory_item.kind.not-a-real-value": {"grep": ["x"]},
        },
    }
    errors = validate_hint_frontmatter(
        fm, sealed_keys=["inventory_item.kind.screen"]
    )
    assert any("not-a-real-value" in e for e in errors), errors


def test_validate_rejects_wrong_type_default_in_scope_hops() -> None:
    fm = {
        "name": "ios",
        "detect": ["*.xcodeproj"],
        "description": "iOS hint.",
        "confidence": "high",
        "default_in_scope_hops": "two",
    }
    errors = validate_hint_frontmatter(fm, sealed_keys=[])
    assert any("default_in_scope_hops" in e for e in errors), errors


def test_validate_rejects_negative_default_in_scope_hops() -> None:
    fm = {
        "name": "ios",
        "detect": ["*.xcodeproj"],
        "description": "iOS hint.",
        "confidence": "high",
        "default_in_scope_hops": -1,
    }
    errors = validate_hint_frontmatter(fm, sealed_keys=[])
    assert any("default_in_scope_hops" in e for e in errors), errors


def test_validate_rejects_non_list_multi_anchor_suffixes() -> None:
    fm = {
        "name": "ios",
        "detect": ["*.xcodeproj"],
        "description": "iOS hint.",
        "confidence": "high",
        "multi_anchor_suffixes": "New,V2",
    }
    errors = validate_hint_frontmatter(fm, sealed_keys=[])
    assert any("multi_anchor_suffixes" in e for e in errors), errors


def test_validate_rejects_empty_detect_item() -> None:
    fm = {
        "name": "ios",
        "detect": ["*.xcodeproj", ""],
        "description": "iOS hint.",
        "confidence": "high",
    }
    errors = validate_hint_frontmatter(fm, sealed_keys=[])
    assert any("detect" in e for e in errors), errors


def test_validate_rejects_non_string_detect_item() -> None:
    fm = {
        "name": "ios",
        "detect": ["*.xcodeproj", 42],
        "description": "iOS hint.",
        "confidence": "high",
    }
    errors = validate_hint_frontmatter(fm, sealed_keys=[])
    assert any("detect" in e for e in errors), errors


def test_validate_rejects_empty_multi_anchor_suffix_item() -> None:
    fm = {
        "name": "ios",
        "detect": ["*.xcodeproj"],
        "description": "iOS hint.",
        "confidence": "high",
        "multi_anchor_suffixes": ["New", ""],
    }
    errors = validate_hint_frontmatter(fm, sealed_keys=[])
    assert any("multi_anchor_suffixes" in e for e in errors), errors


def test_validate_rejects_integer_hotspot_override_value() -> None:
    fm = {
        "name": "ios",
        "detect": ["*.xcodeproj"],
        "description": "iOS hint.",
        "confidence": "high",
        "hotspot_question_overrides": {"feature-flag": 42},
    }
    errors = validate_hint_frontmatter(fm, sealed_keys=[])
    assert any("hotspot_question_overrides" in e for e in errors), errors


def test_validate_rejects_empty_grep_list() -> None:
    fm = {
        "name": "ios",
        "detect": ["*.xcodeproj"],
        "description": "iOS hint.",
        "confidence": "high",
        "sealed_enum_patterns": {
            "inventory_item.kind.screen": {"grep": []},
        },
    }
    errors = validate_hint_frontmatter(
        fm, sealed_keys=["inventory_item.kind.screen"]
    )
    assert any("grep" in e for e in errors), errors


def test_parse_description_empty_sub_val_is_none_not_list() -> None:
    """description: with no value must parse as None, not []."""
    import textwrap
    text = textwrap.dedent("""\
        ---
        name: ios
        detect:
          - "*.xcodeproj"
        description: iOS hint.
        confidence: high
        sealed_enum_patterns:
          inventory_item.kind.screen:
            grep:
              - "class \\\\w+ViewController"
            description:
        ---
    """)
    fm = parse_hint_frontmatter(text)
    sep = fm.get("sealed_enum_patterns", {})
    assert "inventory_item.kind.screen" in sep
    entry = sep["inventory_item.kind.screen"]
    assert entry.get("description") is None, (
        f"Expected None for empty description, got {entry.get('description')!r}"
    )
    assert isinstance(entry.get("grep"), list), "grep must still be a list"


def test_validate_rejects_sealed_enum_patterns_missing_grep() -> None:
    fm = {
        "name": "ios",
        "detect": ["*.xcodeproj"],
        "description": "iOS hint.",
        "confidence": "high",
        "sealed_enum_patterns": {
            "inventory_item.kind.screen": {"description": "no grep here"},
        },
    }
    errors = validate_hint_frontmatter(
        fm, sealed_keys=["inventory_item.kind.screen"]
    )
    assert any("grep" in e for e in errors), errors


# ---------------------------------------------------------------------------
# Round-trip tests: render_draft_to_md → parse_hint_frontmatter
# These guard against latent parser bugs that only surface when Python code
# reads back values that were written by the scout renderer.
# ---------------------------------------------------------------------------

def _render_and_parse(draft: dict) -> dict:
    """Helper: render a draft dict to .md text, then parse the frontmatter."""
    import sys
    from pathlib import Path
    # render_draft lives in the scout lib, not the design-coverage lib.
    scout_lib = (
        Path(__file__).resolve().parents[3]
        / "skills" / "design-tooling" / "design-coverage-scout" / "lib"
    )
    if str(scout_lib) not in sys.path:
        sys.path.insert(0, str(scout_lib))
    from render_draft import render_draft_to_md
    rendered = render_draft_to_md(draft)
    return parse_hint_frontmatter(rendered)


def test_roundtrip_hotspot_question_overrides_non_empty() -> None:
    """Non-empty hotspot_question_overrides must survive a render→parse round-trip,
    including values with special YAML characters."""
    draft = {
        "name": "ios",
        "detect": ["*.xcodeproj"],
        "description": "iOS hint.",
        "confidence": "high",
        "sections": {
            "flow_locator": "x",
            "code_inventory": "x",
            "clarification": "x",
        },
        "hotspot_question_overrides": {
            "feature-flag": 'Treat "ON" as live',
            "permission": "Check staff: role",
        },
    }
    fm = _render_and_parse(draft)
    assert fm.get("hotspot_question_overrides") == {
        "feature-flag": 'Treat "ON" as live',
        "permission": "Check staff: role",
    }


def test_roundtrip_description_with_special_chars() -> None:
    """description values with quotes and backslashes must round-trip correctly."""
    draft = {
        "name": "tricky",
        "detect": ["*.swift"],
        "description": 'Has: colon and "quotes" and \\backslash',
        "confidence": "medium",
        "sections": {
            "flow_locator": "x",
            "code_inventory": "x",
            "clarification": "x",
        },
    }
    fm = _render_and_parse(draft)
    assert fm.get("description") == 'Has: colon and "quotes" and \\backslash'


def test_roundtrip_grep_patterns_are_unescaped() -> None:
    """Grep patterns with backslashes must be returned as single-backslash strings
    (ready for use as Python regex patterns) after a render→parse round-trip."""
    draft = {
        "name": "ios",
        "detect": ["*.xcodeproj"],
        "description": "iOS hint.",
        "confidence": "high",
        "sections": {
            "flow_locator": "x",
            "code_inventory": "x",
            "clarification": "x",
        },
        "sealed_enum_patterns": {
            "inventory_item.kind.screen": {
                "grep": [r"class \w+ViewController"],
                "description": "iOS UIViewController",
            },
        },
    }
    fm = _render_and_parse(draft)
    patterns = fm["sealed_enum_patterns"]["inventory_item.kind.screen"]["grep"]
    assert patterns == [r"class \w+ViewController"], (
        f"Expected single-backslash pattern, got: {patterns!r}"
    )
