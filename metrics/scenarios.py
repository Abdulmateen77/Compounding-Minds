"""Scenarios metrics (Dalio). Formulas: metrics/SPEC.md section 4.

Macro series come from ALFRED vintages through the date gate, so at `as_of` we only see GDP and
unemployment as they had been published by then (revisions come later and stay invisible).
"""
from __future__ import annotations

from datetime import date

from store.concepts import MACRO_SERIES

from .context import Context, Result, combine
from .stats import mean, slope_xy, stdev

GROWTH_WINDOW = 20      # quarters: five years
MIN_POINTS = 12         # fewest growth values we will compute a mean, deviation or beta from
GDP, UNRATE, CURVE, SPREAD = (MACRO_SERIES[k][0] for k in ("gdp", "unemployment", "yield_curve", "credit_spread"))


def growth_at(ctx: Context, end: date) -> Result | None:
    """Revenue of a quarter against the same quarter a year earlier."""
    prior = ctx.back(end, 4)
    if prior is None:
        return None
    now, then = ctx.quarter("revenue", end), ctx.quarter("revenue", prior)
    if now is None or then is None or then.value <= 0:
        return None
    return combine(now.value / then.value - 1, now, then)


def growth_series(ctx: Context) -> list[tuple[date, Result]]:
    out = []
    for e in ctx.timeline[-GROWTH_WINDOW:]:
        g = growth_at(ctx, e)
        if g is not None:
            out.append((e, g))
    return out


def _calendar_quarter_start(end: date) -> date:
    return date(end.year, 3 * ((end.month - 1) // 3) + 1, 1)


def gdp_growth_for(ctx: Context, obs: date) -> float | None:
    gdp = ctx.macro(GDP)
    prior = date(obs.year - 1, obs.month, obs.day)
    if obs in gdp and prior in gdp and gdp[prior] > 0:
        return gdp[obs] / gdp[prior] - 1
    return None


def revenue_macro_beta(ctx: Context) -> Result | None:
    """How strongly revenue growth moves with GDP growth (OLS slope over up to five years)."""
    xs, ys, parts = [], [], []
    for e, g in growth_series(ctx):
        x = gdp_growth_for(ctx, _calendar_quarter_start(e))
        if x is not None:
            xs.append(x)
            ys.append(g.value)
            parts.append(g)
    if len(xs) < MIN_POINTS:
        return None
    b = slope_xy(xs, ys)
    return None if b is None else combine(b, *parts)


def latest(ctx: Context, series_id: str) -> tuple[date, float] | None:
    s = ctx.macro(series_id)
    if not s:
        return None
    d = max(s)
    return d, s[d]


def gdp_growth_yoy(ctx: Context) -> Result | None:
    gdp = ctx.macro(GDP)
    for obs in sorted(gdp, reverse=True):  # latest observation that also has a year-earlier one
        g = gdp_growth_for(ctx, obs)
        if g is not None:
            return Result(g)
    return None


def _rate(ctx: Context, series_id: str) -> Result | None:
    got = latest(ctx, series_id)
    return None if got is None else Result(got[1] / 100)  # FRED publishes percent


def compute(ctx: Context) -> dict[str, Result | None]:
    q0 = ctx.q0
    series = growth_series(ctx) if q0 is not None else []
    values = [g.value for _, g in series]
    enough = len(values) >= MIN_POINTS
    parts = [g for _, g in series]
    latest_growth = growth_at(ctx, q0) if q0 is not None else None
    return {
        "revenue_growth_yoy": latest_growth,
        "revenue_growth_mean_5y": combine(mean(values), *parts) if enough else None,
        "revenue_growth_std_5y": combine(stdev(values), *parts) if enough else None,
        "revenue_macro_beta": revenue_macro_beta(ctx) if q0 is not None else None,
        "gdp_growth_yoy": gdp_growth_yoy(ctx),
        "unemployment_rate": _rate(ctx, UNRATE),
        "yield_curve_10y_2y": _rate(ctx, CURVE),
        "credit_spread_baa": _rate(ctx, SPREAD),
    }
