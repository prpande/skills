# skills/design-tooling/design-coverage/lib/severity_matrix.py
"""Deterministic severity lookup for stage 05's comparator.

Today (pre-wave-1) stage 05 has prose rules ("error if user-noticeable
workflow loss") that two agents read and apply differently — producing
divergent severity calls on the same data. This module replaces the prose
with a table lookup so the comparator's job is purely mechanical.

The matrix is indexed by (status, kind, hotspot_type, clarification_answer).
None matches "any value" for that field. Lookups walk from most-specific to
most-general; the first matching tuple wins.

Unknown tuples fall back to "warn" AND get recorded to a miss buffer the
caller can flush to <run_dir>/_severity_lookup_misses.json. Misses are
the audit signal for "the matrix needs another entry."
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

# (status, kind, hotspot_type, clarification_answer) -> severity
# `None` in any slot matches any value for that slot.
SEVERITY_MATRIX: dict[tuple[Optional[str], Optional[str], Optional[str], Optional[str]], str] = {
    # ----- present rows are always info -----
    ("present", None, None, None): "info",

    # ----- new-in-figma rows are always info (per wave 1 #3 spec) -----
    ("new-in-figma", None, None, None): "info",

    # ----- restructured rows default to warn (no info loss assumed) -----
    ("restructured", None, None, None): "warn",

    # ----- missing screens are always error (entire surface gone) -----
    ("missing", "screen", None, None): "error",

    # ----- missing actions/states/fields depend on hotspot + clarification -----
    # View-type variants where the user said all are required: error.
    ("missing", "action", "view-type", "all_variants_required"): "error",
    ("missing", "state", "view-type", "all_variants_required"): "error",
    ("missing", "field", "view-type", "all_variants_required"): "error",

    # Server-driven sections where user said both states required: error.
    ("missing", "state", "server-driven", "both_states_required"): "error",

    # Feature-flag branches the user said are in scope: error if missing.
    ("missing", "state", "feature-flag", "on"): "error",
    ("missing", "action", "feature-flag", "on"): "error",

    # Permission-granted happy path: missing denied-variants drop to info.
    ("missing", "state", "permission", "granted"): "info",
    ("missing", "action", "permission", "granted"): "info",
    ("missing", "field", "permission", "granted"): "info",

    # Generic missing actions/states/fields without specific clarification: warn.
    ("missing", "action", None, None): "warn",
    ("missing", "state", None, None): "warn",
    ("missing", "field", None, None): "warn",
}

# Miss tracking — buffered in memory; caller flushes to disk at end of stage.
_MISS_BUFFER: list[tuple] = []
_MISSES_PATH = Path("_severity_lookup_misses.json")  # caller overrides via flush_misses(path)


def lookup(
    status: str,
    kind: Optional[str],
    hotspot_type: Optional[str],
    clarification_answer: Optional[str],
) -> str:
    """Return the severity for a comparator row's (status, kind, hotspot_type, clarification) tuple.

    Walks from most-specific to most-general:
      1. Exact (status, kind, hotspot, clarification) match.
      2. (status, kind, hotspot, None).
      3. (status, kind, None, None).
      4. (status, None, None, None).
    First match wins. If nothing matches, falls back to "warn" and records
    the miss for later audit.
    """
    for key in (
        (status, kind, hotspot_type, clarification_answer),
        (status, kind, hotspot_type, None),
        (status, kind, None, None),
        (status, None, None, None),
    ):
        if key in SEVERITY_MATRIX:
            return SEVERITY_MATRIX[key]
    _MISS_BUFFER.append((status, kind, hotspot_type, clarification_answer))
    return "warn"


def flush_misses(path: Optional[Path] = None) -> None:
    """Write the in-memory miss buffer to JSON. Caller invokes at end of stage 05.

    The miss file lives at the run-dir top level (alongside numbered artifacts);
    its name `_severity_lookup_misses.json` is the ONE allowed underscore-prefixed
    file at the top level (per wave 2 #11's scratch-file policy, which exempts
    this audit file).
    """
    target = Path(path) if path is not None else _MISSES_PATH
    if not _MISS_BUFFER:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = []
    payload = existing + [
        {
            "status": s,
            "kind": k,
            "hotspot_type": h,
            "clarification_answer": c,
        }
        for (s, k, h, c) in _MISS_BUFFER
    ]
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _MISS_BUFFER.clear()
