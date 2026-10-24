"""Discrete quarters from SEC period facts (metrics/SPEC.md section 1).

Agents reason in quarters, but filings report differently:

  * income-statement items: a 10-Q reports the 3-month figure, so Q1 to Q3 are read directly
  * cash-flow items: a 10-Q reports YEAR-TO-DATE (3, 6, 9 months), so Q2 = 6M - 3M, Q3 = 9M - 6M
  * Q4 is never reported: the 10-K gives only the full year. Q4 = FY - 9M year-to-date, or
    FY - (Q1 + Q2 + Q3) when no 9-month figure exists
  * balance-sheet items are values at a date, so they need no derivation

A derived quarter is only usable from the LATER of the filing dates it was built from, so Q4
appears when the 10-K is filed, never at the quarter end. Every fact arrives through the date
gate already filtered to `filed_date <= as_of`, which is what makes this safe.

Known limit, accepted: the gate returns the latest visible row per period. If a restatement
changes the 3-month figure but not the 6-month one, the derived Q2 mixes the two. That is rare
and small, and it is what the filings themselves would give an analyst on that date.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from schemas import Fact

DAYS_PER_MONTH = 30.4375


@dataclass(frozen=True)
class Q:
    """One discrete quarter (or balance-sheet date)."""

    end: date
    value: float
    accessions: frozenset[str]
    available: date                 # filing date from which this value could be known
    start: date | None = None       # first day of the quarter (None for balance-sheet values)


SLACK_DAYS = 12   # 52/53-week calendars put a "quarter" anywhere from 84 to 98 days; a year at 364 or 371


def months(start: date, end: date) -> int | None:
    """Length of a reporting period in months, if it really is a 3, 6, 9 or 12 month period."""
    days = (end - start).days + 1
    m = round(days / DAYS_PER_MONTH / 3) * 3
    if m in (3, 6, 9, 12) and abs(days - m * DAYS_PER_MONTH) <= SLACK_DAYS:
        return m
    return None


def instants(facts: list[Fact]) -> dict[date, Q]:
    """Balance-sheet values: one per period end."""
    out: dict[date, Q] = {}
    for f in facts:
        out[f.period_end] = Q(f.period_end, f.value, frozenset({f.accession}), f.filed_date)
    return out


def discrete_quarters(facts: list[Fact]) -> dict[date, Q]:
    """Discrete quarters for a flow concept, keyed by quarter end."""
    groups: dict[date, dict[int, Fact]] = {}   # fiscal-period start -> months -> fact
    for f in facts:
        if f.period_start is None:
            continue
        m = months(f.period_start, f.period_end)
        if m is not None:
            groups.setdefault(f.period_start, {})[m] = f

    direct: dict[date, Q] = {}
    derived: dict[date, Q] = {}
    for start, g in groups.items():
        if 3 in g:
            f = g[3]
            direct[f.period_end] = Q(f.period_end, f.value, frozenset({f.accession}), f.filed_date, f.period_start)
        for m in (6, 9, 12):
            if m in g and (m - 3) in g:
                cur, prev = g[m], g[m - 3]
                # the quarter between the two cumulative figures
                derived[cur.period_end] = Q(
                    cur.period_end, cur.value - prev.value, frozenset({cur.accession, prev.accession}),
                    max(cur.filed_date, prev.filed_date), prev.period_end + timedelta(days=1))
    quarters = {**derived, **direct}  # a directly reported quarter beats a derived one

    # Q4 of an income-statement item when no 9-month figure exists: FY - (Q1 + Q2 + Q3)
    for start, g in groups.items():
        fy = g.get(12)
        if fy is None or fy.period_end in quarters:
            continue
        inside = sorted((q for q in quarters.values()
                         if q.start is not None and q.start >= start and q.end < fy.period_end),
                        key=lambda q: q.end)
        if len(inside) == 3:
            accs = frozenset({fy.accession}).union(*(q.accessions for q in inside))
            quarters[fy.period_end] = Q(
                fy.period_end, fy.value - sum(q.value for q in inside), accs,
                max([fy.filed_date] + [q.available for q in inside]), inside[-1].end + timedelta(days=1))
    return dict(sorted(quarters.items()))
