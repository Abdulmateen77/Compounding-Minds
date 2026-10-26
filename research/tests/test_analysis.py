"""Valuation arithmetic, the investor checks and the overall view."""
from datetime import date

import pytest

from metrics.tests import factory as F
from research import analysis, valuation as V
from research.report import build_report

AFTER = date(2019, 3, 1)
PROFILE = {"name": "Synthetic Co", "ticker": "SYN", "exchange": "Nasdaq", "market": "US", "cik": 1}


@pytest.fixture(autouse=True)
def _reset():
    yield
    F.reset()


def test_cash_flow_growth_fades_in_a_straight_line_to_the_long_run_rate():
    path = V.fcf_path(100.0, 0.10, years=10)
    assert path[0] == pytest.approx(110.0)
    last_growth = path[-1] / path[-2] - 1
    assert last_growth == pytest.approx(V.LONG_RUN)


def test_the_reverse_calculation_recovers_the_growth_that_made_the_price():
    path = V.fcf_path(100.0, 0.08)
    price = V.equity_per_share(path, V.DISCOUNT, net_debt=50.0, shares=10.0)
    assert V.implied_growth(price, 100.0, 50.0, 10.0) == pytest.approx(0.08, abs=1e-6)
    assert V.implied_growth(1e9, 100.0, 50.0, 10.0) is None          # beyond any plausible growth


def test_one_unusual_year_does_not_set_the_starting_cash_flow():
    v = V.build(fcf_history=[9.0, 10.0, -50.0, 11.0], revenue=100.0, cagr3=0.05, cagr5=0.05, net_debt=0.0, shares=1.0, price=None)
    assert v["normalised_fcf"] == 10.0                                  # median of the last three: -50, 10, 11 -> 10


def test_negative_cash_flow_is_not_valued_and_says_why():
    v = V.build(fcf_history=[-5.0, -3.0, -1.0], revenue=100.0, cagr3=0.1, cagr5=0.1, net_debt=0.0, shares=1.0, price=5.0)
    assert v["available"] is False and "not meaningful" in v["reason"]


def test_price_position_is_named_against_the_three_cases():
    pos = V._position
    assert pos(100, [10, 20, 30]) == "above_bull" and pos(25, [10, 20, 30]) == "above_base"
    assert pos(19, [10, 20, 30]) == "near_base" and pos(12, [10, 20, 30]) == "below_base" and pos(5, [10, 20, 30]) == "below_bear"


def test_fit_counts_partial_as_half_and_needs_two_known_checks():
    mk = lambda r: {"result": r}                                          # noqa: E731
    assert analysis.fit([mk("pass"), mk("partial"), mk("fail"), mk("unknown")]) == pytest.approx(0.5)
    assert analysis.fit([mk("pass"), mk("unknown")]) is None


def test_overall_view_rules():
    good = {"buffett": 0.8, "munger": 0.8}
    cheap, rich = {"available": True, "position": "near_base"}, {"available": True, "position": "above_bull"}
    assert analysis.overall(good, cheap)["key"] == "look"
    assert analysis.overall(good, rich)["key"] == "wait"
    assert analysis.overall({"buffett": 0.9, "munger": 0.2}, cheap)["key"] == "avoid"      # real risks beat a good price
    assert analysis.overall({"buffett": 0.2, "munger": 0.8}, cheap)["key"] == "weak"
    assert analysis.overall({"buffett": 0.5, "munger": 0.8}, cheap)["key"] == "mixed"


def test_every_check_names_its_principle_source_and_the_number_it_used():
    F.install(F.build_facts())
    a = build_report("anon_001", AFTER, PROFILE)["analysis"]
    assert [l["key"] for l in a["lenses"]] == ["buffett", "munger", "lynch", "dalio", "jhunjhunwala"]
    assert {l["key"] for l in a["lenses"] if l["backtested"]} == {"buffett", "munger"}
    for lens in a["lenses"]:
        for c in lens["checks"]:
            assert c["id"].startswith(lens["key"]) and c["principle"] != c["id"] and c["source"] and c["shown"]
            assert c["result"] in ("pass", "partial", "fail", "unknown")
    assert a["overall"]["headline"] and a["valuation"]["available"] in (True, False)


def test_the_valuation_uses_price_and_shares_when_the_market_is_known():
    from research import market
    F.install(F.build_facts())
    q = market.Quote("SYN", 5.0, "USD", "2019-02-28", 6.0, 4.0, [])
    a = build_report("anon_001", AFTER, PROFILE, quote=q, shares=(100.0, "2019-02-01", "SH"))["analysis"]
    v = a["valuation"]
    assert v["available"] and v["price"] == 5.0 and v["position"] and len(v["scenarios"]) == 3
    assert v["scenarios"][0]["value_per_share"] < v["scenarios"][1]["value_per_share"] < v["scenarios"][2]["value_per_share"]
    assert a["future"]["scenarios"][1]["fcf"]["5"] > 0


def _facts(**figs):
    """A report-shaped dict with only the figures a test needs."""
    sections = [{"figures": [{"key": k, "value": (v[-1] if isinstance(v, list) else v), "tone": None,
                              "history": [{"end": "x", "value": h} for h in (v if isinstance(v, list) else [v])]}
                             for k, v in figs.items()]}]
    return analysis.Facts({"sections": sections, "risk_flags": [], "economy": [], "market": None}, {})


def test_lynch_sorts_a_company_into_one_of_his_kinds_and_says_why():
    cat = lambda **kw: analysis.lynch_category(_facts(**kw), None)[0]              # noqa: E731
    steady_profit = dict(net_income=[5, 6, 7, 8, 9, 10], operating_margin=[0.2] * 6)
    assert cat(revenue_cagr_3y=0.22, revenue_growth=[0.2] * 5, **steady_profit) == "Fast grower"
    assert cat(revenue_cagr_3y=0.10, revenue_growth=[0.1] * 5, **steady_profit) == "Stalwart"
    assert cat(revenue_cagr_3y=0.02, revenue_growth=[0.02] * 5, **steady_profit) == "Slow grower"
    assert cat(revenue_cagr_3y=0.10, revenue_growth=[0.1, -0.1, 0.1, -0.1, 0.1], net_income=[5, 6, 7, 8, 9, 10],
               operating_margin=[0.2] * 6) == "Cyclical"
    assert cat(revenue_cagr_3y=0.10, revenue_growth=[0.1] * 5, net_income=[5, 6, 7, 8, 9, -2], operating_margin=[0.2] * 6) == "Turnaround"
    assert analysis.lynch_category(_facts(revenue_cagr_3y=0.1, revenue_growth=[0.1] * 5, **steady_profit), "3711")[0] == "Cyclical"


def test_graham_uses_his_own_thresholds_for_price_to_three_year_earnings():
    f = _facts(net_income=[10, 10, 10, 10, 10, 10], equity=100.0)
    f.market = {"market_cap": 120.0}                      # 12 times the three-year average profit
    checks = {c["id"]: c for c in analysis.graham(f)}
    assert checks["graham.g6"]["result"] == "pass" and "12.0" in checks["graham.g6"]["shown"]
    f.market = {"market_cap": 400.0}                      # 40 times
    assert {c["id"]: c for c in analysis.graham(f)}["graham.g6"]["result"] == "fail"


def test_guides_supply_each_check_with_its_rule_and_source_and_leave_the_agents_files_alone():
    assert "P/E" in analysis.principle_text("graham.g6") or "15 times" in analysis.principle_text("graham.g6")
    assert "Intelligent Investor" in analysis.principle_source("graham.g6")
    assert analysis.principle_text("buffett.01") != "buffett.01"                      # the agents' file still answers
    g = analysis.guide_text("lynch")
    assert "six kinds" in g.lower() or "six categories" in g.lower() or "which kind" in g.lower()
    assert "## Checks" not in g and "## Source map" not in g


def test_every_guide_check_line_is_parseable_and_every_lens_check_id_resolves():
    import re
    from pathlib import Path
    for name in ("buffett", "munger", "graham", "lynch", "dalio", "jhunjhunwala"):
        lines = [l for l in (Path(analysis.GUIDES_DIR) / f"{name}.md").read_text(encoding="utf-8").splitlines()
                 if re.match(rf"^{name}\.g\d+b? \|", l)]
        assert len(lines) >= 5 and all(len(l.split("|")) == 4 for l in lines), name


def test_each_investor_makes_a_call_and_price_minded_ones_wait_when_the_price_is_too_high():
    rich, fair = {"available": True, "position": "above_bull"}, {"available": True, "position": "near_base"}
    assert analysis.decide("buffett", 0.8, fair)["call"] == "invest"
    assert analysis.decide("buffett", 0.8, rich)["call"] == "wait"          # quality, but the price is too high for him
    assert analysis.decide("munger", 0.8, rich)["call"] == "invest"         # his checks are about failure, not price
    assert analysis.decide("dalio", 0.5, fair)["call"] == "wait" and analysis.decide("dalio", 0.2, fair)["call"] == "avoid"
    assert analysis.decide("lynch", None, fair)["label"] == "Not enough data"


def test_the_panel_tally_names_the_majority_or_says_it_is_split():
    mk = lambda *calls: [{"decision": {"call": c}} for c in calls]            # noqa: E731
    assert analysis.panel(mk("invest", "invest", "invest", "wait", "avoid"))["headline"] == "3 of 5 investors would invest"
    assert "split" in analysis.panel(mk("invest", "invest", "wait", "wait", "avoid"))["headline"]
    assert analysis.panel(mk("avoid", "avoid", "avoid", "wait", "invest"))["tone"] == "warn"
