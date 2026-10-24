"""The three held-out slices, and the boundaries between them."""
from __future__ import annotations

from datetime import date

import pytest

from eval import split
from eval.tests.helpers import make_call
from ingest.universe import held_out_ids

HELD = {"anon_003"}


def slices(company: str, as_of: date) -> list[str]:
    return split.slice_of(make_call(company=company, as_of=as_of), HELD)


def test_training_company_in_a_training_year_is_in_no_heldout_slice():
    assert slices("anon_001", date(2018, 3, 31)) == []
    assert slices("anon_001", date(2020, 6, 30)) == []      # the COVID quarters are training data


def test_the_year_boundary_2022_12_31_is_training_and_2023_01_01_is_heldout():
    assert slices("anon_001", date(2022, 12, 31)) == []
    assert slices("anon_001", date(2023, 1, 1)) == [split.UNSEEN_YEARS]
    assert slices("anon_001", date(2024, 12, 31)) == [split.UNSEEN_YEARS]


def test_a_heldout_company_in_2021_is_only_in_unseen_companies():
    assert slices("anon_003", date(2021, 6, 30)) == [split.UNSEEN_COMPANIES]
    assert slices("anon_003", date(2018, 3, 31)) == [split.UNSEEN_COMPANIES]


def test_a_heldout_company_in_a_heldout_year_is_in_both_company_slices():
    assert slices("anon_003", date(2023, 3, 31)) == [split.UNSEEN_COMPANIES, split.UNSEEN_BOTH]
    assert slices("anon_003", date(2022, 12, 31)) == [split.UNSEEN_COMPANIES]   # one day earlier: not "both"


def test_unseen_years_never_contains_a_heldout_company_so_the_slices_do_not_double_count():
    for as_of in (date(2023, 1, 1), date(2023, 6, 30), date(2024, 12, 31)):
        assert split.UNSEEN_YEARS not in slices("anon_003", as_of)


def test_a_year_after_the_heldout_window_is_in_no_heldout_year_slice():
    assert slices("anon_001", date(2025, 3, 31)) == []
    assert slices("anon_003", date(2025, 3, 31)) == [split.UNSEEN_COMPANIES]


def test_training_cell_is_a_training_company_in_a_training_year():
    cell = lambda c, d: split.in_training_cell(make_call(company=c, as_of=d), HELD)  # noqa: E731
    assert cell("anon_001", date(2018, 3, 31)) and cell("anon_001", date(2022, 12, 31))
    assert not cell("anon_001", date(2023, 1, 1))
    assert not cell("anon_003", date(2019, 6, 30))
    assert not cell("anon_001", date(2017, 12, 31))


def test_the_window_constants_match_the_spec():
    assert split.TRAIN_YEARS == (2018, 2022) and split.HELDOUT_YEARS == (2023, 2024)
    assert split.SLICES == ("unseen_years", "unseen_companies", "unseen_both")


def test_the_real_universe_has_ten_heldout_companies_that_slice_correctly():
    ids = held_out_ids()
    assert len(ids) == 10
    one = sorted(ids)[0]
    assert split.slice_of(make_call(company=one, as_of=date(2024, 3, 31)), ids) == [split.UNSEEN_COMPANIES,
                                                                                    split.UNSEEN_BOTH]


@pytest.mark.parametrize("settled,late", [(date(2022, 12, 31), False), (date(2023, 1, 1), True), (None, False)])
def test_an_outcome_settled_after_training_is_flagged_as_late(settled, late):
    from eval.tests.helpers import make_scored
    s = make_scored("yes", as_of=date(2022, 9, 30), resolution=settled)
    assert split.resolves_after_training(s.grade) is late
