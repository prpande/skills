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
