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
