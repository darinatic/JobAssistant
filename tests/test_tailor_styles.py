"""Tailoring style resolution + prompt-rule wiring (no LLM)."""

from src.agents.resume_tailor import _STYLE_RULES, TAILOR_STYLES, normalize_style


def test_normalize_style_resolution():
    assert normalize_style("aggressive") == "aggressive"
    assert normalize_style("faithful") == "faithful"
    # Legacy concise flag now maps to aggressive; unknown/None/removed styles
    # fall back to faithful.
    assert normalize_style(None, concise=True) == "aggressive"
    assert normalize_style(None) == "faithful"
    assert normalize_style("balanced") == "faithful"
    assert normalize_style("nonsense") == "faithful"


def test_every_style_has_a_distinct_rule():
    assert set(_STYLE_RULES) == set(TAILOR_STYLES)
    assert TAILOR_STYLES == ("faithful", "aggressive")
    # Two distinct rules of escalating latitude.
    assert len({r for r in _STYLE_RULES.values()}) == 2
    assert "Preserve everything" in _STYLE_RULES["faithful"]
    assert "CUT" in _STYLE_RULES["aggressive"] and "REORDER" in _STYLE_RULES["aggressive"]


def test_honesty_guard_present_in_aggressive_rule():
    # The aggressive style must still restate the no-fabrication guard inline.
    rule = _STYLE_RULES["aggressive"].lower()
    assert "same underlying facts" in rule
    assert "never a new claim" in rule
