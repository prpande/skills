import json
import os
from pathlib import Path
import pytest
from validator import Validator, ValidationError

SCHEMAS = Path(os.environ["DESIGN_COVERAGE_SKILL_ROOT"]) / "schemas"

def v():
    return Validator(SCHEMAS)

def test_type_string_pass():
    v().validate({"a": "x"}, {"type": "object", "properties": {"a": {"type": "string"}}})

def test_type_string_fail_on_int():
    with pytest.raises(ValidationError):
        v().validate({"a": 1}, {"type": "object", "properties": {"a": {"type": "string"}}})

def test_required_missing():
    with pytest.raises(ValidationError):
        v().validate({}, {"type": "object", "required": ["a"], "properties": {"a": {"type": "string"}}})

def test_enum_string_pass():
    v().validate("screen", {"type": "string", "enum": ["screen", "state"]})

def test_enum_string_fail():
    with pytest.raises(ValidationError):
        v().validate("widget", {"type": "string", "enum": ["screen", "state"]})

def test_enum_integer_pass():
    v().validate(2, {"type": "integer", "enum": [1, 2, 3]})

def test_enum_integer_fail():
    with pytest.raises(ValidationError):
        v().validate(9, {"type": "integer", "enum": [1, 2, 3]})

def test_min_length_fail():
    with pytest.raises(ValidationError):
        v().validate("", {"type": "string", "minLength": 1})

def test_min_items_fail():
    with pytest.raises(ValidationError):
        v().validate([], {"type": "array", "minItems": 1})

def test_minimum_fail():
    with pytest.raises(ValidationError):
        v().validate(-1, {"type": "integer", "minimum": 0})

def test_items_validates_each():
    v().validate([1, 2, 3], {"type": "array", "items": {"type": "integer"}})
    with pytest.raises(ValidationError):
        v().validate([1, "x"], {"type": "array", "items": {"type": "integer"}})

def test_ref_resolution_inventory_item():
    schema = json.loads((SCHEMAS / "inventory_item.json").read_text())
    ok = {
        "id": "appt.details",
        "kind": "screen",
        "title": "Appointment Details",
        "parent_id": None,
        "source": {"surface": "compose", "file": "x.kt", "line": 1, "symbol": "AppointmentDetails"},
        "hotspot": None,
        "confidence": "high",
        "notes": None,
    }
    v().validate(ok, schema)
    bad = {**ok, "kind": "widget"}
    with pytest.raises(ValidationError):
        v().validate(bad, schema)

def test_nullable_type_array():
    v().validate(None, {"type": ["string", "null"]})
    v().validate("x", {"type": ["string", "null"]})

def test_code_inventory_ref_through_items():
    schema = json.loads((SCHEMAS / "code_inventory.json").read_text())
    good = {
        "items": [{
            "id": "a", "kind": "screen", "title": "A", "parent_id": None,
            "source": {"surface": "compose", "file": "a.kt", "line": 1, "symbol": "A"},
            "hotspot": None, "confidence": "high", "notes": None
        }],
        "unwalked_destinations": []
    }
    v().validate(good, schema)


def test_inventory_item_accepts_modes_and_ambiguity():
    """The `modes[]`, `ambiguous`, `ambiguity_reason` fields are optional
    dogfood follow-up additions; items with and without them must validate."""
    schema = json.loads((SCHEMAS / "inventory_item.json").read_text())
    with_optionals = {
        "id": "appt.details",
        "kind": "screen",
        "title": "Appointment Details",
        "parent_id": None,
        "source": {"surface": "compose", "file": "x.kt", "line": 1, "symbol": "AppointmentDetails"},
        "hotspot": None,
        "confidence": "high",
        "notes": None,
        "modes": ["light", "dark"],
        "ambiguous": False,
        "ambiguity_reason": None,
    }
    v().validate(with_optionals, schema)
    ambiguous = {**with_optionals,
                 "ambiguous": True,
                 "ambiguity_reason": "only appears in the Haptics demo"}
    v().validate(ambiguous, schema)
