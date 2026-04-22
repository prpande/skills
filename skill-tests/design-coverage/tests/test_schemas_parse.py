import json
import os
from pathlib import Path

SCHEMAS = Path(os.environ["DESIGN_COVERAGE_SKILL_ROOT"]) / "schemas"

def test_all_schemas_parse():
    files = sorted(SCHEMAS.glob("*.json"))
    assert len(files) == 8, f"expected 8 schemas, found {len(files)}"
    for f in files:
        json.loads(f.read_text())
