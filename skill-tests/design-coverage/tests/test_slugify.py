from slugify import slugify

def test_simple_lowercase():
    assert slugify("Appointment Details") == "appointment-details"

def test_strips_punctuation():
    assert slugify("New Appt! — Liability Waiver?") == "new-appt-liability-waiver"

def test_collapses_whitespace_and_dashes():
    assert slugify("  foo   --   bar  ") == "foo-bar"

def test_non_ascii_transliterated_or_stripped():
    assert slugify("café menu") in {"cafe-menu", "caf-menu"}

def test_empty_and_all_punct_returns_untitled():
    assert slugify("") == "untitled"
    assert slugify("!!!") == "untitled"
