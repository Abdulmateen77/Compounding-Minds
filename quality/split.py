"""Which calls are held out, and which count as training data (README 9, BRIEF_HERMES H2).

Two kinds of hold-out: by time (2023 and 2024 are never learned from) and by company (the ten
companies in `ingest.universe.held_out_ids()` are never learned from, in any year).
A call's year is `call.as_of.year`.
"""
from __future__ import annotations

from datetime import date
from typing import Collection

from schemas import AgentCall, Grade

TRAIN_YEARS = (2018, 2022)
HELDOUT_YEARS = (2023, 2024)
TRAIN_END = date(TRAIN_YEARS[1], 12, 31)

UNSEEN_YEARS = "unseen_years"          # training companies, held-out years
UNSEEN_COMPANIES = "unseen_companies"  # held-out companies, every year
UNSEEN_BOTH = "unseen_both"            # held-out companies, held-out years
SLICES = (UNSEEN_YEARS, UNSEEN_COMPANIES, UNSEEN_BOTH)


def is_train_year(year: int) -> bool:
    return TRAIN_YEARS[0] <= year <= TRAIN_YEARS[1]


def is_heldout_year(year: int) -> bool:
    return HELDOUT_YEARS[0] <= year <= HELDOUT_YEARS[1]


def slice_of(call: AgentCall, held_out_ids: Collection[str]) -> list[str]:
    """The held-out slices this call belongs to. A call in no held-out slice returns []."""
    held_company = call.company_id in held_out_ids
    held_year = is_heldout_year(call.as_of.year)
    out = []
    if held_year and not held_company:
        out.append(UNSEEN_YEARS)
    if held_company:
        out.append(UNSEEN_COMPANIES)
    if held_year and held_company:
        out.append(UNSEEN_BOTH)
    return out


def in_training_cell(call: AgentCall, held_out_ids: Collection[str]) -> bool:
    """A training company in a training year: the only calls anything is allowed to learn from."""
    return call.company_id not in held_out_ids and is_train_year(call.as_of.year)


def resolves_after_training(grade: Grade) -> bool:
    """True when the call was made in the training window but the filing that settled it came
    after it. Such an outcome is held-out-window information, so a baseline must not fit on it."""
    return grade.resolution_date is not None and grade.resolution_date > TRAIN_END
