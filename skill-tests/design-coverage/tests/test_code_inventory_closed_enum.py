# skill-tests/design-coverage/tests/test_code_inventory_closed_enum.py
"""Wave 1 #3 — verify the closed enum on unwalked_destinations.reason and the
new candidate_destinations array land in code_inventory.json.

The old free-form reason string allowed agents to write 'out-of-scope-destination'
silently. The closed enum forces mechanical reasons only; agents that judge
something as 'maybe in scope' must emit it to candidate_destinations instead,
where stage 03 will surface it to the user.
"""
import json
from pathlib import Path

import pytest
from validator import Validator, ValidationError

SCHEMAS = Path(__file__).resolve().parents[3] / "skills" / "design-tooling" / "design-coverage" / "schemas"


def _load(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def test_unwalked_destinations_reason_is_closed_enum():
    schema = _load("code_inventory.json")
    reason_schema = schema["properties"]["unwalked_destinations"]["items"]["properties"]["reason"]
    assert "enum" in reason_schema
    assert set(reason_schema["enum"]) == {
        "adapter-hosted",
        "external-module",
        "swiftui-bridge",
        "dynamic-identifier",
        "platform-bridge",
        "unresolved-class",
    }


def test_unwalked_destinations_rejects_legacy_free_form_reason():
    schema = _load("code_inventory.json")
    v = Validator(SCHEMAS)
    bad = {
        "items": [],
        "unwalked_destinations": [
            {"nav_source": "X", "target": "Y", "reason": "out-of-scope-destination"}
        ],
        "candidate_destinations": [],
    }
    with pytest.raises(ValidationError):
        v.validate(bad, schema)


def test_candidate_destinations_field_exists_and_is_array():
    schema = _load("code_inventory.json")
    assert "candidate_destinations" in schema["properties"]
    cd = schema["properties"]["candidate_destinations"]
    assert cd["type"] == "array"
    item_props = cd["items"]["properties"]
    for required_key in ("parent_screen", "symbol", "file", "hop_distance", "why_not_walked"):
        assert required_key in item_props
    assert set(cd["items"]["required"]) == {
        "parent_screen", "symbol", "file", "hop_distance", "why_not_walked",
    }


def test_candidate_destination_item_validates():
    schema = _load("code_inventory.json")
    v = Validator(SCHEMAS)
    good = {
        "items": [],
        "unwalked_destinations": [],
        "candidate_destinations": [
            {
                "parent_screen": "MBOApptDetailViewController",
                "symbol": "MBOApptQuickBookViewController",
                "file": "MindBodyPOS/Legacy/.../QuickBook.m",
                "hop_distance": 1,
                "why_not_walked": "Modify-appointment flow; agent unsure if in scope for appointment-details audit.",
            }
        ],
    }
    v.validate(good, schema)  # must not raise


def test_clarifications_has_in_scope_destinations_field():
    schema = _load("clarifications.json")
    assert "in_scope_destinations" in schema["properties"]
    isd = schema["properties"]["in_scope_destinations"]
    assert isd["type"] == "array"


def test_inventory_item_kind_carries_x_platform_pattern():
    schema = _load("inventory_item.json")
    kind = schema["properties"]["kind"]
    assert kind.get("x-platform-pattern") is True


def test_inventory_item_surface_carries_x_platform_pattern():
    schema = _load("inventory_item.json")
    surface = schema["properties"]["source"]["properties"]["surface"]
    assert surface.get("x-platform-pattern") is True


def test_inventory_item_hotspot_type_carries_x_platform_pattern():
    schema = _load("inventory_item.json")
    htype = schema["properties"]["hotspot"]["properties"]["type"]
    assert htype.get("x-platform-pattern") is True


def test_unwalked_reason_carries_x_platform_pattern():
    schema = _load("code_inventory.json")
    reason = schema["properties"]["unwalked_destinations"]["items"]["properties"]["reason"]
    assert reason.get("x-platform-pattern") is True
