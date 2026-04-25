"""Tests for multi-anchor disambiguation logic (wave 3 #4).

The algorithm strips multi_anchor_suffixes from candidate class names, groups
by base name, and flags any group with N >= 2 candidates as ambiguous.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "fixtures" / "stage-01" / "multi-anchor" / "input"


# --- Algorithm helpers (mirrors stage 01 prose) ---

def _strip_suffix(name: str, suffixes: list[str]) -> str:
    for sfx in suffixes:
        if name.endswith(sfx):
            return name[: -len(sfx)]
    return name


def detect_multi_anchor_groups(
    candidates: list[dict],
    suffixes: list[str],
) -> dict[str, list[dict]]:
    """Return {base_name: [candidates]} for every group with N >= 2 members."""
    from collections import defaultdict
    groups: dict[str, list[dict]] = defaultdict(list)
    for c in candidates:
        base = _strip_suffix(c["class_name"], suffixes)
        groups[base].append(c)
    return {b: g for b, g in groups.items() if len(g) >= 2}


def record_anchor_selection(
    run_config: dict,
    selected: str,
    reason: str = "user-picked-multi-anchor",
) -> dict:
    """Return an updated run-config dict with the selected anchor recorded."""
    return {**run_config, "selected_anchor": selected, "selected_anchor_reason": reason}


# --- Fixtures ---

def _load_suffixes() -> list[str]:
    return json.loads((FIXTURE / "hint_suffixes.json").read_text())


CANDIDATES_AMBIGUOUS = [
    {"class_name": "AppointmentDetailsViewController",    "file": "AppointmentDetailsViewController.swift",    "mtime": "2024-11-08", "lines": 120},
    {"class_name": "AppointmentDetailsHostingController", "file": "AppointmentDetailsHostingController.swift", "mtime": "2026-03-15", "lines": 47},
]

CANDIDATES_SINGLE = [
    {"class_name": "AppointmentDetailsViewController", "file": "AppointmentDetailsViewController.swift", "mtime": "2024-11-08", "lines": 120},
]

CANDIDATES_DIFFERENT_BASE = [
    {"class_name": "MBOApptDetailViewController",         "file": "MBOApptDetailViewController.m",             "mtime": "2024-11-08", "lines": 1842},
    {"class_name": "AppointmentDetailsHostingController", "file": "AppointmentDetailsHostingController.swift", "mtime": "2026-03-15", "lines": 47},
]


# --- Tests ---

def test_multi_anchor_detected():
    suffixes = _load_suffixes()
    groups = detect_multi_anchor_groups(CANDIDATES_AMBIGUOUS, suffixes)
    assert "AppointmentDetails" in groups
    assert len(groups["AppointmentDetails"]) == 2


def test_single_anchor_not_flagged():
    suffixes = _load_suffixes()
    groups = detect_multi_anchor_groups(CANDIDATES_SINGLE, suffixes)
    assert groups == {}


def test_no_suffix_match_not_flagged():
    """Spec's narrative example: different bases after stripping — not flagged."""
    suffixes = _load_suffixes()
    groups = detect_multi_anchor_groups(CANDIDATES_DIFFERENT_BASE, suffixes)
    # MBOApptDetail != AppointmentDetails → no ambiguous group
    assert groups == {}


def test_run_config_records_selected_anchor():
    base_config = {"figma_url": "https://figma.com/test", "platform": "ios"}
    updated = record_anchor_selection(base_config, "AppointmentDetailsViewController")
    assert updated["selected_anchor"] == "AppointmentDetailsViewController"
    assert updated["selected_anchor_reason"] == "user-picked-multi-anchor"
    # Original keys preserved
    assert updated["figma_url"] == base_config["figma_url"]


def test_fixture_files_exist():
    assert (FIXTURE / "AppointmentDetailsViewController.swift").exists()
    assert (FIXTURE / "AppointmentDetailsHostingController.swift").exists()
    assert (FIXTURE / "hint_suffixes.json").exists()


def test_empty_suffixes_never_flags():
    groups = detect_multi_anchor_groups(CANDIDATES_AMBIGUOUS, [])
    # With no suffixes, class names themselves are bases → different names → no group
    assert groups == {}
