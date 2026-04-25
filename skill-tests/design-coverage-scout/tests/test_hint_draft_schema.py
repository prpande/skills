"""Verify hint_draft.json schema parses and accepts valid/rejects invalid drafts."""
from __future__ import annotations
import json
import pathlib

import pytest

from validator import Validator, ValidationError


REPO = pathlib.Path(__file__).resolve().parents[3]
SCOUT_SCHEMAS = REPO / "skills" / "design-tooling" / "design-coverage-scout" / "schemas"
SCHEMA_PATH = SCOUT_SCHEMAS / "hint_draft.json"


def test_schema_parses() -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    assert schema["type"] == "object"
    assert "required" in schema


def test_valid_draft_passes() -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    draft = {
        "name": "react-native",
        "detect": ["metro.config.js"],
        "description": "React Native hint.",
        "confidence": "medium",
        "sections": {
            "flow_locator": "Look for App.tsx or navigation config.",
            "code_inventory": "Grep for `export const` components.",
            "clarification": "Ask about runtime permissions via react-native-permissions.",
        },
    }
    Validator(SCOUT_SCHEMAS).validate(draft, schema)


def test_missing_section_fails() -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    draft = {
        "name": "react-native",
        "detect": ["metro.config.js"],
        "description": "RN.",
        "confidence": "medium",
        "sections": {"flow_locator": "x"},
    }
    with pytest.raises(ValidationError):
        Validator(SCOUT_SCHEMAS).validate(draft, schema)


def test_invalid_confidence_fails() -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    draft = {
        "name": "x",
        "detect": ["foo"],
        "description": "x",
        "confidence": "yolo",
        "sections": {
            "flow_locator": "x",
            "code_inventory": "x",
            "clarification": "x",
        },
    }
    with pytest.raises(ValidationError):
        Validator(SCOUT_SCHEMAS).validate(draft, schema)


def test_unresolved_questions_optional() -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    draft = {
        "name": "rn",
        "detect": ["metro.config.js"],
        "description": "RN.",
        "confidence": "medium",
        "sections": {
            "flow_locator": "x",
            "code_inventory": "x",
            "clarification": "x",
        },
        "unresolved_questions": ["How are deep links wired?"],
    }
    Validator(SCOUT_SCHEMAS).validate(draft, schema)


def test_draft_with_sealed_enum_patterns_passes() -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    draft = {
        "name": "mindbodypos-ios",
        "detect": ["*.xcodeproj"],
        "description": "iOS.",
        "confidence": "high",
        "sections": {
            "flow_locator": "x",
            "code_inventory": "x",
            "clarification": "x",
        },
        "sealed_enum_patterns": {
            "inventory_item.kind.screen": {
                "grep": ["class \\w+ViewController"],
                "description": "iOS UIViewController",
            },
            "inventory_item.hotspot.type.permission": {
                "grep": ["AVCaptureDevice", "CLLocationManager"],
                "description": None,
            },
        },
    }
    Validator(SCOUT_SCHEMAS).validate(draft, schema)


def test_draft_sealed_enum_patterns_missing_grep_caught_by_hint_validator() -> None:
    """The in-repo Validator does not enforce additionalProperties (by design —
    it is documented in the schema but not runtime-checked at the scout draft
    level). The `grep` requirement IS enforced at hint-load time by
    hint_frontmatter.validate_hint_frontmatter. This test documents that
    contract: the schema-level validator passes while the frontmatter validator
    rejects.
    """
    import sys
    from pathlib import Path
    dc_lib = REPO / "skills" / "design-tooling" / "design-coverage" / "lib"
    if str(dc_lib) not in sys.path:
        sys.path.insert(0, str(dc_lib))
    from hint_frontmatter import validate_hint_frontmatter

    fm = {
        "name": "x",
        "detect": ["foo"],
        "description": "x",
        "confidence": "medium",
        "sealed_enum_patterns": {
            "inventory_item.kind.screen": {"description": "no grep!"},
        },
    }
    errors = validate_hint_frontmatter(fm, sealed_keys=["inventory_item.kind.screen"])
    assert any("grep" in e for e in errors), errors


def test_draft_top_level_optional_fields_pass() -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    draft = {
        "name": "x",
        "detect": ["foo"],
        "description": "x",
        "confidence": "medium",
        "sections": {"flow_locator": "x", "code_inventory": "x", "clarification": "x"},
        "multi_anchor_suffixes": ["New", "V2"],
        "default_in_scope_hops": 3,
        "hotspot_question_overrides": {"feature-flag": "Treat ON"},
    }
    Validator(SCOUT_SCHEMAS).validate(draft, schema)
