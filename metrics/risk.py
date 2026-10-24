"""Risk metrics (Munger). Formulas: metrics/SPEC.md section 3."""
from __future__ import annotations

from datetime import date, timedelta

from .context import Context, Result, combine
from .fundamentals import debt_to_ebitda_at, fcf_quarter
from .stats import slope

COVERAGE_CAP = 99.0
RUNWAY_CAP = 40.0            # quarters: the value when the company is not burning cash
CUT = 0.25                   # a fall of 25% or more in trailing-year dividends is a cut
FIVE_YEARS = timedelta(days=5 * 365)
ONE_YEAR = timedelta(days=366)
TEXT_FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A"}


def interest_coverage(ctx: Context, q0: date) -> Result | None:
    ebit = ctx.ttm("operating_income", q0)
    if ebit is None:
        return None
    interest = ctx.zero_if_never_reported("interest_expense") or ctx.ttm("interest_expense", q0)
    if interest is None:
        return None
    value = COVERAGE_CAP if interest.value <= 0 else min(COVERAGE_CAP, ebit.value / interest.value)
    return combine(value, ebit, interest)


def current_ratio(ctx: Context, q0: date) -> Result | None:
    ca, cl = ctx.balance("current_assets", q0), ctx.balance("current_liabilities", q0)
    if ca is None or cl is None or cl.value <= 0:
        return None
    return combine(ca.value / cl.value, ca, cl)


def cash_runway_quarters(ctx: Context, q0: date) -> Result | None:
    """Quarters of cash left at the recent burn rate; the cap if the company is not burning cash."""
    w, cash = ctx.window(q0, 4), ctx.balance("cash", q0)
    if w is None or cash is None:
        return None
    parts = [fcf_quarter(ctx, e) for e in w]
    if any(p is None for p in parts):
        return None
    avg = sum(p.value for p in parts) / 4
    value = RUNWAY_CAP if avg >= 0 else min(RUNWAY_CAP, max(cash.value, 0.0) / -avg)
    return combine(value, cash, *parts)


def dividend_cut_history_5y(ctx: Context, q0: date) -> Result | None:
    """How many separate dividend cuts in the last five years.

    A cut is trailing-year dividends falling 25% or more against a year earlier. One cut shows up
    in four consecutive quarters, so a run of flagged quarters counts once.
    """
    concept = next((c for c in ("dividends_paid", "dividends_per_share") if ctx.has(c)), None)
    if concept is None:
        return Result(0.0)  # never paid a dividend: nothing to cut
    tl = ctx.timeline
    recent = tl[-20:]
    flags, used, comparable = [], frozenset(), 0
    for e in recent:
        prior = ctx.back(e, 4)
        cur, prev = ctx.ttm(concept, e), (ctx.ttm(concept, prior) if prior else None)
        if cur is None or prev is None:
            flags.append(False)
            continue
        comparable += 1
        used |= cur.inputs | prev.inputs
        flags.append(prev.value > 0 and cur.value <= (1 - CUT) * prev.value)
    if comparable == 0:
        return None
    cuts = sum(1 for i, f in enumerate(flags) if f and (i == 0 or not flags[i - 1]))
    return Result(float(cuts), used)


def auditor_changes_5y(ctx: Context) -> Result | None:
    """8-K item 4.01 (change of certifying accountant) in the last five years."""
    events = ctx.events()
    if not events:
        return None  # no filing list loaded for this company: unknown, not zero
    hits = [e for e in events if e.form in ("8-K", "8-K/A") and "4.01" in e.items
            and e.filed_date > ctx.as_of - FIVE_YEARS]
    return Result(float(len(hits)), frozenset(e.accession for e in hits))


def going_concern_hits(ctx: Context) -> Result | None:
    """Going-concern passages in the 10-Ks and 10-Qs filed in the last year."""
    recent = [e for e in ctx.events() if e.form in TEXT_FORMS and e.filed_date > ctx.as_of - ONE_YEAR]
    if not recent:
        return None
    return Result(float(sum(e.going_concern_hits for e in recent)), frozenset(e.accession for e in recent))


def leverage_trend_8q(ctx: Context, q0: date) -> Result | None:
    w = ctx.window(q0, 8)
    if w is None:
        return None
    parts = [debt_to_ebitda_at(ctx, e) for e in w]
    if any(p is None for p in parts):
        return None
    return combine(slope([p.value for p in parts]), *parts)


def compute(ctx: Context) -> dict[str, Result | None]:
    q0 = ctx.q0
    if q0 is None:
        return {}
    return {
        "interest_coverage": interest_coverage(ctx, q0),
        "current_ratio": current_ratio(ctx, q0),
        "cash_runway_quarters": cash_runway_quarters(ctx, q0),
        "dividend_cut_history_5y": dividend_cut_history_5y(ctx, q0),
        "auditor_changes_5y": auditor_changes_5y(ctx),
        "going_concern_hits": going_concern_hits(ctx),
        "leverage_trend_8q": leverage_trend_8q(ctx, q0),
    }
