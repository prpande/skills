import json
from pathlib import Path
from skill_io import atomic_write_json, read_json, new_run_dir, record_retry, get_retry_count

def test_atomic_write_roundtrip(tmp_path):
    target = tmp_path / "a.json"
    atomic_write_json(target, {"x": 1})
    assert json.loads(target.read_text()) == {"x": 1}

def test_atomic_write_no_tmp_left_behind(tmp_path):
    target = tmp_path / "a.json"
    atomic_write_json(target, {"x": 1})
    assert not (tmp_path / "a.json.tmp").exists()

def test_read_json_missing_returns_none(tmp_path):
    assert read_json(tmp_path / "missing.json") is None

def test_new_run_dir_creates_dated_slug_folder(tmp_path):
    d = new_run_dir(tmp_path, "2026-04-14", "appointment-details")
    assert d.is_dir()
    assert d.name == "2026-04-14-appointment-details"

def test_retry_tracker_increments(tmp_path):
    record_retry(tmp_path, stage="2")
    record_retry(tmp_path, stage="2")
    assert get_retry_count(tmp_path, "2") == 2


def test_atomic_write_read_roundtrip_preserves_non_ascii(tmp_path):
    """Figma frame names can be non-ASCII (Japanese, emoji, accents).

    Writer encodes UTF-8 explicitly; reader must decode UTF-8 explicitly or
    Windows falls back to cp1252 and raises UnicodeDecodeError.
    """
    target = tmp_path / "inv.json"
    payload = {
        "frame": "予約詳細",
        "label": "Café — Menu 🍕",
        "note": "Accents: naïve, résumé, façade",
    }
    atomic_write_json(target, payload)
    loaded = read_json(target)
    assert loaded == payload
