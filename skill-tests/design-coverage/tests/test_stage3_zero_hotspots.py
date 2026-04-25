import json
import os
from pathlib import Path
from validator import Validator

FX = Path(__file__).parents[1] / "fixtures" / "stage-03" / "zero-hotspots"
SCHEMAS = Path(os.environ["DESIGN_COVERAGE_SKILL_ROOT"]) / "schemas"

def stage3_resolve(inventory):
    hotspots = [i for i in inventory["items"] if i.get("hotspot")]
    if not hotspots:
        # Short-circuit: no hotspot questions, no candidate destinations.
        # Still writes figma_dedup_policy with the default (wave 3 #5).
        return {
            "resolved": [],
            "in_scope_destinations": [],
            "figma_dedup_policy": "dark-twins-folded",
        }
    return None

def test_zero_hotspots_short_circuits():
    inv = json.loads((FX / "input" / "code_inventory.json").read_text())
    produced = stage3_resolve(inv)
    expected = json.loads((FX / "expected" / "clarifications.json").read_text())
    assert produced == expected

def test_zero_hotspots_validates():
    data = json.loads((FX / "expected" / "clarifications.json").read_text())
    schema = json.loads((SCHEMAS / "clarifications.json").read_text())
    Validator(SCHEMAS).validate(data, schema)
