# skill-tests/design-coverage/tests/test_severity_matrix.py
"""Wave 1 #2 — replace stage 05's prose severity rules with a deterministic
table lookup. Two agents on the same comparator inputs must produce identical
severity calls.
"""
from pathlib import Path

import pytest


def test_lookup_known_tuple_returns_expected_severity():
    from severity_matrix import lookup
    # Missing screen with no hotspot is always error.
    assert lookup("missing", "screen", None, None) == "error"


def test_lookup_present_returns_info():
    from severity_matrix import lookup
    assert lookup("present", "screen", None, None) == "info"
    assert lookup("present", "action", None, None) == "info"


def test_lookup_new_in_figma_returns_info():
    from severity_matrix import lookup
    assert lookup("new-in-figma", None, None, None) == "info"


def test_lookup_restructured_returns_warn():
    from severity_matrix import lookup
    assert lookup("restructured", "screen", None, None) == "warn"


def test_lookup_view_type_violation_is_error():
    from severity_matrix import lookup
    # When clarification says all variants required and one is missing, that's an error.
    assert lookup("missing", "action", "view-type", "all_variants_required") == "error"


def test_lookup_permission_granted_missing_is_info():
    from severity_matrix import lookup
    # If user said permission is granted (default happy path), code-side
    # permission-denied paths missing from Figma drop to info.
    assert lookup("missing", "action", "permission", "granted") == "info"


def test_lookup_unknown_tuple_returns_warn_fallback(tmp_path):
    from severity_matrix import lookup
    sev = lookup("missing", "novel-kind-not-in-matrix", None, None)
    assert sev == "warn"


def test_lookup_unknown_tuple_records_miss(tmp_path, monkeypatch):
    """Misses are recorded so the matrix can be audited and grown over time."""
    import severity_matrix as sm
    misses_path = tmp_path / "_severity_lookup_misses.json"
    monkeypatch.setattr(sm, "_MISSES_PATH", misses_path)
    sm._MISS_BUFFER.clear()  # ensure clean state
    sm.lookup("missing", "novel-kind", None, None)
    sm.flush_misses(misses_path)
    import json
    data = json.loads(misses_path.read_text())
    assert any("novel-kind" in str(entry) for entry in data)


def test_lookup_returns_only_canonical_severity_strings():
    """All emitted severities must be one of {info, warn, error}."""
    from severity_matrix import lookup, SEVERITY_MATRIX
    for sev in SEVERITY_MATRIX.values():
        assert sev in {"info", "warn", "error"}, f"matrix has invalid severity: {sev}"
