import json
import os
from pathlib import Path
from validator import Validator

ROOT = Path(__file__).parents[1] / "fixtures"
SCHEMAS = Path(os.environ["DESIGN_COVERAGE_SKILL_ROOT"]) / "schemas"

SCHEMA_MAP = {
    "flow_mapping.json": "flow_mapping.json",
    "code_inventory.json": "code_inventory.json",
    "clarifications.json": "clarifications.json",
    "figma_inventory.json": "figma_inventory.json",
    "comparison.json": "comparison.json",
    "report.json": "report.json",
    "run.json": "run.json",
}

def test_every_expected_fixture_validates():
    validator = Validator(SCHEMAS)
    checked = 0
    for path in ROOT.rglob("expected/*.json"):
        schema_name = SCHEMA_MAP.get(path.name)
        if not schema_name:
            continue
        schema = json.loads((SCHEMAS / schema_name).read_text())
        data = json.loads(path.read_text())
        validator.validate(data, schema)
        checked += 1
    assert checked >= 1
