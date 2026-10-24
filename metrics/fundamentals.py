"""Fundamentals metrics (Buffett). Formulas: metrics/SPEC.md section 2."""
from __future__ import annotations

from datetime import date

from .context import Context, Result, combine
from .stats import slope

DEBT_CAP = 99.0  # debt/EBITDA when EBITDA is not positive: "not meaningful, very high"


def fcf_quarter(ctx: Context, end: date) -> Result | None:
    """Operating cash flow minus capex for one discrete quarter."""
    cfo, capex = ctx.quarter("op_cash_flow", end), ctx.quarter("capex", end)
    if cfo is None or capex is None:
        return None
    return combine(cfo.value - capex.value, cfo, capex)


def fcf_margin_ttm_at(ctx: Context, end: date) -> Result | None:
    w = ctx.window(end, 4)
    rev = ctx.ttm("revenue", end)
    if w is None or rev is None or rev.value <= 0:
        return None
    parts = [fcf_quarter(ctx, e) for e in w]
    if any(p is None for p in parts):
        return None
    return combine(sum(p.value for p in parts) / rev.value, rev, *parts)


def total_debt(ctx: Context, end: date) -> Result | None:
    """Long-term plus short-term debt, without counting the current portion twice.

    `LongTermDebt` already includes the current part, so when that is the tag in use only pure
    `ShortTermBorrowings` is added on top. A company that never reports a debt concept has none.
    """
    def pick(concept: str) -> tuple[Result | None, str | None]:
        if not ctx.has(concept):
            return Result(0.0), None
        r = ctx.balance(concept, end)
        tag = next((f.source_tag for f in ctx.facts(concept) if f.period_end == end), None)
        return r, tag

    ltd, ltd_tag = pick("long_term_debt")
    std, std_tag = pick("short_term_debt")
    if ltd is None or std is None:
        return None
    if ltd_tag == "LongTermDebt" and std_tag != "ShortTermBorrowings":
        std = Result(0.0)
    return ltd + std


def debt_to_ebitda_at(ctx: Context, end: date) -> Result | None:
    debt, ebit, da = total_debt(ctx, end), ctx.ttm("operating_income", end), ctx.ttm("depreciation_amortization", end)
    if debt is None or ebit is None or da is None:
        return None
    ebitda = ebit.value + da.value
    value = DEBT_CAP if ebitda <= 0 else min(DEBT_CAP, debt.value / ebitda)
    return combine(value, debt, ebit, da)


def _invested_capital(ctx: Context, end: date) -> Result | None:
    equity, cash, debt = ctx.balance("equity", end), ctx.balance("cash", end), total_debt(ctx, end)
    if equity is None or cash is None or debt is None:
        return None
    return combine(equity.value + debt.value - cash.value, equity, cash, debt)


def roic(ctx: Context, q0: date) -> Result | None:
    ebit, tax, pretax = ctx.ttm("operating_income", q0), ctx.ttm("income_tax_expense", q0), ctx.ttm("pretax_income", q0)
    prior = ctx.back(q0, 4)
    if ebit is None or tax is None or pretax is None or prior is None:
        return None
    ic_now, ic_then = _invested_capital(ctx, q0), _invested_capital(ctx, prior)
    if ic_now is None or ic_then is None:
        return None
    avg = (ic_now.value + ic_then.value) / 2
    if avg <= 0:
        return None
    rate = min(max(tax.value / pretax.value, 0.0), 0.35) if pretax.value > 0 else 0.0
    return combine(ebit.value * (1 - rate) / avg, ebit, tax, pretax, ic_now, ic_then)


def fcf_slope_8q(ctx: Context, q0: date) -> Result | None:
    w = ctx.window(q0, 8)
    if w is None:
        return None
    margins, parts = [], []
    for e in w:
        f, r = fcf_quarter(ctx, e), ctx.quarter("revenue", e)
        if f is None or r is None or r.value <= 0:
            return None
        margins.append(f.value / r.value)
        parts += [f, r]
    return combine(slope(margins), *parts)


def compute(ctx: Context) -> dict[str, Result | None]:
    q0 = ctx.q0
    if q0 is None:
        return {}
    out: dict[str, Result | None] = {}
    now = fcf_margin_ttm_at(ctx, q0)
    out["fcf_margin_ttm"] = now
    prev_end = ctx.back(q0, 1)
    prev = fcf_margin_ttm_at(ctx, prev_end) if prev_end else None
    out["fcf_margin_qoq_change"] = combine(now.value - prev.value, now, prev) if now and prev else None

    ebit, rev = ctx.ttm("operating_income", q0), ctx.ttm("revenue", q0)
    out["operating_margin"] = combine(ebit.value / rev.value, ebit, rev) if ebit and rev and rev.value > 0 else None
    out["roic"] = roic(ctx, q0)
    out["debt_to_ebitda"] = debt_to_ebitda_at(ctx, q0)
    out["fcf_slope_8q"] = fcf_slope_8q(ctx, q0)
    capex = ctx.ttm("capex", q0)
    out["capex_to_revenue"] = combine(capex.value / rev.value, capex, rev) if capex and rev and rev.value > 0 else None
    return out
