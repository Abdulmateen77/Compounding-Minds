"""The 5-year outlook: bootstrap odds from the company's own record, and value per share along the way."""
import pytest

from research import outlook, valuation as V


def test_a_steady_grower_is_very_likely_bigger_and_a_shrinker_is_not():
    up = outlook.growth_odds([0.08, 0.10, 0.07, 0.09, 0.11, 0.06])
    down = outlook.growth_odds([-0.05, -0.08, -0.02, -0.06, 0.01, -0.04])
    assert up["chance_higher"] == 1.0 and up["low_change"] > 0.3
    assert down["chance_higher"] < 0.05
    mixed = outlook.growth_odds([0.3, -0.25, 0.2, -0.2, 0.1, -0.1])
    assert 0.2 < mixed["chance_higher"] < 0.9 and mixed["low_change"] < 0 < mixed["high_change"]


def test_the_odds_are_repeatable_and_need_four_years():
    g = [0.3, -0.25, 0.2, -0.2, 0.1]
    assert outlook.growth_odds(g) == outlook.growth_odds(g)
    assert outlook.growth_odds([0.1, 0.2, 0.3]) is None


def test_value_path_starts_at_the_valuations_own_value_and_grows_with_the_base_case():
    val = V.build(fcf_history=[90.0, 100.0, 110.0], revenue=1000.0, cagr3=0.06, cagr5=0.06, net_debt=50.0, shares=10.0, price=None)
    path = outlook.value_path(val, 10.0, 50.0)
    base = next(p for p in path if p["name"] == "Base")
    assert base["points"][0]["value"] == pytest.approx(val["scenarios"][1]["value_per_share"])
    assert base["points"][-1]["value"] > base["points"][0]["value"]
    assert [p["name"] for p in path] == ["Bear", "Base", "Bull"] and len(base["points"]) == 6


def test_the_verdict_reads_both_the_odds_and_the_price():
    odds = outlook.growth_odds([0.08, 0.10, 0.07, 0.09, 0.11, 0.06])
    assert outlook._verdict(odds, 0.12)["tone"] == "good"
    assert outlook._verdict(odds, -0.05)["tone"] == "warn" and "already assumes" in outlook._verdict(odds, -0.05)["why"]
    assert "Too little history" in outlook._verdict(None, None)["headline"]
