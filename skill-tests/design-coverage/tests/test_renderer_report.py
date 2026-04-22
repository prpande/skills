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
