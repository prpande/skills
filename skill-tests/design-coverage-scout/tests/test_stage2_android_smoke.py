"""Wave 2 #10c smoke — scout stage 02's Android Platform section's grep
patterns find at least one match in a tiny Android-shaped fixture for >= 80%
of the schema-derived registry keys.

Mirrors test_stage2_smoke.py (iOS) but targets the Android section and scans
*.kt and *.xml fixture files.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCOUT_STAGE_MD = (
    REPO / "skills" / "design-tooling" / "design-coverage-scout"
    / "stages" / "02-pattern-extraction.md"
)
DC_LIB = REPO / "skills" / "design-tooling" / "design-coverage" / "lib"
sys.path.insert(0, str(DC_LIB))

from sealed_enum_index import get_sealed_enum_pattern_keys  # noqa: E402

FIXTURE = REPO / "skill-tests" / "fixtures" / "scout-android"

# Keys excluded from the Android tally — each with a reason comment.
N_A_ON_ANDROID = {
    # SwiftUI-specific mechanism; explicitly n/a on Android per the stage MD.
    "code_inventory.unwalked_destinations.reason.swiftui-bridge",
    # File-system path pattern (`res/navigation/.*\.xml`); does not appear
    # as a string in Kotlin source or XML content — only in build output paths.
    "inventory_item.source.surface.nav-xml",
}


def _android_section_text() -> str:
    text = SCOUT_STAGE_MD.read_text(encoding="utf-8")
    m = re.search(r"^#### Android\b(.*?)(?=^#### |^### |\Z)",
                  text, re.MULTILINE | re.DOTALL)
    assert m, "Android Platform section not found in scout stage 02 MD"
    return m.group(1)


def _patterns_for_key(android_section: str, key: str) -> list[str]:
    """Pull the backtick-quoted regex patterns from the bullet for `key`."""
    line_re = re.compile(
        rf"^- \*\*`{re.escape(key)}`\*\*:(.*?)(?=^- \*\*|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = line_re.search(android_section)
    if not m:
        return []
    body = m.group(1)
    return [
        m2.group(1).replace(r"\\", "\\")
        for m2 in re.finditer(r"`([^`]+)`", body)
    ]


def _matches_any(pattern: str, files: list[Path]) -> bool:
    rx = re.compile(pattern)  # raises re.error loudly if pattern is invalid
    return any(rx.search(f.read_text(encoding="utf-8", errors="ignore"))
               for f in files)


def test_android_patterns_cover_at_least_80_percent_of_registry() -> None:
    keys = [k for k in get_sealed_enum_pattern_keys() if k not in N_A_ON_ANDROID]
    android_section = _android_section_text()
    source_files = (
        list(FIXTURE.rglob("*.kt")) + list(FIXTURE.rglob("*.xml"))
    )
    assert source_files, "fixture has no .kt or .xml files"

    covered = []
    for key in keys:
        pats = _patterns_for_key(android_section, key)
        if any(_matches_any(p, source_files) for p in pats):
            covered.append(key)

    coverage = len(covered) / len(keys)
    assert coverage >= 0.80, (
        f"Android Platform section covers {coverage:.0%} of registry "
        f"({len(covered)}/{len(keys)} keys); wave-2 DoD requires >= 80%. "
        f"Uncovered: {sorted(set(keys) - set(covered))}"
    )
