from renderer import render_report

def test_summary_ordered_error_first():
    data = {
        "summary": [
            {"severity": "info", "message": "ok", "screen": "A"},
            {"severity": "error", "message": "missing", "screen": "B"},
            {"severity": "warn", "message": "restructured", "screen": "C"},
        ],
        "matrix": [
            {"figma_frame": "F1", "android_screen": "A", "status": "present"}
        ]
    }
    md = render_report(data)
    err_idx = md.index("missing")
    warn_idx = md.index("restructured")
    info_idx = md.index("ok")
    assert err_idx < warn_idx < info_idx


def test_matrix_header_is_platform_neutral():
    """Matrix column header must read 'Code screen', not 'Android screen',
    to stay platform-neutral for iOS / agnostic runs. JSON key stays
    android_screen per schema."""
    data = {
        "summary": [],
        "matrix": [{"figma_frame": "F1", "android_screen": "HomeScreen",
                    "status": "present"}],
    }
    md = render_report(data)
    assert "| Figma frame | Code screen | Status |" in md
    assert "Android screen" not in md
