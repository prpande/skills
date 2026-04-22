import hashlib, json
from renderer import render_flow_mapping, DO_NOT_EDIT_BANNER

SAMPLE = {
    "figma_url": "https://figma.com/x",
    "locator_method": "nav-graph",
    "confidence": "high",
    "refused_reason": None,
    "mappings": [
        {"figma_frame_id": "F1", "android_destination": "AppointmentDetailsFragment", "score": 3}
    ]
}

def test_renders_banner_and_hash():
    md = render_flow_mapping(SAMPLE)
    assert DO_NOT_EDIT_BANNER in md
    expected_sha = hashlib.sha256(
        json.dumps(SAMPLE, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert f"sha256: {expected_sha}" in md

def test_refused_reason_surfaces():
    refused = {**SAMPLE, "locator_method": "refused", "refused_reason": "default-named frames"}
    md = render_flow_mapping(refused)
    assert "REFUSED" in md
    assert "default-named frames" in md

def test_mapping_row_rendered():
    md = render_flow_mapping(SAMPLE)
    assert "F1" in md and "AppointmentDetailsFragment" in md
