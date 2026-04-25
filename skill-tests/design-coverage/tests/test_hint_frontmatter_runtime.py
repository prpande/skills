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
