"""Dividend cuts, measured so that payment timing is not mistaken for a cut.

A company that pays on the first of the month (Coca-Cola pays on 1 April, 1 July, 1 October and mid-December) has
quarters whose cash dividends land just either side of a quarter-end. One trailing-twelve-month window can then lose
a payment and fall by a third for a single quarter, with nothing cut. A real cut stays: the trailing year is lower in
the following quarters too. So a cut here is a trailing-year fall of 25% or more against a year earlier that holds for
two quarters in a row, and the declared dividend per share is preferred to cash paid when the company reports it.

The replay's Risk metric (metrics/risk.py) and the grader (grader/risk.py) still use the single-quarter rule, because
the final replay was graded under it. This module is what the research report and its back-test use.
"""
from __future__ import annotations

from datetime import date

from metrics.context import Context, Result

CUT = 0.25
CONCEPTS = ("dividends_per_share", "dividends_paid")     # smooth declared figure first, cash paid as the fallback
MIN_QUARTERS = 8


def _concept(ctx: Context) -> str | None:
    for c in CONCEPTS:
        if len(ctx.quarters(c)) >= MIN_QUARTERS:
            return c
    return None


def flagged_quarters(ctx: Context, concept: str, since: date | None = None, until: date | None = None) -> list[tuple[date, Result]]:
    """Quarter ends where the trailing year is at least 25% below a year earlier, oldest first."""
    out = []
    for e in ctx.timeline:
        if (since is not None and e <= since) or (until is not None and e > until):
            continue
        prior = ctx.back(e, 4)
        cur, prev = ctx.ttm(concept, e), (ctx.ttm(concept, prior) if prior else None)
        if cur is not None and prev is not None and prev.value > 0 and cur.value <= (1 - CUT) * prev.value:
            out.append((e, cur + prev))
    return out


def _runs(ctx: Context, flagged: list[tuple[date, Result]]) -> list[list[tuple[date, Result]]]:
    """Runs of flagged quarters that are consecutive on the company's own timeline."""
    index = {e: i for i, e in enumerate(ctx.timeline)}
    runs: list[list[tuple[date, Result]]] = []
    for item in flagged:
        if runs and index[item[0]] == index[runs[-1][-1][0]] + 1:
            runs[-1].append(item)
        else:
            runs.append([item])
    return runs


def count_cuts(ctx: Context, last_quarters: int = 20) -> Result | None:
    """Cuts in roughly the last five years: runs of two or more consecutive flagged quarters. A company that has never
    paid a dividend has made none; a payer with too little history gives None."""
    if not any(ctx.has(c) for c in CONCEPTS):
        return Result(0.0)
    c = _concept(ctx)
    if c is None:
        return None
    window = set(ctx.timeline[-last_quarters:])
    flagged = [x for x in flagged_quarters(ctx, c) if x[0] in window]
    runs = [r for r in _runs(ctx, flagged) if len(r) >= 2]
    used = frozenset().union(*(inputs for r in runs for _, res in r for inputs in [res.inputs])) if runs else frozenset()
    return Result(float(len(runs)), used)


def cut_in_window(ctx_at_end: Context, as_of: date, until: date) -> int | None:
    """1 if a cut began in (as_of, until] and had held for a second quarter by the context's date, 0 if not, None when
    the company pays a dividend but we cannot tell. Used by the back-test as the outcome."""
    if not any(ctx_at_end.has(c) for c in CONCEPTS):
        return 0
    c = _concept(ctx_at_end)
    if c is None:
        return None
    flagged = flagged_quarters(ctx_at_end, c, since=as_of)
    runs = [r for r in _runs(ctx_at_end, flagged) if len(r) >= 2 and r[0][0] <= until]
    return 1 if runs else 0
