"""Wave 2 #10c smoke — scout stage 02's iOS Platform section's grep
patterns find at least one match in a tiny iOS-shaped fixture for >= 80%
of the schema-derived registry keys.

The scout itself runs in a subagent; we cannot dispatch one inside a
pytest run. Instead, this smoke test:

  1. Loads the iOS Platform section from stages/02-pattern-extraction.md.
  2. For each registry key, parses the listed grep regexes out of the MD.
  3. Runs each regex against the fixture tree (*.swift files only).
  4. Asserts >= 80% of registry keys have at least one fixture match.

This is the unit-testable proxy for "scout produces a useful draft on a
fresh iOS repo": if the patterns in the MD don't actually match the
fixture, no scout subagent following them will produce a useful draft.
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

FIXTURE = REPO / "skill-tests" / "fixtures" / "scout-ios"

# Keys explicitly excluded from the iOS tally — each with a reason comment.
N_A_ON_IOS = {
    # Android-specific resource qualifiers; no iOS analogue.
    "inventory_item.hotspot.type.config-qualifier",
    # Android ViewPager2 tab mechanism; no iOS analogue.
    "inventory_item.hotspot.type.viewpager-tab",
    # Detected by post-walk process diff, not a grep pattern;
    # the iOS section has no backtick-quoted regex for this key.
    "code_inventory.unwalked_destinations.reason.unresolved-class",
    # Storyboard <segue> tags live in .storyboard/.xib XML, not .swift;
    # the iOS section's pattern can't match in a .swift-only search.
    "inventory_item.source.surface.nav-xml",
}


def _ios_section_text() -> str:
    text = SCOUT_STAGE_MD.read_text(encoding="utf-8")
    m = re.search(r"^#### iOS\b(.*?)(?=^#### |^### |\Z)",
                  text, re.MULTILINE | re.DOTALL)
    assert m, "iOS Platform section not found in scout stage 02 MD"
    return m.group(1)


def _patterns_for_key(ios_section: str, key: str) -> list[str]:
    """Pull the backtick-quoted regex patterns from the bullet for `key`."""
    line_re = re.compile(
        rf"^- \*\*`{re.escape(key)}`\*\*:(.*?)(?=^- \*\*|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = line_re.search(ios_section)
    if not m:
        return []
    body = m.group(1)
    return [
        m2.group(1).replace(r"\\", "\\")
        for m2 in re.finditer(r"`([^`]+)`", body)
    ]


def _matches_any(pattern: str, files: list[Path]) -> bool:
    try:
        rx = re.compile(pattern)
    except re.error:
        return False
    return any(rx.search(f.read_text(encoding="utf-8", errors="ignore"))
               for f in files)


def test_ios_patterns_cover_at_least_80_percent_of_registry() -> None:
    keys = [k for k in get_sealed_enum_pattern_keys() if k not in N_A_ON_IOS]
    ios_section = _ios_section_text()
    swift_files = list(FIXTURE.rglob("*.swift"))
    assert swift_files, "fixture has no .swift files"

    covered = []
    for key in keys:
        pats = _patterns_for_key(ios_section, key)
        if any(_matches_any(p, swift_files) for p in pats):
            covered.append(key)

    coverage = len(covered) / len(keys)
    assert coverage >= 0.80, (
        f"iOS Platform section covers {coverage:.0%} of registry "
        f"({len(covered)}/{len(keys)} keys); wave-2 DoD requires >= 80%. "
        f"Uncovered: {sorted(set(keys) - set(covered))}"
    )
