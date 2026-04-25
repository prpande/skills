"""Verify skill_root.get_skill_root() finds SKILL.md by walking up from __file__.

This module is the foundation for skill-relative path resolution; everything
else in lib/ that needs to load schemas/ depends on it. The test covers both
the real skill location AND a synthetic tmp-path layout to ensure portability.
"""
from pathlib import Path
import pytest


def test_real_skill_root_contains_skill_md():
    """When called from the real lib/, the resolved root contains SKILL.md."""
    from skill_root import get_skill_root
    root = get_skill_root()
    assert (root / "SKILL.md").exists(), f"SKILL.md not found in {root}"


def test_real_skill_root_contains_schemas_dir():
    """The resolved root has the sibling schemas/ directory we'll need."""
    from skill_root import get_skill_root
    root = get_skill_root()
    assert (root / "schemas").is_dir()


def test_get_skill_root_raises_when_skill_md_absent(tmp_path, monkeypatch):
    """If invoked from a directory tree with no SKILL.md ancestor, raise loudly."""
    import sys
    import importlib

    fake_lib = tmp_path / "fake" / "lib"
    fake_lib.mkdir(parents=True)
    fake_module = fake_lib / "skill_root_clone.py"
    import skill_root as real_module
    fake_module.write_text(Path(real_module.__file__).read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.syspath_prepend(str(fake_lib))
    if "skill_root_clone" in sys.modules:
        del sys.modules["skill_root_clone"]
    clone = importlib.import_module("skill_root_clone")

    with pytest.raises(RuntimeError, match="SKILL.md"):
        clone.get_skill_root()
