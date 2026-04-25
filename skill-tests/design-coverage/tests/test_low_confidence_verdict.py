"""Tests for the low-confidence anchor verdict warning (wave 3 #13).

The narrative render in SKILL.md reads 01-flow-mapping.json and prepends a
warning block when confidence == "low" OR locator_method == "name-search".
"""
from __future__ import annotations

WARNING_PREFIX = "> ⚠ **Low-confidence anchor — review stage 1 before trusting this report.**"


def should_warn(flow_mapping: dict) -> bool:
    """Return True if the verdict block should be prepended with the warning."""
    return (
        flow_mapping.get("confidence") == "low"
        or flow_mapping.get("locator_method") == "name-search"
    )


def render_verdict_block(flow_mapping: dict, verdict_line: str) -> str:
    """Render the verdict block with or without the low-confidence warning."""
    if should_warn(flow_mapping):
        return f"{WARNING_PREFIX}\n{verdict_line}"
    return verdict_line


# --- Tests ---

def test_low_confidence_triggers_warning():
    fm = {"confidence": "low", "locator_method": "nav-graph", "mappings": []}
    assert should_warn(fm) is True


def test_name_search_triggers_warning():
    fm = {"confidence": "high", "locator_method": "name-search", "mappings": []}
    assert should_warn(fm) is True


def test_medium_confidence_name_search_triggers_warning():
    fm = {"confidence": "medium", "locator_method": "name-search", "mappings": []}
    assert should_warn(fm) is True


def test_high_confidence_nav_graph_no_warning():
    fm = {"confidence": "high", "locator_method": "nav-graph", "mappings": []}
    assert should_warn(fm) is False


def test_medium_confidence_nav_graph_no_warning():
    fm = {"confidence": "medium", "locator_method": "nav-graph", "mappings": []}
    assert should_warn(fm) is False


def test_warning_block_contains_expected_text():
    fm = {"confidence": "low", "locator_method": "nav-graph", "mappings": []}
    verdict_line = "> **Verdict:** 🟢 Ready to ship"
    block = render_verdict_block(fm, verdict_line)
    assert "⚠" in block
    assert "Low-confidence anchor" in block
    assert verdict_line in block


def test_clean_block_has_no_warning():
    fm = {"confidence": "high", "locator_method": "nav-graph", "mappings": []}
    verdict_line = "> **Verdict:** 🟢 Ready to ship"
    block = render_verdict_block(fm, verdict_line)
    assert block == verdict_line
    assert "⚠" not in block


def test_refused_locator_no_warning_unless_low_confidence():
    """A refused flow-mapping has no useful confidence signal — only the
    confidence field itself determines whether the warning fires."""
    fm = {"confidence": "high", "locator_method": "refused", "mappings": []}
    assert should_warn(fm) is False

    fm_low = {"confidence": "low", "locator_method": "refused", "mappings": []}
    assert should_warn(fm_low) is True
