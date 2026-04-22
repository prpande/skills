"""Lock in the durability rule in scout stage-2.

Scout runs against a real repo and can observe instance counts (e.g.,
'329 UIViewController hits across 143 files'). Those counts drift as the
repo evolves, which turns a checked-in hint file stale. Stage-2 must
instruct the LLM to describe patterns, not counts, so the hint remains
durable across many future runs.

If someone removes or weakens the durability rule in stage-2, this test
should catch it. This is a text-level guard — no LLM is in the loop.
"""
from __future__ import annotations
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[3]
STAGE_02 = (
    REPO
    / "skills"
    / "design-tooling"
    / "design-coverage-scout"
    / "stages"
    / "02-pattern-extraction.md"
)


def _text() -> str:
    return STAGE_02.read_text(encoding="utf-8")


def test_stage2_exists() -> None:
    assert STAGE_02.exists(), f"missing stage-2 prompt at {STAGE_02}"


def test_stage2_has_durability_section() -> None:
    assert "Durability rule" in _text(), (
        "stage-2 prompt must carry a 'Durability rule' section that forbids "
        "point-in-time instance counts in generated hints"
    )


def test_stage2_forbids_instance_counts() -> None:
    t = _text()
    assert "Describe patterns, not instance" in t, (
        "stage-2 prompt must state 'Describe patterns, not instance counts' "
        "(or equivalent phrasing) — forbidding tallies like '329 hits'"
    )


def test_stage2_calls_out_allowed_vs_not_allowed() -> None:
    t = _text()
    assert "**Allowed**" in t, "stage-2 prompt should enumerate allowed patterns"
    assert "**Not allowed**" in t, "stage-2 prompt should enumerate disallowed patterns"
