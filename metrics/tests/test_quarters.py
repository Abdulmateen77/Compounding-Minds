"""Discrete-quarter derivation (metrics/SPEC.md section 1) and the date gate around it."""
from datetime import date

import pytest

from metrics.quarters import discrete_quarters, instants, months
from schemas import Fact
from store import queries

from . import factory as F

AFTER_FY2018 = date(2019, 3, 1)    # the FY2018 10-K was filed 2019-02-20
BEFORE_FY2018 = date(2019, 2, 19)


@pytest.fixture(autouse=True)
def _reset():
    yield
    F.reset()


def _quarters(concept, as_of):
    facts = queries.get_facts("anon_001", concept, as_of)
    return discrete_quarters(facts)


def test_period_length_in_months():
    assert months(date(2018, 1, 1), date(2018, 3, 31)) == 3
    assert months(date(2018, 1, 1), date(2018, 6, 30)) == 6
    assert months(date(2018, 1, 1), date(2018, 12, 31)) == 12
    assert months(date(2018, 1, 1), date(2018, 3, 3)) is None            # not a reporting period
    assert months(date(2018, 12, 31), date(2019, 3, 30)) == 3            # 52/53-week style calendars


def test_cash_flow_quarters_come_from_year_to_date_differences():
    F.install(F.build_facts())
    q = _quarters("op_cash_flow", AFTER_FY2018)
    # 2018: discrete opcf = 30 + 3i for i = 20..23 = 90, 93, 96, 99
    got = [q[date(2018, m, d)].value for m, d in F.QUARTER_ENDS]
    assert got == [90.0, 93.0, 96.0, 99.0]


def test_q4_of_cash_flow_is_full_year_minus_nine_months_and_uses_both_filings():
    F.install(F.build_facts())
    q4 = _quarters("op_cash_flow", AFTER_FY2018)[date(2018, 12, 31)]
    assert q4.accessions == {"ACC-2018-FY", "ACC-2018-Q3"}
    assert q4.available == date(2019, 2, 20)           # usable from the 10-K filing date, not the quarter end


def test_q4_is_invisible_before_the_10k_is_filed():
    F.install(F.build_facts())
    assert date(2018, 12, 31) not in _quarters("op_cash_flow", BEFORE_FY2018)
    assert date(2018, 9, 30) in _quarters("op_cash_flow", BEFORE_FY2018)
    assert date(2018, 12, 31) in _quarters("op_cash_flow", AFTER_FY2018)


def test_income_statement_q1_to_q3_are_read_directly_and_q4_uses_the_fallback():
    F.install(F.build_facts())      # operating income has no 6M/9M figures in the fixture
    q = _quarters("operating_income", AFTER_FY2018)
    assert [q[date(2018, m, d)].value for m, d in F.QUARTER_ENDS] == [40.0, 41.0, 42.0, 43.0]
    assert q[date(2018, 12, 31)].accessions >= {"ACC-2018-FY", "ACC-2018-Q1", "ACC-2018-Q2", "ACC-2018-Q3"}


def test_income_statement_q4_uses_nine_months_when_it_is_reported():
    F.install(F.build_facts())      # revenue has year-to-date figures
    q = _quarters("revenue", AFTER_FY2018)
    assert q[date(2018, 12, 31)].value == 330.0
    assert q[date(2018, 12, 31)].accessions == {"ACC-2018-FY", "ACC-2018-Q3"}


def test_a_directly_reported_quarter_beats_a_derived_one():
    F.install(F.build_facts())
    q = _quarters("revenue", AFTER_FY2018)
    assert q[date(2018, 6, 30)].accessions == {"ACC-2018-Q2"}          # the 3-month fact, not 6M - 3M


def test_balance_sheet_values_need_no_derivation():
    F.install(F.build_facts())
    q = instants(queries.get_facts("anon_001", "cash", AFTER_FY2018))
    assert q[date(2018, 12, 31)].value == 50.0 and q[date(2018, 12, 31)].available == date(2019, 2, 20)


def test_a_missing_quarter_leaves_a_gap_rather_than_a_guess():
    F.install(F.build_facts(skip_quarters=(21,)))      # no Q2 2018 cash flow figure at all
    q = _quarters("op_cash_flow", AFTER_FY2018)
    assert date(2018, 6, 30) not in q
    assert date(2018, 9, 30) not in q                   # Q3 needs the 6M figure it was differenced from


def test_52_week_calendar_period_lengths_are_recognised():
    # Costco-style: 12-week quarters (84 days), year-to-date of 24 and 36 weeks, a 52-week year
    start = date(2017, 9, 4)
    assert months(start, date(2017, 11, 26)) == 3        # 84 days
    assert months(start, date(2018, 2, 18)) == 6         # 168 days
    assert months(start, date(2018, 5, 13)) == 9         # 252 days
    assert months(start, date(2018, 9, 2)) == 12         # 364 days
    assert months(start, date(2018, 9, 8)) == 12         # a 53-week year, 370 days
    assert months(start, date(2017, 12, 31)) is None     # 119 days: not a reporting period


def test_a_retailer_calendar_cash_flow_derives_four_quarters():
    start = date(2017, 9, 4)
    cum = [(date(2017, 11, 26), 100.0, "Q1"), (date(2018, 2, 18), 250.0, "Q2"),
           (date(2018, 5, 13), 420.0, "Q3"), (date(2018, 9, 2), 600.0, "FY")]
    facts = [Fact(company_id="anon_001", concept="op_cash_flow", value=v, unit="USD", period_start=start,
                  period_end=end, fiscal_period=fp, form="10-K" if fp == "FY" else "10-Q", accession=f"A-{fp}",
                  filed_date=end) for end, v, fp in cum]
    q = discrete_quarters(facts)
    assert [q[end].value for end, _, _ in cum] == [100.0, 150.0, 170.0, 180.0]
