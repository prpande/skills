"""Render a hint_draft.json dict into a hint .md file body.

Wave 2 #10c — the .md must carry the new wave-2 frontmatter fields so the
runtime hint loader (lib/hint_frontmatter.py in design-coverage) can read
them. Sanitization of section bodies still happens in stage 03's MD via
lib/sanitize.py — this module is concerned with the frontmatter shape only.
"""
from __future__ import annotations

from typing import Any


def render_draft_to_md(
    draft: dict[str, Any],
    sanitized_sections: dict[str, str] | None = None,
) -> str:
    """Render the draft as a full hint .md (frontmatter + section bodies).

    `sanitized_sections` overrides the raw `draft["sections"]` strings if
    provided (stage 03 passes them through `sanitize_section` first).
    """
    def _yaml_str(s: str) -> str:
        """Emit s as a double-quoted YAML scalar with minimal escaping."""
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

    fm_lines = ["---", f"name: {draft['name']}", "detect:"]
    for d in draft["detect"]:
        fm_lines.append(f'  - "{d}"')
    fm_lines.append(f"description: {_yaml_str(draft['description'])}")
    fm_lines.append(f"confidence: {draft['confidence']}")

    if "multi_anchor_suffixes" in draft and draft["multi_anchor_suffixes"]:
        fm_lines.append("multi_anchor_suffixes:")
        for s in draft["multi_anchor_suffixes"]:
            fm_lines.append(f'  - "{s}"')
    if "default_in_scope_hops" in draft:
        fm_lines.append(f"default_in_scope_hops: {draft['default_in_scope_hops']}")
    if "hotspot_question_overrides" in draft:
        overrides = draft["hotspot_question_overrides"]
        if overrides:
            fm_lines.append("hotspot_question_overrides:")
            for k, v in sorted(overrides.items()):
                fm_lines.append(f'  {k}: "{v}"')
        else:
            fm_lines.append("hotspot_question_overrides: {}")
    if "sealed_enum_patterns" in draft and draft["sealed_enum_patterns"]:
        fm_lines.append("sealed_enum_patterns:")
        for key in sorted(draft["sealed_enum_patterns"].keys()):
            body = draft["sealed_enum_patterns"][key]
            fm_lines.append(f"  {key}:")
            fm_lines.append("    grep:")
            for g in body.get("grep", []):
                escaped = g.replace("\\", "\\\\").replace('"', '\\"')
                fm_lines.append(f'      - "{escaped}"')
            desc = body.get("description")
            if desc is None:
                fm_lines.append("    description: null")
            else:
                fm_lines.append(f"    description: {_yaml_str(desc)}")
    fm_lines.append("---")

    sections = sanitized_sections or draft["sections"]
    body_parts = [
        "## 01 Flow locator",
        sections["flow_locator"].rstrip(),
        "",
        "## 02 Code inventory",
        sections["code_inventory"].rstrip(),
        "",
        "## 03 Clarification",
        sections["clarification"].rstrip(),
        "",
    ]
    if draft.get("unresolved_questions"):
        body_parts.append("## Unresolved questions")
        for q in draft["unresolved_questions"]:
            body_parts.append(f"- {q}")
        body_parts.append("")

    return "\n".join(fm_lines) + "\n\n" + "\n".join(body_parts)
