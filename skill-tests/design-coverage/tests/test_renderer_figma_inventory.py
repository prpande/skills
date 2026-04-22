from renderer import render_figma_inventory

def test_renders_frames_and_crosscheck():
    data = {
        "items": [{"id": "f1.title", "kind": "field", "title": "Title", "parent_id": "f1",
                   "source": {"surface": "compose", "file": "figma", "line": None, "symbol": None},
                   "hotspot": None, "confidence": "high", "notes": None}],
        "frames": [{"frame_id": "f1", "screenshot_cross_check": "disagreed", "error": None}]
    }
    md = render_figma_inventory(data)
    assert "disagreed" in md and "f1" in md


def test_figma_items_surface_modes_and_ambiguity():
    data = {
        "items": [
            {"id": "f1.screen", "kind": "screen", "title": "Appt Details",
             "parent_id": None,
             "source": {"surface": "compose", "file": "figma", "line": None, "symbol": None},
             "hotspot": None, "confidence": "high", "notes": None,
             "modes": ["light", "dark"]},
            {"id": "f1.cell.dynamic", "kind": "state", "title": "Apply Payment cell",
             "parent_id": "f1.screen",
             "source": {"surface": "compose", "file": "figma", "line": None, "symbol": None},
             "hotspot": None, "confidence": "low", "notes": None,
             "ambiguous": True,
             "ambiguity_reason": "only visible in Haptics demo"},
        ],
        "frames": [{"frame_id": "f1", "screenshot_cross_check": "agreed", "error": None}],
    }
    md = render_figma_inventory(data)
    assert "modes: light, dark" in md
    assert "⚠ ambiguous: only visible in Haptics demo" in md
