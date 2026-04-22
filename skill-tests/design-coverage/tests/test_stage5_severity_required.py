import json
import os
from pathlib import Path
import pytest
from validator import Validator, ValidationError

SCHEMAS = Path(os.environ["DESIGN_COVERAGE_SKILL_ROOT"]) / "schemas"

def _v():
    return Validator(SCHEMAS)

def test_present_row_requires_pass_and_severity():
    schema = json.loads((SCHEMAS / "comparison.json").read_text())
    good = {"rows": [{"pass": "flow", "status": "present", "severity": "info", "code_ref": "A", "figma_ref": "F1", "evidence": "m"}]}
    _v().validate(good, schema)
    bad_no_severity = {"rows": [{"pass": "flow", "status": "present", "code_ref": "A", "figma_ref": "F1", "evidence": "m"}]}
    with pytest.raises(ValidationError):
        _v().validate(bad_no_severity, schema)
    bad_no_pass = {"rows": [{"status": "present", "severity": "info", "code_ref": "A", "figma_ref": "F1", "evidence": "m"}]}
    with pytest.raises(ValidationError):
        _v().validate(bad_no_pass, schema)

def test_new_in_figma_row_requires_pass_and_severity():
    schema = json.loads((SCHEMAS / "comparison.json").read_text())
    good = {"rows": [{"pass": "flow", "status": "new-in-figma", "severity": "info", "code_ref": None, "figma_ref": "F2", "evidence": "new"}]}
    _v().validate(good, schema)
    bad = {"rows": [{"pass": "flow", "status": "new-in-figma", "code_ref": None, "figma_ref": "F2", "evidence": "new"}]}
    with pytest.raises(ValidationError):
        _v().validate(bad, schema)
