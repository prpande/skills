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


def test_summary_bullets_carry_severity_emoji():
    """Polish #7 — each summary bullet is prefixed with a severity emoji
    so the reader can scan the list visually before reading any text."""
    data = {
        "summary": [
            {"severity": "error", "message": "missing resource picker", "screen": "B"},
            {"severity": "warn", "message": "toolbar collapse", "screen": "C"},
            {"severity": "info", "message": "layout polish", "screen": "A"},
        ],
        "matrix": [],
    }
    md = render_report(data)
    # Emoji appears before the [SEVERITY] tag on each bullet
    assert "- 🔴 [ERROR]" in md
    assert "- 🟠 [WARN]" in md
    assert "- ℹ️ [INFO]" in md


def test_matrix_rows_carry_status_emoji():
    """Polish #7 — each matrix row prefixes its status cell with an emoji
    matching the severity convention used by the narrative render."""
    data = {
        "summary": [],
        "matrix": [
            {"figma_frame": "F1", "android_screen": "A", "status": "present"},
            {"figma_frame": "F2", "android_screen": None, "status": "new-in-figma"},
            {"figma_frame": "F3", "android_screen": "B", "status": "restructured"},
            {"figma_frame": "F4", "android_screen": "C", "status": "missing"},
        ],
    }
    md = render_report(data)
    assert "✅ present" in md
    assert "⚪ new-in-figma" in md
    assert "🟡 restructured" in md
    assert "🔴 missing" in md
