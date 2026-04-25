"""Constrained vocabulary for the stage-6 narrative next-5-actions block.

Wave 3 #12 — replaces free-prose action instructions with a slot-fill template
so two runs on the same 06-report.json produce matching verbs and noun-objects.
"""
from __future__ import annotations

ALLOWED_VERBS: list[str] = ["Ask", "Confirm", "Drop", "Document", "Wire", "Deprecate"]

# Display guide for agent use — NOT a str.format() template.
# Slots with `|`-delimited options (e.g., `{has no | conflicts with}`) are
# prose choices; the agent picks one. Do NOT call .format() on this string.
ACTION_TEMPLATE_DISPLAY: str = (
    "{N}. **{verb} {object}** — {legacy_ref} {has no | conflicts with} {figma_ref}.\n"
    "   {one-sentence consequence}. "
    "Action: {ask_design | confirm_with_product | document_as_dropped | wire_in_navigation}."
)
