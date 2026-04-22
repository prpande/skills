from renderer import render_clarifications

def test_empty_list():
    md = render_clarifications({"resolved": []})
    assert "No hotspots" in md

def test_resolved_rendered():
    md = render_clarifications({"resolved": [
        {"hotspot_id": "h1", "answer": "phone only", "resolved_at": "2026-04-14T12:00:00Z"}
    ]})
    assert "h1" in md and "phone only" in md
