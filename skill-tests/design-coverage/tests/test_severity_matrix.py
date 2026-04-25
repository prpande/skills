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


def test_lookup_unknown_tuple_records_miss(tmp_path):
    """Misses are recorded so the matrix can be audited and grown over time."""
    import severity_matrix as sm
    misses_path = tmp_path / "_severity_lookup_misses.json"
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


def test_reset_misses_clears_buffer():
    """reset_misses() is the public alias call sites use to start a fresh per-run audit."""
    import severity_matrix as sm
    sm._MISS_BUFFER.clear()
    sm.lookup("missing", "novel-kind", None, None)
    assert len(sm._MISS_BUFFER) == 1
    sm.reset_misses()
    assert sm._MISS_BUFFER == []


def test_flush_misses_replaces_existing_file_not_appends(tmp_path):
    """flush_misses must overwrite, not append: per-run audit, not cumulative log."""
    import json
    import severity_matrix as sm
    target = tmp_path / "_severity_lookup_misses.json"

    # First run records one miss.
    sm.reset_misses()
    sm.lookup("missing", "kind-a", None, None)
    sm.flush_misses(target)
    first_payload = json.loads(target.read_text())
    assert len(first_payload) == 1
    assert first_payload[0]["kind"] == "kind-a"

    # Second run records a different miss; output must reflect ONLY the second run.
    sm.reset_misses()
    sm.lookup("missing", "kind-b", None, None)
    sm.flush_misses(target)
    second_payload = json.loads(target.read_text())
    assert len(second_payload) == 1, f"flush appended instead of replacing: {second_payload}"
    assert second_payload[0]["kind"] == "kind-b"


def test_flush_misses_empty_buffer_clears_stale_file(tmp_path):
    """Run with zero misses must NOT inherit a stale miss file from a prior run."""
    import json
    import severity_matrix as sm
    target = tmp_path / "_severity_lookup_misses.json"

    # Stale file from a prior run.
    sm.reset_misses()
    sm.lookup("missing", "stale-kind", None, None)
    sm.flush_misses(target)
    assert json.loads(target.read_text()) != []  # sanity

    # New run produces zero misses; flush must overwrite to empty list.
    sm.reset_misses()
    sm.flush_misses(target)
    after = json.loads(target.read_text())
    assert after == [], f"empty-buffer flush left stale entries: {after}"


def test_lookup_fallback_walk_order():
    """Document-and-test the four-step walk: (s,k,h,a) → (s,k,h,None) → (s,k,None,None) → (s,None,None,None)."""
    from severity_matrix import lookup, SEVERITY_MATRIX

    # Step 1: exact match wins.
    assert lookup("missing", "action", "feature-flag", "on") == "error"

    # Step 2: hotspot-specific, clarification-agnostic — synthesise via temporary entry.
    SEVERITY_MATRIX[("missing", "action", "config-qualifier", None)] = "info"
    try:
        assert lookup("missing", "action", "config-qualifier", "weird-answer") == "info"
    finally:
        del SEVERITY_MATRIX[("missing", "action", "config-qualifier", None)]

    # Step 3: kind-specific, hotspot-agnostic — already in matrix as ("missing","action",None,None).
    assert lookup("missing", "action", "type-not-in-matrix", "any-answer") == "warn"

    # Step 4: status-only catch-all — ("present", None, None, None).
    assert lookup("present", "kind-not-listed", "hotspot-not-listed", "answer") == "info"
