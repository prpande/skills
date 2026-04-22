from renderer import render_code_inventory

INV = {
    "items": [
        {"id": "scr", "kind": "screen", "title": "Appt", "parent_id": None,
         "source": {"surface": "compose", "file": "a.kt", "line": 10, "symbol": "ApptScreen"},
         "hotspot": None, "confidence": "high", "notes": None},
        {"id": "btn", "kind": "action", "title": "Save", "parent_id": "scr",
         "source": {"surface": "compose", "file": "a.kt", "line": 20, "symbol": "SaveBtn"},
         "hotspot": None, "confidence": "high", "notes": None},
        {"id": "orphan", "kind": "field", "title": "Stray", "parent_id": "missing-parent",
         "source": {"surface": "xml", "file": "b.xml", "line": None, "symbol": "stray"},
         "hotspot": None, "confidence": "low", "notes": None},
    ],
    "unwalked_destinations": [
        {"nav_source": "nav_main.xml", "target": "HiddenFragment", "reason": "class not found"}
    ]
}

def test_hierarchy_renders_child_under_parent():
    md = render_code_inventory(INV)
    assert "Appt" in md and "Save" in md

def test_orphaned_items_section_exists_and_contains_orphan():
    md = render_code_inventory(INV)
    assert "## Orphaned items" in md
    assert "Stray" in md
    assert any(
        "Stray" in line and "parent `missing-parent` not found" in line
        for line in md.splitlines()
    )

def test_unwalked_destinations_section():
    md = render_code_inventory(INV)
    assert "Unwalked destinations" in md
    assert "HiddenFragment" in md

def test_cycle_does_not_recurse():
    cyclic = {
        "items": [
            {"id": "a", "kind": "screen", "title": "A", "parent_id": "b",
             "source": {"surface": "compose", "file": "a.kt", "line": 1, "symbol": "A"},
             "hotspot": None, "confidence": "high", "notes": None},
            {"id": "b", "kind": "screen", "title": "B", "parent_id": "a",
             "source": {"surface": "compose", "file": "b.kt", "line": 1, "symbol": "B"},
             "hotspot": None, "confidence": "high", "notes": None},
        ],
        "unwalked_destinations": []
    }
    md = render_code_inventory(cyclic)
    assert "cycle" in md
