"""Tests for schemas/frame_classification.json (wave 3 #5)."""
from __future__ import annotations

import json
import os
import pytest
from pathlib import Path
from validator import ValidationError, Validator

SCHEMAS = Path(os.environ["DESIGN_COVERAGE_SKILL_ROOT"]) / "schemas"
FIXTURES = Path(__file__).parents[1] / "fixtures" / "frame-classification"


def test_schema_file_exists():
    schema_path = SCHEMAS / "frame_classification.json"
    assert schema_path.exists(), "schemas/frame_classification.json is missing"
    json.loads(schema_path.read_text())  # must parse as valid JSON


def test_valid_leaf_only_passes():
    data = json.loads((FIXTURES / "valid_leaf_only.json").read_text())
    schema = json.loads((SCHEMAS / "frame_classification.json").read_text())
    Validator(SCHEMAS).validate(data, schema)  # must not raise


def test_valid_mixed_passes():
    data = json.loads((FIXTURES / "valid_mixed.json").read_text())
    schema = json.loads((SCHEMAS / "frame_classification.json").read_text())
    Validator(SCHEMAS).validate(data, schema)  # must not raise


def test_missing_is_leaf_fails():
    data = json.loads((FIXTURES / "invalid_missing_is_leaf.json").read_text())
    schema = json.loads((SCHEMAS / "frame_classification.json").read_text())
    with pytest.raises(ValidationError):
        Validator(SCHEMAS).validate(data, schema)


def test_leaf_frame_is_leaf_true():
    data = json.loads((FIXTURES / "valid_leaf_only.json").read_text())
    for frame in data["frames"]:
        assert frame["is_leaf"] is True


def test_parent_frame_is_leaf_false():
    data = json.loads((FIXTURES / "valid_mixed.json").read_text())
    parent = next(f for f in data["frames"] if f["frame_id"] == "2:1")
    assert parent["is_leaf"] is False


def test_figma_parent_id_nullable():
    data = json.loads((FIXTURES / "valid_leaf_only.json").read_text())
    for frame in data["frames"]:
        assert frame["figma_parent_id"] is None
