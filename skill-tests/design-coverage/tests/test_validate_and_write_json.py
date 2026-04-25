"""Wave 2 #7 — validate_and_write_json refuses-loud on schema violations and
does not write the file when validation fails.
"""
import json
import os
from pathlib import Path

import pytest

from skill_io import validate_and_write_json
from validator import ValidationError


SCHEMAS = Path(os.environ["DESIGN_COVERAGE_SKILL_ROOT"]) / "schemas"


def test_writes_when_payload_validates(tmp_path: Path) -> None:
    payload = {
        "items": [],
        "unwalked_destinations": [],
    }
    target = tmp_path / "02-code-inventory.json"
    validate_and_write_json(target, payload, "code_inventory.json", SCHEMAS)
    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8")) == payload


def test_refuses_loud_with_json_pointer_path(tmp_path: Path) -> None:
    bad_payload = {
        "items": [
            {
                "id": "x",
                "kind": "screen",
                "title": "X",
                "parent_id": None,
                "source": {"surface": "foo", "file": "x.swift"},
                "hotspot": None,
                "confidence": "high",
            }
        ],
        "unwalked_destinations": [],
    }
    target = tmp_path / "02-code-inventory.json"
    with pytest.raises(ValidationError) as ei:
        validate_and_write_json(target, bad_payload, "code_inventory.json", SCHEMAS)
    msg = str(ei.value)
    assert "items[0].source.surface" in msg
    assert "foo" in msg
    assert not target.exists(), "validate_and_write_json must NOT write on validation failure"


def test_does_not_leave_a_tmp_file_on_failure(tmp_path: Path) -> None:
    bad_payload = {"items": "not-a-list", "unwalked_destinations": []}
    target = tmp_path / "02-code-inventory.json"
    with pytest.raises(ValidationError):
        validate_and_write_json(target, bad_payload, "code_inventory.json", SCHEMAS)
    assert not target.exists()
    assert not (tmp_path / "02-code-inventory.json.tmp").exists()


def test_unknown_schema_name_raises(tmp_path: Path) -> None:
    """If the caller names a schema that doesn't exist under schemas/, the
    function must refuse loudly rather than silently skipping validation."""
    target = tmp_path / "x.json"
    with pytest.raises((FileNotFoundError, ValidationError)):
        validate_and_write_json(target, {"x": 1}, "no_such_schema.json", SCHEMAS)
    assert not target.exists()


def test_malformed_stage02_payload_blocks_pipeline(tmp_path: Path) -> None:
    """Wave 2 #7 DoD — a deliberately-malformed stage-02 payload causes a
    refuse-loud halt before stage 03 starts.
    """
    target = tmp_path / "02-code-inventory.json"
    bad = {
        "items": [
            {
                "id": "x",
                "kind": "screen",
                "title": "X",
                "parent_id": None,
                "source": {"surface": "foo", "file": "x.swift"},
                "hotspot": None,
                "confidence": "high",
            }
        ],
        "unwalked_destinations": [],
    }
    with pytest.raises(ValidationError):
        validate_and_write_json(target, bad, "code_inventory.json", SCHEMAS)
    assert not target.exists()
