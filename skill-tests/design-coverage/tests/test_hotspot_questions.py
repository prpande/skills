# skill-tests/design-coverage/tests/test_hotspot_questions.py
"""Wave 1 #1 — verify the hotspot question registry emits deterministic
questions for known inventory shapes. Two agents on the same stage-2 inventory
must produce identical question sets in stage 3.
"""
import pytest


def _inventory_with(hotspots: list[dict]) -> dict:
    """Build a minimal stage-2 inventory dict with the given hotspot annotations."""
    items = []
    for i, h in enumerate(hotspots):
        items.append({
            "id": f"item-{i}",
            "kind": "state",
            "title": f"State {i}",
            "parent_id": None,
            "source": {"surface": "compose", "file": "x.swift"},
            "confidence": "high",
            "hotspot": h,
        })
    return {"items": items, "unwalked_destinations": [], "candidate_destinations": []}


def test_emit_questions_returns_empty_when_no_hotspots():
    from hotspot_questions import emit_questions_for_inventory
    questions = emit_questions_for_inventory(_inventory_with([]), platform_overrides={})
    assert questions == []


def test_emit_questions_one_per_distinct_symbol():
    from hotspot_questions import emit_questions_for_inventory
    inv = _inventory_with([
        {"type": "feature-flag", "symbol": "isAppointmentDetailsNewDesignEnabled"},
        {"type": "feature-flag", "symbol": "isAppointmentDetailsNewDesignEnabled"},  # duplicate
        {"type": "feature-flag", "symbol": "isGroupAppointmentsEnabled"},
    ])
    questions = emit_questions_for_inventory(inv, platform_overrides={})
    symbols = [q.symbol for q in questions]
    assert symbols == ["isAppointmentDetailsNewDesignEnabled", "isGroupAppointmentsEnabled"]


def test_emit_questions_uses_template_for_each_hotspot_type():
    from hotspot_questions import emit_questions_for_inventory
    inv = _inventory_with([
        {"type": "permission", "symbol": "staff.canEditAppointments"},
        {"type": "view-type", "symbol": "MBOApptDetailCheckoutCell"},
    ])
    questions = emit_questions_for_inventory(inv, platform_overrides={})
    by_type = {q.hotspot_type: q for q in questions}
    assert "permission" in by_type
    # Single view-type symbol — applies_when_count_gte=2 means it should NOT emit.
    assert "view-type" not in by_type
    assert "staff.canEditAppointments" in by_type["permission"].rendered_text


def test_emit_questions_respects_applies_when_count_gte():
    """view-type template requires at least 2 distinct symbols of the same type."""
    from hotspot_questions import emit_questions_for_inventory
    inv = _inventory_with([
        {"type": "view-type", "symbol": "MBOApptDetailCheckoutCell"},
    ])
    questions = emit_questions_for_inventory(inv, platform_overrides={})
    assert not any(q.hotspot_type == "view-type" for q in questions)


def test_emit_questions_view_type_with_multiple_symbols_emits():
    """When >=2 view-type symbols exist, both questions emit."""
    from hotspot_questions import emit_questions_for_inventory
    inv = _inventory_with([
        {"type": "view-type", "symbol": "MBOApptDetailCheckoutCell"},
        {"type": "view-type", "symbol": "MBOApptDetailPaymentCheckoutCell"},
    ])
    questions = emit_questions_for_inventory(inv, platform_overrides={})
    view_type_qs = [q for q in questions if q.hotspot_type == "view-type"]
    assert len(view_type_qs) == 2


def test_platform_overrides_replace_template_text():
    from hotspot_questions import emit_questions_for_inventory
    inv = _inventory_with([
        {"type": "permission", "symbol": "staff.canFoo"},
    ])
    overrides = {"permission": "Custom-template for {symbol}: ok?"}
    questions = emit_questions_for_inventory(inv, platform_overrides=overrides)
    assert questions
    assert "Custom-template for staff.canFoo" in questions[0].rendered_text


def test_question_template_severity_metadata_present():
    from hotspot_questions import HOTSPOT_QUESTIONS
    for hotspot_type, tmpl in HOTSPOT_QUESTIONS.items():
        assert tmpl.severity_if_violated in {"info", "warn", "error"}, \
            f"{hotspot_type} template has invalid severity"
        assert tmpl.default_answer, f"{hotspot_type} template missing default_answer"
        assert "{symbol}" in tmpl.template, f"{hotspot_type} template missing {{symbol}} slot"


def test_registry_covers_every_hotspot_type_value():
    """The registry must have one entry per hotspot.type enum value (verified
    via the schema-derived sealed_enum_index helper)."""
    from hotspot_questions import HOTSPOT_QUESTIONS
    from sealed_enum_index import get_sealed_enum_pattern_keys
    hotspot_types_in_schema = {
        k.split(".")[-1]
        for k in get_sealed_enum_pattern_keys()
        if k.startswith("inventory_item.hotspot.type.") or k.startswith("hotspot.type.")
    }
    missing = hotspot_types_in_schema - set(HOTSPOT_QUESTIONS.keys())
    assert not missing, f"hotspot_questions registry missing entries for: {sorted(missing)}"


def test_emitted_question_carries_canonical_answers():
    """Stage 03 must present canonical_answers (default + alternatives) to the
    user; persisting any other string breaks stage 05's matrix lookup."""
    from hotspot_questions import emit_questions_for_inventory
    inv = _inventory_with([
        {"type": "feature-flag", "symbol": "someFlag"},
    ])
    questions = emit_questions_for_inventory(inv, platform_overrides={})
    assert len(questions) == 1
    q = questions[0]
    # default_answer always leads the canonical set.
    assert q.canonical_answers[0] == q.default_answer
    # Set is non-trivial: the registry declares alternatives for every type.
    assert len(q.canonical_answers) >= 2
    # Default + alternatives are unique.
    assert len(set(q.canonical_answers)) == len(q.canonical_answers)


def test_every_template_declares_alternatives():
    """A template with only `default_answer` (no alternatives) gives the user
    no choice and silently produces drift if anyone hand-edits the answer.
    Every registry entry must offer at least one alternative."""
    from hotspot_questions import HOTSPOT_QUESTIONS
    for hotspot_type, tmpl in HOTSPOT_QUESTIONS.items():
        assert tmpl.alternatives, (
            f"{hotspot_type} template has no alternatives — the user has no canonical "
            "non-default answer to choose from"
        )
        assert tmpl.default_answer not in tmpl.alternatives, (
            f"{hotspot_type} template duplicates default_answer in alternatives"
        )


def test_view_type_template_phrasing_does_not_imply_per_symbol_multiplicity():
    """Wave-1 fix: the prior wording 'Multiple variants of {symbol} exist'
    misled the user when applies_when_count_gte=2 actually counts distinct
    *symbols* of the type, not variants of one symbol."""
    from hotspot_questions import HOTSPOT_QUESTIONS
    tmpl = HOTSPOT_QUESTIONS["view-type"]
    # The template should NOT say "Multiple variants of {symbol}" — that phrase
    # implies the symbol itself has multiple variants, which is not what the
    # gating logic measures.
    assert "Multiple variants of {symbol}" not in tmpl.template
    # The replacement phrasing references the {N}-of-symbols framing.
    assert "{N}" in tmpl.template
