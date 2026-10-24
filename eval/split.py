"""Train and held-out split by time and by company (README 9).

* Time: train 2018-2022, held-out 2023-2024.
* Company: about 10 companies are held out for good. Learning never sees them, in any year.
* The company choice is a fixed hash, so it never depends on results and nobody can tune it.
"""
from __future__ import annotations

import calendar
import hashlib
from dataclasses import dataclass
from datetime import date

TRAIN_YEARS = (2018, 2022)
HELD_OUT_YEARS = (2023, 2024)
DEFAULT_HELD_OUT_COMPANIES = 10
SEED = "compounding-minds-heldout-v1"

HORIZON_QUARTERS = {"next_quarter": 1, "4_quarters": 4, "12_months": 4}


def quarter_ends(first_year: int, last_year: int) -> list[date]:
    out = []
    for y in range(first_year, last_year + 1):
        for m in (3, 6, 9, 12):
            out.append(date(y, m, calendar.monthrange(y, m)[1]))
    return out


def add_quarters(d: date, n: int) -> date:
    """The quarter end n quarters after the quarter containing d."""
    idx = d.year * 4 + (d.month - 1) // 3 + n
    year, q = divmod(idx, 4)
    month = q * 3 + 3
    return date(year, month, calendar.monthrange(year, month)[1])


def pick_held_out(companies: list[str], n: int = DEFAULT_HELD_OUT_COMPANIES, seed: str = SEED) -> list[str]:
    ranked = sorted(companies, key=lambda c: hashlib.sha256(f"{seed}:{c}".encode()).hexdigest())
    return sorted(ranked[:n])


@dataclass(frozen=True)
class Split:
    train_companies: tuple[str, ...]
    held_out_companies: tuple[str, ...]
    train_quarters: tuple[date, ...]
    held_out_quarters: tuple[date, ...]

    @property
    def train_end(self) -> date:
        return self.train_quarters[-1]

    @property
    def all_companies(self) -> tuple[str, ...]:
        return self.train_companies + self.held_out_companies

    def to_dict(self) -> dict:
        return {
            "train_companies": list(self.train_companies),
            "held_out_companies": list(self.held_out_companies),
            "train_window": [self.train_quarters[0].isoformat(), self.train_quarters[-1].isoformat()],
            "held_out_window": [self.held_out_quarters[0].isoformat(), self.held_out_quarters[-1].isoformat()],
            "train_quarters": len(self.train_quarters),
            "held_out_quarters": len(self.held_out_quarters),
        }


def make_split(companies: list[str], n_held_out: int = DEFAULT_HELD_OUT_COMPANIES,
               train_years: tuple[int, int] = TRAIN_YEARS,
               held_out_years: tuple[int, int] = HELD_OUT_YEARS) -> Split:
    companies = sorted(set(companies))
    if n_held_out < 1 or n_held_out >= len(companies):
        raise ValueError(f"need 1 <= held-out ({n_held_out}) < companies ({len(companies)})")
    if held_out_years[0] <= train_years[1]:
        raise ValueError("held-out window must start after the train window ends")
    held = pick_held_out(companies, n_held_out)
    return Split(
        train_companies=tuple(c for c in companies if c not in held),
        held_out_companies=tuple(held),
        train_quarters=tuple(quarter_ends(*train_years)),
        held_out_quarters=tuple(quarter_ends(*held_out_years)),
    )
