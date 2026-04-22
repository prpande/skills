from renderer import render_comparison

def test_renders_all_statuses():
    data = {"rows": [
        {"pass": "flow", "status": "present", "severity": "info", "code_ref": "A", "figma_ref": "F1", "evidence": "matched"},
        {"pass": "flow", "status": "missing", "severity": "error", "code_ref": "B", "figma_ref": None, "evidence": "not in figma"},
        {"pass": "flow", "status": "new-in-figma", "severity": "info", "code_ref": None, "figma_ref": "F2", "evidence": "new"},
        {"pass": "screen", "status": "restructured", "severity": "warn", "code_ref": "C", "figma_ref": "F3", "evidence": "moved"},
    ]}
    md = render_comparison(data)
    for s in ["present", "missing", "new-in-figma", "restructured"]:
        assert s in md
