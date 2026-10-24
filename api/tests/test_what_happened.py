"""The plain sentence under each prediction is written by Python from the grader's own evidence."""
from api.service import _what_happened


def test_fundamentals_sentence_uses_the_graders_numbers():
    ev = [{"q0": {"fcf_margin_ttm": 0.15, "operating_margin": 0.211},
           "q1": {"fcf_margin_ttm": 0.157, "operating_margin": 0.216}}]
    s = _what_happened("fundamentals", "yes", ev)
    assert "15.0% → 15.7%" in s and "21.1% → 21.6%" in s and s.endswith("both improved.")


def test_scenarios_sentence_names_the_band_and_the_growth():
    assert _what_happened("scenarios", "bear", [{"revenue_growth": -0.1}]).endswith("shrank (bear: below 0%), at -10.0%.")


def test_risk_sentence_names_the_event_and_unsettled_calls_say_nothing():
    ev = [{"components": {"dividend_cut": {"result": "yes"}, "auditor_change": {"result": "no"}}}]
    assert "dividend cut" in _what_happened("risk", "yes", ev)
    assert _what_happened("risk", None, ev) is None
