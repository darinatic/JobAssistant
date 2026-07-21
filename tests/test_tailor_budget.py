"""The 'fit to page' explicit line-budget rule threaded into the tailor prompt."""

from src.agents.resume_tailor import _budget_rule, normalize_style


def test_budget_rule_states_the_line_budget_and_is_rule_seven():
    rule = _budget_rule(52.0)
    assert rule.startswith("7. ")
    assert "52 rendered lines" in rule


def test_budget_rule_rounds_and_generalizes_beyond_one_page():
    assert "104 rendered lines" in _budget_rule(104.0)


def test_budget_rule_keeps_honesty_guardrails():
    rule = _budget_rule(52.0).lower()
    assert "not fabricate" in rule
    assert "required-skill coverage" in rule


def test_normalize_style_unchanged():
    assert normalize_style("aggressive") == "aggressive"
    assert normalize_style(None, concise=True) == "balanced"
    assert normalize_style(None) == "faithful"
