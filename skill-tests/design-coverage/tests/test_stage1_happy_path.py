import json
import re
import os
from pathlib import Path
from validator import Validator

ROOT = Path(__file__).parents[1]
SCHEMAS = Path(os.environ["DESIGN_COVERAGE_SKILL_ROOT"]) / "schemas"


def _tokens(s: str) -> set:
    # split CamelCase and non-alnum into lowercase tokens
    parts = re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z0-9]+|[A-Z]+", s)
    return {p.lower() for p in parts if p}


def _score(frame_name: str, candidate_tokens: set) -> int:
    return len(_tokens(frame_name) & candidate_tokens)


def stage1_nav_graph_match(figma_url: str, frames, destinations):
    mappings = []
    for f in frames:
        best = None
        best_score = 0
        for d in destinations:
            dest_tokens = _tokens(d["label"]) | _tokens(d["class_or_composable"])
            # exclude generic "screen"/"fragment" suffix tokens from contributing
            dest_tokens -= {"screen", "fragment"}
            s = _score(f["name"], dest_tokens)
            if s > best_score:
                best, best_score = d, s
        if best is not None and best_score > 0:
            mappings.append({
                "figma_frame_id": f["id"],
                "android_destination": best["id"],
                "score": best_score,
            })
    return {
        "figma_url": figma_url,
        "locator_method": "nav-graph",
        "confidence": "high",
        "refused_reason": None,
        "mappings": mappings,
    }


def stage1_name_search_fallback(figma_url: str, frames, code_anchors):
    mappings = []
    for f in frames:
        best = None
        best_score = 0
        for a in code_anchors:
            anchor_tokens = _tokens(a["symbol"]) - {"screen", "fragment"}
            s = _score(f["name"], anchor_tokens)
            if s > best_score:
                best, best_score = a, s
        if best is not None and best_score > 0:
            mappings.append({
                "figma_frame_id": f["id"],
                "android_destination": best["symbol"],
                "score": best_score,
            })
    return {
        "figma_url": figma_url,
        "locator_method": "name-search",
        "confidence": "medium",
        "refused_reason": None,
        "mappings": mappings,
    }


def test_nav_graph_match_returns_high_confidence():
    fx = ROOT / "fixtures" / "stage-01" / "nav-graph-match"
    frames = json.loads((fx / "input" / "figma_frames.json").read_text())["frames"]
    destinations = json.loads((fx / "input" / "nav_destinations.json").read_text())
    expected = json.loads((fx / "expected" / "flow_mapping.json").read_text())
    produced = stage1_nav_graph_match("https://figma.com/example", frames, destinations)
    assert produced == expected
    schema = json.loads((SCHEMAS / "flow_mapping.json").read_text())
    Validator(SCHEMAS).validate(produced, schema)


def test_name_search_fallback_returns_medium_confidence():
    fx = ROOT / "fixtures" / "stage-01" / "name-search-fallback"
    frames = json.loads((fx / "input" / "figma_frames.json").read_text())["frames"]
    anchors = json.loads((fx / "input" / "code_anchors.json").read_text())
    expected = json.loads((fx / "expected" / "flow_mapping.json").read_text())
    produced = stage1_name_search_fallback("https://figma.com/example", frames, anchors)
    assert produced == expected
    schema = json.loads((SCHEMAS / "flow_mapping.json").read_text())
    Validator(SCHEMAS).validate(produced, schema)
