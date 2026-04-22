import json
import os
from pathlib import Path
from validator import Validator

ROOT = Path(__file__).parents[1]
SCHEMAS = Path(os.environ["DESIGN_COVERAGE_SKILL_ROOT"]) / "schemas"

def _is_default_name(name: str) -> bool:
    import re
    return bool(re.match(r"^(Frame|Rectangle|Group|Ellipse)\s+\d+$", name.strip()))

def stage1_locate(figma_url: str, frames):
    if frames and all(_is_default_name(f["name"]) for f in frames):
        return {
            "figma_url": figma_url,
            "locator_method": "refused",
            "confidence": "low",
            "refused_reason": "Figma frames are all default-named; rename frames or pass --old-flow",
            "mappings": []
        }
    raise NotImplementedError

def test_refuses_on_default_names():
    fx = ROOT / "fixtures" / "stage-01" / "refused-default-names"
    input_frames = json.loads((fx / "input" / "figma_frames.json").read_text())["frames"]
    expected = json.loads((fx / "expected" / "flow_mapping.json").read_text())
    produced = stage1_locate("https://figma.com/example", input_frames)
    assert produced == expected

def test_refused_output_validates_against_schema():
    fx = ROOT / "fixtures" / "stage-01" / "refused-default-names"
    expected = json.loads((fx / "expected" / "flow_mapping.json").read_text())
    schema = json.loads((SCHEMAS / "flow_mapping.json").read_text())
    Validator(SCHEMAS).validate(expected, schema)
