import json
import os
from pathlib import Path
import pytest
from validator import Validator, ValidationError

SCHEMAS = Path(os.environ["DESIGN_COVERAGE_SKILL_ROOT"]) / "schemas"
FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "run-json"
    / "expected"
    / "run.json"
)

def _schema():
    return json.loads((SCHEMAS / "run.json").read_text())

def test_run_json_fixture_validates():
    validator = Validator(SCHEMAS)
    data = json.loads(FIXTURE.read_text())
    validator.validate(data, _schema())

    # Every stage property 1..6 must be present and carry a valid status.
    allowed = {"pending", "in_progress", "completed", "refused", "failed"}
    for stage in ("1", "2", "3", "4", "5", "6"):
        assert stage in data["stages"]
        entry = data["stages"][stage]
        assert entry["status"] in allowed
        assert "retries" not in entry

def test_run_json_missing_status_fails():
    validator = Validator(SCHEMAS)
    data = json.loads(FIXTURE.read_text())
    # Remove required "status" from stage 3 — must raise ValidationError.
    del data["stages"]["3"]["status"]
    with pytest.raises(ValidationError):
        validator.validate(data, _schema())
