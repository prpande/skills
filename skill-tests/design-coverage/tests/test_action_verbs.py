"""Tests for lib/action_verbs.py (wave 3 #12)."""
from __future__ import annotations

import pytest
from action_verbs import ALLOWED_VERBS, ACTION_TEMPLATE_DISPLAY


def test_allowed_verbs_exported():
    assert ALLOWED_VERBS == ["Ask", "Confirm", "Drop", "Document", "Wire", "Deprecate"]


def test_action_template_display_exported():
    assert isinstance(ACTION_TEMPLATE_DISPLAY, str)
    assert len(ACTION_TEMPLATE_DISPLAY) > 0


def test_template_contains_verb_slot():
    assert "{verb}" in ACTION_TEMPLATE_DISPLAY


def test_template_contains_object_slot():
    assert "{object}" in ACTION_TEMPLATE_DISPLAY


def test_template_is_not_format_callable():
    """ACTION_TEMPLATE_DISPLAY is a prose display guide, not a str.format() target.
    Slots like `{has no | conflicts with}` are invalid placeholder names — calling
    .format() must raise KeyError so the contract is machine-checked."""
    with pytest.raises(KeyError):
        ACTION_TEMPLATE_DISPLAY.format()


def test_all_allowed_verbs_are_title_case():
    for verb in ALLOWED_VERBS:
        assert verb[0].isupper(), f"{verb!r} must start with an uppercase letter"
        assert verb == verb.strip(), f"{verb!r} must not have surrounding whitespace"


def test_allowed_verbs_no_duplicates():
    assert len(ALLOWED_VERBS) == len(set(ALLOWED_VERBS))
