"""Dividend cuts: payment timing is not a cut, a held fall is."""
from datetime import date

import pytest

from metrics.context import Context
from metrics.tests import factory as F
from research import dividends

AFTER = date(2019, 3, 1)             # after the FY2018 10-K: the last quarter is i = 23


@pytest.fixture(autouse=True)
def _reset():
    yield
    F.reset()


def _ctx(per_quarter):
    F.install(F.build_facts(dividends_paid=per_quarter))
    return Context("anon_001", AFTER)


def test_a_steady_dividend_has_no_cuts():
    assert dividends.count_cuts(_ctx(lambda i: 10)).value == 0.0


def test_one_quarter_where_a_payment_slips_over_the_quarter_end_is_not_a_cut():
    # a payment due at the end of quarter 20 lands in quarter 21: the trailing year dips for one quarter only
    glitch = lambda i: 0 if i == 20 else 20 if i == 21 else 10                          # noqa: E731
    ctx = _ctx(glitch)
    assert dividends.flagged_quarters(ctx, "dividends_paid"), "the single-quarter rule would call this a cut"
    assert dividends.count_cuts(ctx).value == 0.0


def test_a_dividend_that_stays_lower_is_one_cut_even_though_it_shows_in_several_quarters():
    ctx = _ctx(lambda i: 10 if i < 20 else 4)
    assert dividends.count_cuts(ctx).value == 1.0


def test_a_company_that_never_paid_has_made_no_cut_and_a_short_record_gives_none():
    F.install(F.build_facts())                                  # no dividends in the default company
    assert dividends.count_cuts(Context("anon_001", AFTER)).value == 0.0
    F.install(F.build_facts(years=1, dividends_paid=lambda i: 10))
    assert dividends.count_cuts(Context("anon_001", date(2014, 3, 1))) is None


def test_the_outcome_only_counts_cuts_that_begin_in_the_window_and_hold():
    ctx = _ctx(lambda i: 10 if i < 20 else 4)                  # the cut starts in 2018
    assert dividends.cut_in_window(ctx, date(2017, 12, 31), date(2018, 12, 31)) == 1
    assert dividends.cut_in_window(ctx, date(2018, 12, 31), date(2019, 12, 31)) == 0   # already under way before the window
    glitch = _ctx(lambda i: 0 if i == 20 else 20 if i == 21 else 10)
    assert dividends.cut_in_window(glitch, date(2017, 12, 31), date(2018, 12, 31)) == 0
