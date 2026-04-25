# skills/design-tooling/design-coverage/lib/hotspot_questions.py
"""Deterministic question registry for stage 03 clarification.

Today (pre-wave-1) stage 03 asks free-form questions invented by the agent.
Two agents on the same stage-2 inventory produce different question sets,
which produces different downstream severity calls. This module replaces
the free-form prose with a registry: one entry per hotspot.type enum value,
each declaring a question template + default answer + severity-if-violated.

Stage 03 calls emit_questions_for_inventory(stage2_inventory, platform_overrides).
The function:
  1. Walks every inventory item with a non-null hotspot.
  2. Groups by (hotspot_type, hotspot.symbol) so duplicate symbols collapse.
  3. Looks up the template in HOTSPOT_QUESTIONS (or platform_overrides if present).
  4. Skips templates whose applies_when_count_gte threshold isn't met.
  5. Returns one Question per distinct (type, symbol) — the order is
     stable: hotspot_type alphabetical, then symbol alphabetical.

The resulting list feeds AskUserQuestion (or equivalent) one question at a time.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class QuestionTemplate:
    """One entry in the registry per hotspot.type enum value."""
    template: str  # Must contain {symbol}; may contain {N} for view-type variant counts.
    default_answer: str
    severity_if_violated: str  # "info" | "warn" | "error"
    applies_when_count_gte: int = 1  # Minimum distinct symbols of this type for the Q to apply.
    # Canonical answer set the user may select from. Stage 03 MUST present
    # these as multiple-choice options via AskUserQuestion and persist exactly
    # one of them as `clarifications.resolved[].answer` — stage 05's severity
    # matrix only matches against these literal strings, so a free-form answer
    # would silently fall through to the generic "warn" bucket.
    alternatives: tuple[str, ...] = ()


@dataclass(frozen=True)
class Question:
    """One emitted question to ask the user."""
    hotspot_type: str
    symbol: str
    rendered_text: str
    default_answer: str
    severity_if_violated: str
    # Full canonical answer set (default_answer plus any alternatives). Stage 03
    # MUST present these as the only valid answers; persisting anything else
    # breaks the join with severity_matrix.SEVERITY_MATRIX.
    canonical_answers: tuple[str, ...] = ()


# Registry — one entry per hotspot.type enum value.
# Sync this set with schemas/inventory_item.json's hotspot.type enum (the
# test_registry_covers_every_hotspot_type_value test gates the sync).
HOTSPOT_QUESTIONS: dict[str, QuestionTemplate] = {
    "feature-flag": QuestionTemplate(
        template="Treat the {symbol} flag as on, off, or both branches for this audit?",
        default_answer="on",
        severity_if_violated="error",
        applies_when_count_gte=1,
        alternatives=("off", "both"),
    ),
    "permission": QuestionTemplate(
        template="Assume the {symbol} permission is granted unless a Figma frame explicitly shows the denied state?",
        default_answer="granted",
        severity_if_violated="warn",
        applies_when_count_gte=1,
        alternatives=("denied", "both"),
    ),
    "server-driven": QuestionTemplate(
        template="For the {symbol} server-driven section, must Figma cover BOTH the populated and the empty states?",
        default_answer="both_states_required",
        severity_if_violated="error",
        applies_when_count_gte=1,
        alternatives=("populated_only", "empty_only"),
    ),
    "view-type": QuestionTemplate(
        # `applies_when_count_gte=2` gates on the *count of distinct view-type
        # symbols in code*, not multiplicity of one symbol — phrase the prompt
        # accordingly so the user understands they're confirming coverage of
        # the whole class of variants, not variants of a single cell.
        template="{symbol} is one of {N} view-type variants in code. Must Figma cover all variants of this view-type group?",
        default_answer="all_variants_required",
        severity_if_violated="error",
        applies_when_count_gte=2,  # Only ask if >=2 distinct symbols of this type.
        alternatives=("single_variant_only", "out_of_scope"),
    ),
    "form-factor": QuestionTemplate(
        template="The {symbol} branch differs by form factor (compact/regular/landscape/etc.). Are all axes in scope?",
        default_answer="all_in_scope",
        severity_if_violated="warn",
        applies_when_count_gte=1,
        alternatives=("default_only",),
    ),
    "config-qualifier": QuestionTemplate(
        template="The {symbol} branch depends on a configuration qualifier (e.g., business-setting flag). Assume the default qualifier value, or are all values in scope?",
        default_answer="default_only",
        severity_if_violated="info",
        applies_when_count_gte=1,
        alternatives=("all_in_scope",),
    ),
    "process-death": QuestionTemplate(
        template="The {symbol} state-restoration path handles process death. Is this path in scope for the audit?",
        default_answer="out_of_scope",
        severity_if_violated="info",
        applies_when_count_gte=1,
        alternatives=("in_scope",),
    ),
    "viewpager-tab": QuestionTemplate(
        template="The {symbol} tab/page navigation has multiple destinations. Are all tabs in scope?",
        default_answer="all_in_scope",
        severity_if_violated="warn",
        applies_when_count_gte=1,
        alternatives=("default_tab_only",),
    ),
    "sheet-dialog": QuestionTemplate(
        template="The {symbol} sheet/dialog overlay can be presented from multiple states. Must Figma cover the presented variant?",
        default_answer="presented_variant_required",
        severity_if_violated="warn",
        applies_when_count_gte=1,
        alternatives=("dismissed_only",),
    ),
}


def emit_questions_for_inventory(inventory: dict, platform_overrides: dict[str, str]) -> list[Question]:
    """Walk the stage-2 inventory and emit one Question per distinct hotspot symbol.

    `inventory` is the parsed code_inventory.json shape. Items with no hotspot
    are skipped. Duplicate (hotspot.type, hotspot.symbol) pairs collapse to
    one Question. `platform_overrides` is a mapping of hotspot_type -> template
    string; when present, replaces HOTSPOT_QUESTIONS[type].template.
    """
    # Group by (hotspot_type, symbol) to dedupe.
    seen: dict[tuple[str, str], None] = {}
    by_type_count: dict[str, int] = {}
    for item in inventory.get("items", []):
        h = item.get("hotspot")
        if not h:
            continue
        htype = h.get("type")
        symbol = h.get("symbol")  # Identifier for dedup + template substitution.
        if not htype or not symbol:
            continue
        key = (htype, symbol)
        if key not in seen:
            seen[key] = None
            by_type_count[htype] = by_type_count.get(htype, 0) + 1

    questions: list[Question] = []
    for (htype, symbol) in sorted(seen.keys()):
        tmpl = HOTSPOT_QUESTIONS.get(htype)
        if tmpl is None:
            continue  # Hotspot type not in registry — skip silently (test gates this).
        if by_type_count[htype] < tmpl.applies_when_count_gte:
            continue
        template_text = platform_overrides.get(htype, tmpl.template)
        rendered = template_text.format(symbol=symbol, N=by_type_count[htype])
        questions.append(Question(
            hotspot_type=htype,
            symbol=symbol,
            rendered_text=rendered,
            default_answer=tmpl.default_answer,
            severity_if_violated=tmpl.severity_if_violated,
            canonical_answers=(tmpl.default_answer,) + tmpl.alternatives,
        ))
    return questions
