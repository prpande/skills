import json
import os
from pathlib import Path
from renderer import render_report
from validator import Validator

FX = Path(__file__).parents[1] / "fixtures" / "end-to-end" / "minimal-smoke"
SCHEMAS = Path(os.environ["DESIGN_COVERAGE_SKILL_ROOT"]) / "schemas"

def test_smoke_validates_and_renders():
    data = json.loads((FX / "expected" / "report.json").read_text())
    schema = json.loads((SCHEMAS / "report.json").read_text())
    Validator(SCHEMAS).validate(data, schema)
    md = render_report(data)
    assert "AppointmentNotes screen missing" in md
    assert "Coverage Matrix" in md

    # Section headers must be present.
    assert "## Summary" in md
    assert "## Coverage Matrix" in md

    # Severity ordering: the error row renders before the info row.
    err_idx = md.index("AppointmentNotes screen missing")
    info_idx = md.index("AppointmentDetails covered")
    assert err_idx < info_idx

    # The matrix table must have exactly 2 data rows between the header
    # separator and end-of-string.
    separator = "|---|---|---|"
    sep_idx = md.index(separator)
    after_sep = md[sep_idx + len(separator):]
    data_rows = [
        line for line in after_sep.splitlines()
        if line.startswith("|") and line.strip() != separator
    ]
    assert len(data_rows) == 2
