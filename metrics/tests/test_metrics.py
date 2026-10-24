"""The 22 metrics, checked against values worked out by hand from the synthetic company in
factory.py. The expectations below deliberately do NOT reuse the code under test: they apply the
formulas in metrics/SPEC.md to plain lists indexed by quarter number i (i = 23 is 2018Q4).
"""
from datetime import date

import pytest

from metrics import AGENT_METRICS, MAX_MISSING, get_metrics
from store import queries
from store.stubs import _load

from . import factory as F

AFTER = date(2019, 3, 1)            # after the FY2018 10-K (filed 2019-02-20): Q0 = 2018Q4, i = 23
BEFORE = date(2019, 2, 19)          # before it: Q0 = 2018Q3, i = 22
TOL = 6e-5                          # values are rounded to 4 decimals


def close(got, want):
    assert got is not None, "metric was missing"
    assert abs(got - want) <= TOL, f"{got} != {want}"


def metric(bundle, name):
    return next((m["value"] for m in bundle["metrics"] if m["name"] == name), None)


# plain-list reference series (quarter index i)
rev = lambda i: 100 + 10 * i                                  # noqa: E731
opinc = lambda i: 20 + i                                      # noqa: E731
fcf = lambda i: (30 + 3 * i) - 10                             # noqa: E731
ttm = lambda f, i: sum(f(j) for j in range(i - 3, i + 1))     # noqa: E731


def ols(xs, ys):
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)


@pytest.fixture(autouse=True)
def _reset():
    yield
    F.reset()


@pytest.fixture
def company():
    facts = F.build_facts()
    events = [
        dict(company_id="anon_001", form="8-K", items=["4.01", "9.01"], filed_date=date(2016, 6, 1), accession="EV-AUD-1"),
        dict(company_id="anon_001", form="8-K", items=["4.01"], filed_date=date(2012, 1, 5), accession="EV-AUD-OLD"),
        dict(company_id="anon_001", form="8-K", items=["2.02"], filed_date=date(2018, 5, 1), accession="EV-EARN"),
        dict(company_id="anon_001", form="10-Q", items=[], filed_date=date(2018, 5, 5), accession="EV-Q1", going_concern_hits=0),
        dict(company_id="anon_001", form="10-Q", items=[], filed_date=date(2018, 8, 5), accession="EV-Q2", going_concern_hits=2),
        dict(company_id="anon_001", form="10-Q", items=[], filed_date=date(2018, 11, 5), accession="EV-Q3", going_concern_hits=1),
        dict(company_id="anon_001", form="10-K", items=[], filed_date=date(2018, 2, 20), accession="EV-K17", going_concern_hits=9),
    ]
    F.install(facts, events, F.build_macro())
    return facts


# ------------------------------------------------------------------ Fundamentals
def test_fundamentals_metrics(company):
    b = get_metrics("anon_001", "fundamentals", AFTER)
    close(metric(b, "fcf_margin_ttm"), ttm(fcf, 23) / ttm(rev, 23))
    prev = ttm(fcf, 22) / ttm(rev, 22)
    close(metric(b, "fcf_margin_qoq_change"), ttm(fcf, 23) / ttm(rev, 23) - prev)
    close(metric(b, "operating_margin"), ttm(opinc, 23) / ttm(rev, 23))
    close(metric(b, "capex_to_revenue"), 40 / ttm(rev, 23))
    close(metric(b, "debt_to_ebitda"), (100 + 20) / (ttm(opinc, 23) + 20))
    # ROIC: tax rate = TTM tax 8 / TTM pre-tax (opinc - 2 per quarter), invested capital averaged over Q0 and Q-4
    pretax = ttm(opinc, 23) - 8
    nopat = ttm(opinc, 23) * (1 - 8 / pretax)
    ic = lambda i: (500 + 10 * i) + 120 - 50                  # noqa: E731
    close(metric(b, "roic"), nopat / ((ic(23) + ic(19)) / 2))
    # slope of the last eight quarterly FCF margins
    idx = list(range(16, 24))
    close(metric(b, "fcf_slope_8q"), ols(list(range(8)), [fcf(i) / rev(i) for i in idx]))


def test_before_the_10k_the_latest_quarter_is_q3_not_q4(company):
    b = get_metrics("anon_001", "fundamentals", BEFORE)
    close(metric(b, "fcf_margin_ttm"), ttm(fcf, 22) / ttm(rev, 22))
    close(metric(b, "operating_margin"), ttm(opinc, 22) / ttm(rev, 22))


def test_debt_is_not_counted_twice_when_long_term_debt_includes_the_current_part():
    facts = F.build_facts()
    for f in facts:
        if f["concept"] == "long_term_debt":
            f["source_tag"] = "LongTermDebt"             # this tag already contains the current portion
    F.install(facts)
    b = get_metrics("anon_001", "fundamentals", AFTER)
    close(metric(b, "debt_to_ebitda"), 100 / (ttm(opinc, 23) + 20))      # short-term debt NOT added


def test_negative_ebitda_gives_the_cap_not_a_negative_multiple():
    F.install(F.build_facts(operating_income=lambda i: -50, pretax_income=lambda i: -52, depreciation_amortization=lambda i: 5))
    b = get_metrics("anon_001", "fundamentals", AFTER)
    close(metric(b, "debt_to_ebitda"), 99.0)


# ------------------------------------------------------------------ Risk
def test_risk_metrics(company):
    b = get_metrics("anon_001", "risk", AFTER)
    close(metric(b, "interest_coverage"), ttm(opinc, 23) / 8)
    close(metric(b, "current_ratio"), (200 + 23) / 100)
    close(metric(b, "cash_runway_quarters"), 40.0)                        # positive FCF: not burning cash
    close(metric(b, "dividend_cut_history_5y"), 0.0)                      # never paid a dividend
    close(metric(b, "auditor_changes_5y"), 1.0)                           # the 2012 one is outside five years
    close(metric(b, "going_concern_hits"), 3.0)                           # 2 + 1 in the last year; the 2018-02 10-K is too old
    # leverage trend: debt / TTM EBITDA over the last 8 quarters
    ys = [120 / (ttm(opinc, i) + 20) for i in range(16, 24)]
    close(metric(b, "leverage_trend_8q"), ols(list(range(8)), ys))


def test_cash_runway_when_the_company_burns_cash():
    # opcf 0 with capex 10 -> FCF = -10 a quarter; cash 50 -> 5 quarters
    F.install(F.build_facts(op_cash_flow=lambda i: 0))
    close(metric(get_metrics("anon_001", "risk", AFTER), "cash_runway_quarters"), 5.0)


def test_runway_is_capped():
    F.install(F.build_facts(op_cash_flow=lambda i: 9, cash=lambda i: 5000))   # burning 1 a quarter, 5000 cash
    close(metric(get_metrics("anon_001", "risk", AFTER), "cash_runway_quarters"), 40.0)


def test_one_dividend_cut_counts_once_even_though_it_shows_in_several_quarters():
    # 4 a quarter until i = 13, then 2: trailing-year dividends fall by 25% or more in i = 15..19 (one run)
    F.install(F.build_facts(dividends_paid=lambda i: 4 if i <= 13 else 2))
    close(metric(get_metrics("anon_001", "risk", AFTER), "dividend_cut_history_5y"), 1.0)


def test_a_steady_dividend_is_not_a_cut():
    F.install(F.build_facts(dividends_paid=lambda i: 4))
    close(metric(get_metrics("anon_001", "risk", AFTER), "dividend_cut_history_5y"), 0.0)


def test_no_interest_expense_ever_reported_gives_the_cap():
    F.install(F.build_facts(interest_expense=None))
    close(metric(get_metrics("anon_001", "risk", AFTER), "interest_coverage"), 99.0)


def test_events_and_text_counts_are_missing_not_zero_when_no_filing_list_is_loaded():
    F.install(F.build_facts())
    b = get_metrics("anon_001", "risk", AFTER)
    assert {"auditor_changes_5y", "going_concern_hits"} <= set(b["missing"])
    assert b["usable"] is True                                     # 2 missing is still below the limit


def test_a_later_event_is_invisible_at_an_earlier_date(company):
    b = get_metrics("anon_001", "risk", date(2018, 5, 10))
    # going-concern: only the Q1 10-Q (0 hits) and the Feb 2018 10-K (9 hits) are visible and recent
    close(metric(b, "going_concern_hits"), 9.0)


# ------------------------------------------------------------------ Scenarios
def test_scenarios_revenue_metrics(company):
    b = get_metrics("anon_001", "scenarios", AFTER)
    g = lambda i: rev(i) / rev(i - 4) - 1                          # noqa: E731
    gs = [g(i) for i in range(4, 24)]                              # the last 20 quarters
    close(metric(b, "revenue_growth_yoy"), g(23))
    mean = sum(gs) / 20
    close(metric(b, "revenue_growth_mean_5y"), mean)
    close(metric(b, "revenue_growth_std_5y"), (sum((x - mean) ** 2 for x in gs) / 19) ** 0.5)


def test_scenarios_macro_metrics(company):
    b = get_metrics("anon_001", "scenarios", AFTER)
    close(metric(b, "unemployment_rate"), 0.042)                   # January's reading was published 2019-02-01, before AFTER
    close(metric(b, "yield_curve_10y_2y"), 0.0025)
    close(metric(b, "credit_spread_baa"), 0.019)
    # latest GDP observation known at AFTER with a year-earlier value: 2018 Q4 is published 2019-01-28 (j = 23)
    close(metric(b, "gdp_growth_yoy"), F.gdp_value(23) / F.gdp_value(19) - 1)


def test_macro_beta_is_the_ols_slope_of_revenue_growth_on_gdp_growth(company):
    b = get_metrics("anon_001", "scenarios", AFTER)
    g = lambda i: rev(i) / rev(i - 4) - 1                          # noqa: E731
    xs = [F.gdp_value(i) / F.gdp_value(i - 4) - 1 for i in range(4, 24)]
    ys = [g(i) for i in range(4, 24)]
    close(metric(b, "revenue_macro_beta"), ols(xs, ys))


def test_a_gdp_revision_is_invisible_until_it_is_published():
    revision = dict(series_id="GDPC1", value=F.gdp_value(22) * 1.5, obs_date=date(2018, 10, 1), vintage_date=date(2019, 6, 1))
    F.install(F.build_facts(), macro=F.build_macro(revision=revision))
    before = metric(get_metrics("anon_001", "scenarios", date(2019, 5, 1)), "gdp_growth_yoy")
    after = metric(get_metrics("anon_001", "scenarios", date(2019, 7, 1)), "gdp_growth_yoy")
    assert before != after


def test_unemployment_uses_the_reading_published_by_as_of():
    F.install(F.build_facts(), macro=F.build_macro())
    close(metric(get_metrics("anon_001", "scenarios", date(2019, 1, 31)), "unemployment_rate"), 0.039)
    close(metric(get_metrics("anon_001", "scenarios", date(2019, 2, 1)), "unemployment_rate"), 0.042)


def test_too_little_history_drops_the_five_year_statistics():
    F.install(F.build_facts(years=2), macro=F.build_macro())            # only 8 quarters of revenue
    b = get_metrics("anon_001", "scenarios", date(2015, 3, 1))
    assert {"revenue_growth_mean_5y", "revenue_growth_std_5y", "revenue_macro_beta"} <= set(b["missing"])
    assert metric(b, "revenue_growth_yoy") is not None


# ------------------------------------------------------------------ the bundle itself
def test_bundle_shape_matches_the_stubs_and_the_agent_metric_lists(company):
    for agent in AGENT_METRICS:
        b = get_metrics("anon_001", agent, AFTER)
        stub = _load(agent)[0]["metrics"]
        stub_units = {m["name"]: m["unit"] for m in stub}
        assert AGENT_METRICS[agent] == stub_units, f"{agent}: names or units differ from the stubs"
        assert list(AGENT_METRICS[agent]) == [m["name"] for m in stub]       # same order
        assert set(b) == {"company_id", "agent", "as_of", "metrics", "missing", "usable"}
        assert all(set(m) == {"name", "value", "unit", "as_of", "inputs"} for m in b["metrics"])


def test_values_are_rounded_so_a_model_can_copy_them_exactly(company):
    for m in get_metrics("anon_001", "fundamentals", AFTER)["metrics"]:
        assert m["value"] == round(m["value"], 4)


def test_every_input_accession_is_a_real_filing_of_this_company(company):
    known = F.all_accessions(company) | {"EV-AUD-1", "EV-Q1", "EV-Q2", "EV-Q3", "EV-K17", "EV-AUD-OLD", "EV-EARN"}
    for agent in ("fundamentals", "risk"):
        for m in get_metrics("anon_001", agent, AFTER)["metrics"]:
            assert set(m["inputs"]) <= known, (agent, m["name"])
    for m in get_metrics("anon_001", "fundamentals", AFTER)["metrics"]:
        assert m["inputs"], f"{m['name']} cites no filing"


def test_no_input_was_filed_after_as_of(company):
    filed = {f["accession"]: f["filed_date"] for f in company}
    for as_of in (BEFORE, AFTER):
        for m in get_metrics("anon_001", "fundamentals", as_of)["metrics"]:
            assert all(filed[a] <= as_of for a in m["inputs"]), (as_of, m["name"])


def test_three_or_more_missing_metrics_make_the_bundle_unusable():
    F.install(F.build_facts(cash=None))                  # cash drives runway and (for roic) invested capital
    b = get_metrics("anon_001", "risk", AFTER)           # no events: auditor and going-concern also missing
    assert len(b["missing"]) >= MAX_MISSING and b["usable"] is False


def test_unknown_agent_and_unknown_company():
    F.install(F.build_facts())
    with pytest.raises(KeyError):
        get_metrics("anon_001", "valuation", AFTER)
    b = get_metrics("anon_999", "fundamentals", AFTER)    # nothing loaded for this company
    assert b["metrics"] == [] and b["usable"] is False and len(b["missing"]) == 7


def test_the_gate_is_the_only_door(company, monkeypatch):
    """Every fact the metrics read goes through queries.get_facts at as_of."""
    seen = []
    real = queries.get_facts

    def spy(company_id, concept, as_of):
        seen.append(as_of)
        return real(company_id, concept, as_of)
    monkeypatch.setattr(queries, "get_facts", spy)
    get_metrics("anon_001", "fundamentals", BEFORE)
    assert seen and set(seen) == {BEFORE}
