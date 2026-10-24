"""Discrete quarters and TTM sums from store facts (metrics/SPEC.md section 1). Pure Python.

Facts come from store.queries.get_facts(company, concept, as_of), so every row is already
point-in-time and the latest visible restatement wins. A derived quarter (Q2 = 6M - 3M,
Q4 = FY - 9M) becomes visible at the LATER filing date of the facts it uses.

ONE DEFINITION OF A QUARTER. The agent is shown numbers built by metrics/ (Person A) and is graded on
numbers built here, so the two must never disagree. `quarter_table` therefore reads its quarters from the
same `metrics.context.Context` the metrics engine uses: the same period-length windows (52/53-week
retailers), the same 120-day quarter-gap limit, and the same derived operating income for filers that
never tag it. Found on real data: the grader's own copy marked 30 of 82 Fundamentals calls unresolvable
because it knew none of this.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from schemas import Fact
from store import queries

from metrics.context import MAX_GAP, MIN_GAP, Context

from .config import QUARTER_DAYS


@dataclass(frozen=True)
class Quarter:
    period_end: date
    value: float
    visible: date           # filing date at which this quarter first became knowable
    accessions: tuple[str, ...]


def _days(a: date, b: date) -> int:
    return (b - a).days


def _is_quarter(f: Fact) -> bool:
    return f.period_start is not None and QUARTER_DAYS[0] <= _days(f.period_start, f.period_end) <= QUARTER_DAYS[1]


def discrete_quarters(facts: list[Fact]) -> list[Quarter]:
    flows = [f for f in facts if f.period_start is not None]
    by_start: dict[date, list[Fact]] = {}
    for f in flows:
        by_start.setdefault(f.period_start, []).append(f)
    out: dict[date, Quarter] = {}
    for f in flows:
        if _is_quarter(f):
            out[f.period_end] = Quarter(f.period_end, f.value, f.filed_date, (f.accession,))
    for group in by_start.values():
        group.sort(key=lambda f: f.period_end)
        for f in group:
            if f.period_end in out or _is_quarter(f):
                continue
            prev = [p for p in group if QUARTER_DAYS[0] <= _days(p.period_end, f.period_end) <= QUARTER_DAYS[1]]
            if prev:
                p = prev[0]
                out[f.period_end] = Quarter(f.period_end, f.value - p.value, max(f.filed_date, p.filed_date),
                                            tuple(dict.fromkeys((f.accession, p.accession))))
    return sorted(out.values(), key=lambda q: q.period_end)


def _consecutive(a: Quarter, b: Quarter) -> bool:
    return MIN_GAP <= _days(a.period_end, b.period_end) <= MAX_GAP


def run_ending_at(qs: list[Quarter], end: date, n: int) -> list[Quarter] | None:
    """The n consecutive quarters ending at `end`, or None if they are not all there."""
    idx = next((i for i, q in enumerate(qs) if q.period_end == end), None)
    if idx is None or idx + 1 < n:
        return None
    run = qs[idx - n + 1: idx + 1]
    return run if all(_consecutive(x, y) for x, y in zip(run, run[1:])) else None


def ttm(qs: list[Quarter], end: date) -> Quarter | None:
    run = run_ending_at(qs, end, 4)
    if not run:
        return None
    return Quarter(end, sum(q.value for q in run), max(q.visible for q in run),
                   tuple(dict.fromkeys(a for q in run for a in q.accessions)))


def quarter_table(company_id: str, concepts, as_of: date) -> dict[str, list[Quarter]]:
    ctx = Context(company_id, as_of)    # reads through the date gate at as_of, like everything else
    return {c: [Quarter(q.end, q.value, q.available, tuple(sorted(q.accessions)))
                for q in ctx.quarters(c).values()] for c in concepts}


def common_ends(table: dict[str, list[Quarter]]) -> list[date]:
    sets = [{q.period_end for q in qs} for qs in table.values()]
    return sorted(set.intersection(*sets)) if sets else []
