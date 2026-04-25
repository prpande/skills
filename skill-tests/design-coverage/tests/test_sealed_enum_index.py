"""Wave 1 — verify get_sealed_enum_pattern_keys() derives the registry from
schemas/, NOT from a hand-coded list. The schemas are the existing source of
truth for what enums exist; a hand-maintained registry would drift on every
schema change.
"""
import json
from pathlib import Path

import pytest


def test_returns_a_sorted_list_of_strings():
    from sealed_enum_index import get_sealed_enum_pattern_keys
    keys = get_sealed_enum_pattern_keys()
    assert isinstance(keys, list)
    assert keys == sorted(keys)
    assert all(isinstance(k, str) for k in keys)
    assert len(keys) >= 9  # hotspot.type alone has 9 values


def test_includes_every_hotspot_type_value():
    from sealed_enum_index import get_sealed_enum_pattern_keys
    keys = set(get_sealed_enum_pattern_keys())
    expected = {
        "inventory_item.hotspot.type.feature-flag",
        "inventory_item.hotspot.type.permission",
        "inventory_item.hotspot.type.server-driven",
        "inventory_item.hotspot.type.config-qualifier",
        "inventory_item.hotspot.type.form-factor",
        "inventory_item.hotspot.type.process-death",
        "inventory_item.hotspot.type.view-type",
        "inventory_item.hotspot.type.viewpager-tab",
        "inventory_item.hotspot.type.sheet-dialog",
    }
    missing = expected - keys
    assert not missing, f"missing hotspot.type keys: {sorted(missing)}"


def test_includes_inventory_item_kind_values():
    from sealed_enum_index import get_sealed_enum_pattern_keys
    keys = set(get_sealed_enum_pattern_keys())
    expected = {
        "inventory_item.kind.screen",
        "inventory_item.kind.state",
        "inventory_item.kind.action",
        "inventory_item.kind.field",
    }
    assert expected <= keys


def test_includes_surface_values():
    from sealed_enum_index import get_sealed_enum_pattern_keys
    keys = set(get_sealed_enum_pattern_keys())
    expected = {
        "inventory_item.source.surface.compose",
        "inventory_item.source.surface.xml",
        "inventory_item.source.surface.hybrid",
        "inventory_item.source.surface.nav-xml",
        "inventory_item.source.surface.nav-compose",
    }
    assert expected <= keys


def test_includes_unwalked_reason_values():
    from sealed_enum_index import get_sealed_enum_pattern_keys
    keys = set(get_sealed_enum_pattern_keys())
    expected = {
        "code_inventory.unwalked_destinations.reason.adapter-hosted",
        "code_inventory.unwalked_destinations.reason.external-module",
        "code_inventory.unwalked_destinations.reason.swiftui-bridge",
        "code_inventory.unwalked_destinations.reason.dynamic-identifier",
        "code_inventory.unwalked_destinations.reason.platform-bridge",
        "code_inventory.unwalked_destinations.reason.unresolved-class",
    }
    assert expected <= keys


def test_excludes_universal_enums():
    """Severity, status, confidence, etc. are universal — they must NOT carry
    x-platform-pattern, and therefore must NOT appear in the registry."""
    from sealed_enum_index import get_sealed_enum_pattern_keys
    keys = " ".join(get_sealed_enum_pattern_keys())
    for forbidden in ("severity", "status", "screenshot_cross_check", "confidence", "locator_method"):
        assert forbidden not in keys, f"{forbidden} should not appear in the registry"


def test_dynamically_picks_up_new_x_platform_pattern_value(tmp_path, monkeypatch):
    """Adding a new x-platform-pattern: true enum value to a schema makes the
    registry surface it without any code change in sealed_enum_index.py."""
    fake_skill_root = tmp_path / "fake-skill"
    (fake_skill_root / "schemas").mkdir(parents=True)
    (fake_skill_root / "SKILL.md").write_text("---\nname: fake\n---\n")
    schema = {
        "$id": "fake.json",
        "type": "object",
        "properties": {
            "novel_enum": {
                "type": "string",
                "x-platform-pattern": True,
                "enum": ["alpha", "beta"]
            }
        }
    }
    (fake_skill_root / "schemas" / "fake.json").write_text(json.dumps(schema))

    import skill_root as real_skill_root_mod
    monkeypatch.setattr(real_skill_root_mod, "get_skill_root", lambda: fake_skill_root)
    # No importlib.reload needed — sealed_enum_index uses attribute-level access
    # (`skill_root.get_skill_root()`) so the monkeypatch is live without rebinding.
    import sealed_enum_index

    keys = sealed_enum_index.get_sealed_enum_pattern_keys()
    assert "fake.novel_enum.alpha" in keys
    assert "fake.novel_enum.beta" in keys


def test_sealed_enum_index_does_not_leak_monkeypatch_after_test():
    """Regression: importlib.reload + `from skill_root import get_skill_root`
    bound a stale lambda to sealed_enum_index for the rest of the session.
    Switching to `import skill_root` + attribute access fixes it. After the
    monkeypatch test above reverts, this test must see the real schemas."""
    from sealed_enum_index import get_sealed_enum_pattern_keys
    keys = get_sealed_enum_pattern_keys()
    # Real schemas have inventory_item.hotspot.type.* keys; the fake schema
    # used in the prior test only declared fake.novel_enum.*.
    assert any(k.startswith("inventory_item.hotspot.type.") for k in keys), (
        "sealed_enum_index appears to be reading from fake schemas — module state "
        "leaked across tests"
    )
    assert not any(k.startswith("fake.") for k in keys), (
        "fake schema keys should not appear once the prior test's monkeypatch "
        "has reverted"
    )
