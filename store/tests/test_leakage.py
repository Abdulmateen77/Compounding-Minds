"""Leakage test (README 4.4, test 1). Must pass before anything else is demoed."""
from datetime import date

import pytest

from store import queries
from store.queries import InMemoryBackend


def _fact(value, period_end, filed, accession):
    return dict(company_id="anon_001", concept="Revenues", value=value, unit="USD",
                period_start=None, period_end=period_end, fiscal_period="Q1", form="10-Q",
                accession=accession, filed_date=filed)


@pytest.fixture(autouse=True)
def backend():
    queries.set_backend(InMemoryBackend(
        facts=[
            _fact(100.0, date(2019, 3, 31), date(2019, 5, 2), "a1"),
            _fact(95.0, date(2019, 3, 31), date(2019, 11, 1), "a2"),   # restatement
            _fact(110.0, date(2019, 6, 30), date(2019, 8, 1), "a3"),
        ],
        events=[
            dict(company_id="anon_001", form="8-K", items=["4.01"], filed_date=date(2019, 9, 10), accession="e1"),
            dict(company_id="anon_001", form="10-Q", items=[], filed_date=date(2019, 5, 2), accession="e2"),
        ],
        macro=[
            dict(series_id="GDP", value=2.0, obs_date=date(2019, 3, 31), vintage_date=date(2019, 4, 28)),
            dict(series_id="GDP", value=3.1, obs_date=date(2019, 3, 31), vintage_date=date(2019, 7, 26)),  # revised
        ],
    ))
    yield
    queries.set_backend(InMemoryBackend())


@pytest.mark.parametrize("t", [date(2019, 4, 1), date(2019, 6, 1), date(2019, 9, 1), date(2019, 12, 31)])
def test_no_row_filed_after_as_of(t):
    assert all(f.filed_date <= t for f in queries.get_facts("anon_001", "Revenues", t))
    assert all(e.filed_date <= t for e in queries.get_events("anon_001", t))
    assert all(p.vintage_date <= t for p in queries.get_macro("GDP", t))


def test_restatement_invisible_before_its_filing_and_wins_after():
    before = {f.period_end: f.value for f in queries.get_facts("anon_001", "Revenues", date(2019, 10, 31))}
    after = {f.period_end: f.value for f in queries.get_facts("anon_001", "Revenues", date(2019, 11, 1))}
    assert before[date(2019, 3, 31)] == 100.0
    assert after[date(2019, 3, 31)] == 95.0


def test_period_end_in_the_past_does_not_make_a_row_visible():
    # Q2 period ended 2019-06-30 but was filed 2019-08-01.
    assert queries.get_facts("anon_001", "Revenues", date(2019, 7, 15))[-1].period_end == date(2019, 3, 31)


def test_macro_returns_vintage_valid_at_t():
    assert queries.get_macro("GDP", date(2019, 6, 1))[0].value == 2.0
    assert queries.get_macro("GDP", date(2019, 8, 1))[0].value == 3.1


def test_events_form_filter_and_gate():
    assert queries.get_events("anon_001", date(2019, 9, 1), forms=["8-K"]) == []
    assert len(queries.get_events("anon_001", date(2019, 9, 10), forms=["8-K"])) == 1


def test_three_and_six_month_facts_with_the_same_period_end_are_both_visible():
    """Regression: a Q2 10-Q reports the 3-month and the 6-month figure ending on the same date."""
    def f(value, start, accession):
        return dict(company_id="anon_002", concept="op_cash_flow", value=value, unit="USD", period_start=start,
                    period_end=date(2019, 6, 30), fiscal_period="Q2", form="10-Q", accession=accession,
                    filed_date=date(2019, 8, 1))
    queries.set_backend(InMemoryBackend(facts=[f(40.0, date(2019, 4, 1), "q2"), f(70.0, date(2019, 1, 1), "q2")]))
    got = {(x.period_start, x.value) for x in queries.get_facts("anon_002", "op_cash_flow", date(2019, 8, 1))}
    assert got == {(date(2019, 4, 1), 40.0), (date(2019, 1, 1), 70.0)}
