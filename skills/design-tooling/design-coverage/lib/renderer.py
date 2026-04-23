import hashlib
import json
from typing import Any, Dict

DO_NOT_EDIT_BANNER = "<!-- DO NOT EDIT — regenerated from JSON source of truth -->"

def _header(data: Dict[str, Any], title: str) -> str:
    sha = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return f"{DO_NOT_EDIT_BANNER}\n<!-- sha256: {sha} -->\n\n# {title}\n"

def render_flow_mapping(data: Dict[str, Any]) -> str:
    lines = [_header(data, "Flow Mapping")]
    if data.get("locator_method") == "refused":
        lines.append(f"\n**REFUSED:** {data.get('refused_reason') or 'unknown reason'}\n")
    lines.append(f"\n- Figma URL: {data.get('figma_url', '')}")
    lines.append(f"- Locator: {data.get('locator_method')}")
    lines.append(f"- Confidence: {data.get('confidence')}\n")
    lines.append("## Mappings\n")
    for m in data.get("mappings", []):
        lines.append(f"- `{m['figma_frame_id']}` → `{m['android_destination']}` (score {m['score']})")
    return "\n".join(lines) + "\n"

def render_code_inventory(data: Dict[str, Any]) -> str:
    lines = [_header(data, "Code Inventory")]
    items = data.get("items", [])
    by_id = {it["id"]: it for it in items}
    roots = [it for it in items if it.get("parent_id") is None]
    orphans = [it for it in items if it.get("parent_id") is not None and it["parent_id"] not in by_id]

    lines.append("\n## Items\n")
    rendered_ids: set = set()

    def _item_suffix(node: Dict[str, Any]) -> str:
        """Trailing annotations: modes list, ambiguity marker."""
        parts: list[str] = []
        modes = node.get("modes") or []
        if modes:
            parts.append(f"modes: {', '.join(modes)}")
        if node.get("ambiguous"):
            reason = node.get("ambiguity_reason")
            parts.append(f"⚠ ambiguous{f': {reason}' if reason else ''}")
        return f" ({'; '.join(parts)})" if parts else ""

    def _walk(node, depth, seen=None):
        seen = seen if seen is not None else set()
        if node["id"] in seen:
            return [f"{'  ' * depth}- ⚠ cycle at `{node['id']}`"]
        seen = seen | {node["id"]}
        rendered_ids.add(node["id"])
        out = [f"{'  ' * depth}- **{node['kind']}** `{node['id']}` — {node['title']}{_item_suffix(node)}"]
        for child in items:
            if child.get("parent_id") == node["id"]:
                out.extend(_walk(child, depth + 1, seen))
        return out
    for r in roots:
        lines.extend(_walk(r, 0))
    # Render any items not reachable from roots (e.g. nodes in a cycle) so they aren't silently dropped.
    for it in items:
        if it["id"] not in rendered_ids and it.get("parent_id") in by_id:
            lines.extend(_walk(it, 0))

    lines.append("\n## Orphaned items\n")
    if orphans:
        for o in orphans:
            lines.append(f"- `{o['id']}` ({o['kind']}) — {o['title']} — parent `{o['parent_id']}` not found")
    else:
        lines.append("_None_")

    lines.append("\n## Unwalked destinations\n")
    for u in data.get("unwalked_destinations", []):
        lines.append(f"- `{u['nav_source']}` → `{u['target']}`: {u['reason']}")
    return "\n".join(lines) + "\n"

def render_clarifications(data: Dict[str, Any]) -> str:
    lines = [_header(data, "Clarifications")]
    resolved = data.get("resolved", [])
    if not resolved:
        lines.append("\n_No hotspots required clarification._\n")
        return "\n".join(lines) + "\n"
    lines.append("\n## Resolved\n")
    for r in resolved:
        lines.append(f"- `{r['hotspot_id']}` ({r['resolved_at']}): {r['answer']}")
    return "\n".join(lines) + "\n"

def render_figma_inventory(data: Dict[str, Any]) -> str:
    lines = [_header(data, "Figma Inventory")]
    lines.append("\n## Frames\n")
    for f in data.get("frames", []):
        err = f" — error: {f['error']}" if f.get("error") else ""
        lines.append(f"- `{f['frame_id']}` — cross-check: **{f['screenshot_cross_check']}**{err}")
    lines.append("\n## Items\n")
    for it in data.get("items", []):
        annotations: list[str] = []
        modes = it.get("modes") or []
        if modes:
            annotations.append(f"modes: {', '.join(modes)}")
        if it.get("ambiguous"):
            reason = it.get("ambiguity_reason")
            annotations.append(f"⚠ ambiguous{f': {reason}' if reason else ''}")
        suffix = f" ({'; '.join(annotations)})" if annotations else ""
        lines.append(f"- `{it['id']}` ({it['kind']}) — {it['title']}{suffix}")
    return "\n".join(lines) + "\n"

def render_comparison(data: Dict[str, Any]) -> str:
    lines = [_header(data, "Comparison")]
    for row in data.get("rows", []):
        lines.append(
            f"- **{row['status']}** [{row['severity']}] pass={row['pass']} "
            f"code={row.get('code_ref')} figma={row.get('figma_ref')} — {row.get('evidence') or ''}"
        )
    return "\n".join(lines) + "\n"

_SEVERITY_EMOJI = {"error": "🔴", "warn": "🟠", "info": "ℹ️"}
_STATUS_EMOJI = {
    "missing": "🔴",
    "restructured": "🟡",
    "new-in-figma": "⚪",
    "present": "✅",
}


def render_report(data: Dict[str, Any]) -> str:
    lines = [_header(data, "Design Coverage Report")]
    severity_order = {"error": 0, "warn": 1, "info": 2}
    summary = sorted(data.get("summary", []), key=lambda s: severity_order.get(s["severity"], 99))
    lines.append("\n## Summary\n")
    for s in summary:
        emoji = _SEVERITY_EMOJI.get(s["severity"], "")
        screen = f" ({s['screen']})" if s.get("screen") else ""
        prefix = f"{emoji} " if emoji else ""
        lines.append(f"- {prefix}[{s['severity'].upper()}]{screen} {s['message']}")
    lines.append("\n## Coverage Matrix\n")
    # Column header is platform-neutral; the JSON key stays `android_screen`
    # for schema compatibility (see spec "Known limitations").
    lines.append("| Figma frame | Code screen | Status |")
    lines.append("|---|---|---|")
    for m in data.get("matrix", []):
        status = m["status"]
        status_emoji = _STATUS_EMOJI.get(status, "")
        status_cell = f"{status_emoji} {status}" if status_emoji else status
        lines.append(f"| {m['figma_frame']} | {m.get('android_screen') or '—'} | {status_cell} |")
    return "\n".join(lines) + "\n"
