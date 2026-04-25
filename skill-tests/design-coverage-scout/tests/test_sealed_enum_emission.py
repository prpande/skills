"""Wave 2 #10c — scout stage 02 walks get_sealed_enum_pattern_keys() and
emits per-key grep patterns into hint-draft.json.
"""
from __future__ import annotations
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
STAGE_MD = (
    REPO / "skills" / "design-tooling" / "design-coverage-scout"
    / "stages" / "02-pattern-extraction.md"
)


def test_stage_md_references_sealed_enum_index() -> None:
    text = STAGE_MD.read_text(encoding="utf-8")
    assert "get_sealed_enum_pattern_keys" in text, (
        "Scout stage 02 must explicitly reference the schema-derived registry "
        "function so adding a new x-platform-pattern enum value flows through "
        "to the scout without a code change here."
    )


def test_stage_md_has_platform_sections_for_ios_and_android() -> None:
    text = STAGE_MD.read_text(encoding="utf-8")
    assert re.search(r"^#### iOS\b", text, re.MULTILINE), (
        "Scout stage 02 must document iOS platform-truth heuristics under a "
        "`#### iOS` section so new repos on iOS get a useful baseline."
    )
    assert re.search(r"^#### Android\b", text, re.MULTILINE), (
        "Scout stage 02 must document Android platform-truth heuristics under "
        "a `#### Android` section."
    )


def test_stage_md_documents_extension_path_for_new_platforms() -> None:
    text = STAGE_MD.read_text(encoding="utf-8")
    assert "Adding a new platform" in text or "new platform section" in text, (
        "Scout stage 02 must document how to add a new platform section."
    )


def test_stage_md_documents_minimum_coverage_threshold() -> None:
    text = STAGE_MD.read_text(encoding="utf-8")
    assert "80%" in text or "0.8" in text, (
        "Wave-2 DoD requires sealed_enum_patterns coverage >= 80% of derived "
        "keys; the stage MD must surface that threshold."
    )
