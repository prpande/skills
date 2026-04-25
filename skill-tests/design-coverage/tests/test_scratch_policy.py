"""Wave 2 #11 — scratch-file policy enforcement.

The orchestrator must:
  1. Create <run_dir>/.gitignore containing `.scratch/` on first stage.
  2. Create <run_dir>/.scratch/ as a real directory.
  3. Never write `_*.json` (other than `_severity_lookup_misses.json`)
     or `_*.py` at the run-dir top level.

This test simulates the orchestrator's first-stage steps directly and
asserts the resulting layout matches the policy. The actual orchestrator
runs from SKILL.md prose, so the test is a contract check on the
documented commands rather than a unit test of orchestrator code.
"""
from __future__ import annotations
import re
from pathlib import Path


def _orchestrator_first_stage_init(run_dir: Path) -> None:
    """Mirror the SKILL.md scratch-files setup commands."""
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / ".gitignore").write_text(".scratch/\n", encoding="utf-8")
    (run_dir / ".scratch").mkdir(exist_ok=True)


def test_run_dir_has_gitignore_with_scratch_entry(tmp_path: Path) -> None:
    run = tmp_path / "2026-04-25-test"
    _orchestrator_first_stage_init(run)
    assert (run / ".gitignore").exists()
    assert ".scratch/" in (run / ".gitignore").read_text()


def test_scratch_dir_exists(tmp_path: Path) -> None:
    run = tmp_path / "2026-04-25-test"
    _orchestrator_first_stage_init(run)
    assert (run / ".scratch").is_dir()


def test_only_severity_lookup_misses_underscore_file_at_top_level(
    tmp_path: Path,
) -> None:
    """The whitelisted underscore-prefixed file is _severity_lookup_misses.json
    (wave 1). Any other _*.json or _*.py at run-dir top is a policy violation.
    """
    run = tmp_path / "2026-04-25-test"
    _orchestrator_first_stage_init(run)

    # Simulate a wave-1-style miss-buffer write: that one IS allowed.
    (run / "_severity_lookup_misses.json").write_text("[]\n", encoding="utf-8")
    # Simulate stage artifacts (these are NOT _*-prefixed and ARE allowed).
    (run / "01-flow-mapping.json").write_text("{}\n", encoding="utf-8")
    (run / "02-code-inventory.md").write_text("ok\n", encoding="utf-8")

    forbidden = []
    for entry in run.iterdir():
        if not entry.is_file():
            continue
        name = entry.name
        if name == "_severity_lookup_misses.json":
            continue
        if re.fullmatch(r"_[A-Za-z0-9_-]+\.(json|py)", name):
            forbidden.append(name)

    assert forbidden == [], (
        f"scratch policy violation: forbidden underscore-prefixed files at "
        f"run-dir top level: {forbidden}"
    )


def test_violation_detected_when_stage_writes_underscore_prefixed_file(
    tmp_path: Path,
) -> None:
    """Negative test: the policy check above must actually catch a forbidden
    write so a future regression has a guard.
    """
    run = tmp_path / "2026-04-25-test"
    _orchestrator_first_stage_init(run)
    (run / "_in_scope_with_names.json").write_text("[]\n", encoding="utf-8")

    forbidden = []
    for entry in run.iterdir():
        if not entry.is_file():
            continue
        name = entry.name
        if name == "_severity_lookup_misses.json":
            continue
        if re.fullmatch(r"_[A-Za-z0-9_-]+\.(json|py)", name):
            forbidden.append(name)

    assert "_in_scope_with_names.json" in forbidden
