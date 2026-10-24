"""The research report for one company as of one date. Python computes every figure; nothing here calls a model.

Built on metrics.Context, so it reads through the same date gate as the replay (as_of is simply today for a live
company). Each figure carries the SEC filings it came from and a short history at year-spaced points, so a chart
and an audit trail come for free. Tones (good / watch / warn) are rules of thumb, kept in TONE below in one place.
They describe the evidence; they are not advice.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

from metrics import fundamentals, risk, scenarios
from metrics.context import Context, Result, combine

from . import dividends, quick_check
from .analysis import analyse

STALE_DAYS = 500            # a last revenue quarter older than this means we cannot read the company's revenue
HISTORY_POINTS = 7          # year-spaced points, six years: the oldest only feeds the first growth figure


# ---- rules of thumb: (good if, warn if) per metric. One place, so they are easy to read and to defend ----------
def _hi(good, warn):          # higher is better
    return lambda v: "good" if v >= good else "warn" if v < warn else "watch"


def _lo(good, warn):          # lower is better
    return lambda v: "good" if v <= good else "warn" if v > warn else "watch"


TONE: dict[str, Callable[[float], str]] = {
    "revenue_growth": _hi(0.08, 0.0), "revenue_cagr_3y": _hi(0.08, 0.0),
    "operating_margin": _hi(0.15, 0.05), "net_margin": _hi(0.10, 0.02), "gross_margin": _hi(0.40, 0.20),
    "fcf_margin": _hi(0.10, 0.0), "cash_conversion": _hi(0.8, 0.3),
    "current_ratio": _hi(1.5, 1.0), "debt_to_ebitda": _lo(2.0, 4.0), "interest_cover": _hi(8.0, 3.0),
    "roic": _hi(0.15, 0.08), "roe": _hi(0.15, 0.08), "roce": _hi(0.20, 0.10),
}
LABEL_TONE = {"good": "Strength", "watch": "Worth watching", "warn": "Concern"}


@dataclass
class Fig:
    key: str
    label: str
    meaning: str
    unit: str                      # usd | pct | x | count | quarters | pts | usd_ps
    res: Result | None
    history: list[tuple[date, float | None]]
    approx: bool = False
    tone_key: str | None = None

    def as_dict(self) -> dict:
        v = None if self.res is None else self.res.value
        tone = TONE[self.tone_key](v) if v is not None and self.tone_key in TONE else None
        return {"key": self.key, "label": self.label, "meaning": self.meaning, "unit": self.unit, "value": v,
                "approx": self.approx, "tone": tone,
                "history": [{"end": e.isoformat(), "value": x} for e, x in self.history],
                "sources": sorted(self.res.inputs)[:3] if self.res else []}


# ---- small arithmetic on Results, so every derived figure keeps its filings ------------------------------------
def _div(a: Result | None, b: Result | None) -> Result | None:
    if a is None or b is None or b.value == 0:
        return None
    return combine(a.value / b.value, a, b)


def _sub(a: Result | None, b: Result | None) -> Result | None:
    return None if a is None or b is None else combine(a.value - b.value, a, b)


def _add(a: Result | None, b: Result | None) -> Result | None:
    return None if a is None or b is None else combine(a.value + b.value, a, b)


def _pos(a: Result | None) -> Result | None:
    return a if a is not None and a.value > 0 else None


class Base:
    """The building-block figures at one quarter end (trailing twelve months for flows, the date for balances)."""

    def __init__(self, ctx: Context, end: date):
        self.ctx, self.end = ctx, end
        t, b = ctx.ttm, ctx.balance
        self.revenue = t("revenue", end)
        cogs = t("cost_of_revenue", end)
        self.gross_profit = t("gross_profit", end) or (_sub(self.revenue, cogs) if cogs else None)
        self.op_income, self.op_approx = self._operating_income()
        self.net_income = t("net_income", end)
        self.da, self.da_approx = t("depreciation_amortization", end), False
        if self.da is None and (dep := t("depreciation", end)) is not None:   # no D&A total: depreciation alone
            self.da, self.da_approx = dep, True
        self.ebitda = _add(self.op_income, self.da)
        self.ocf, self.capex = t("op_cash_flow", end), t("capex", end)
        self.fcf = _sub(self.ocf, self.capex)
        self.rnd = t("rnd_expense", end)
        self.interest = t("interest_expense", end)
        self.dividends = t("dividends_paid", end) if ctx.has("dividends_paid") else None
        self.cash, self.equity, self.assets = b("cash", end), b("equity", end), b("total_assets", end)
        self.cur_assets, self.cur_liab = b("current_assets", end), b("current_liabilities", end)
        self.debt = fundamentals.total_debt(ctx, end)
        self.net_debt = _sub(self.debt, self.cash)

    def _operating_income(self) -> tuple[Result | None, bool]:
        """Reported operating income; else revenue minus total costs; else pre-tax income plus interest. The last
        two are approximations and are marked as such on the page (the grader's rule stays stricter)."""
        t, end = self.ctx.ttm, self.end
        direct = t("operating_income", end)
        if direct is not None:
            return direct, False
        costs = t("costs_and_expenses", end)
        if self.revenue is not None and costs is not None:
            return _sub(self.revenue, costs), True
        pretax = t("pretax_income", end)
        if pretax is not None:
            interest = t("interest_expense", end)
            return (_add(pretax, interest) if interest is not None else pretax), True
        return None, False


def _years(ctx: Context) -> list[date]:
    q0 = ctx.q0
    if q0 is None:
        return []
    ends = [q0]
    while len(ends) < HISTORY_POINTS:
        prev = ctx.back(ends[-1], 4)
        if prev is None:
            break
        ends.append(prev)
    return sorted(ends)


def build_report(company_id: str, as_of: date, profile: dict, *, quote=None, shares=None, plans=None, share_history=None) -> dict:
    """`profile`: name, ticker, exchange, market, cik. `quote`: research.market.Quote or None.
    `shares`: (count, period_end, accession) or None. `plans`: research.text.Plans or None."""
    ctx = Context(company_id, as_of)
    ends = _years(ctx)
    if not ends:
        return {"supported": False, "company": profile,
                "reason": "No quarterly revenue in US-GAAP 10-K/10-Q filings. Foreign filers (20-F, IFRS), funds and "
                          "newly listed companies are not covered yet."}
    if ends[-1] < as_of - timedelta(days=STALE_DAYS):
        return {"supported": False, "company": profile,
                "reason": f"The latest revenue figure we can read is from {ends[-1].strftime('%B %Y')}. This company reports "
                          "revenue in a form this version does not recognise (banks, insurers and some other financial "
                          "companies do), so a report would be out of date."}
    bases = {e: Base(ctx, e) for e in ends}
    cur, ago1 = bases[ends[-1]], bases.get(ctx.back(ends[-1], 4))
    notes: list[str] = []

    def fig(key, label, meaning, unit, fn, tone_key=None, approx=False) -> Fig:
        hist = [(e, None if (r := fn(bases[e])) is None else r.value) for e in ends]
        return Fig(key, label, meaning, unit, fn(cur), hist, approx, tone_key)

    def growth_at(b: Base):
        prev = bases.get(ctx.back(b.end, 4))
        if prev is None or b.revenue is None or prev.revenue is None or prev.revenue.value <= 0:
            return None
        return combine(b.revenue.value / prev.revenue.value - 1, b.revenue, prev.revenue)

    def cagr(years: int):
        def f(b: Base):
            i = ends.index(b.end)
            if i - years < 0 or ends[i - years] not in bases:
                return None
            old, new = bases[ends[i - years]].revenue, b.revenue
            if old is None or new is None or old.value <= 0 or new.value <= 0:
                return None
            return combine((new.value / old.value) ** (1 / years) - 1, old, new)
        return f

    margin = lambda num: (lambda b: _div(getattr(b, num), _pos(b.revenue)))

    ebitda_approx = cur.op_approx or cur.da_approx

    # ---- sections ------------------------------------------------------------------------------------------
    growth = [
        fig("revenue", "Revenue (last 12 months)", "Total sales over the last four quarters", "usd", lambda b: b.revenue),
        fig("revenue_growth", "Revenue growth, year on year", "Last 12 months versus the 12 before", "pct", growth_at, "revenue_growth"),
        fig("revenue_cagr_3y", "Revenue growth per year, 3 years", "Average yearly growth over three years", "pct", cagr(3), "revenue_cagr_3y"),
        fig("revenue_cagr_5y", "Revenue growth per year, 5 years", "Average yearly growth over five years", "pct", cagr(5)),
    ]
    profit = [
        fig("gross_margin", "Gross margin", "Share of sales left after the direct cost of making the product", "pct", margin("gross_profit"), "gross_margin"),
        fig("operating_margin", "Operating margin", "Profit from the core business per dollar of sales", "pct", margin("op_income"), "operating_margin", cur.op_approx),
        fig("ebitda", "EBITDA", "Operating profit before depreciation and amortisation: a rough measure of cash earnings", "usd", lambda b: b.ebitda, None, ebitda_approx),
        fig("ebitda_margin", "EBITDA margin", "EBITDA per dollar of sales", "pct", lambda b: _div(b.ebitda, _pos(b.revenue)), None, ebitda_approx),
        fig("net_income", "Net profit", "Profit after interest and tax", "usd", lambda b: b.net_income),
        fig("net_margin", "Net margin", "Net profit per dollar of sales", "pct", margin("net_income"), "net_margin"),
    ]
    cash = [
        fig("op_cash_flow", "Cash from operations", "Cash the business generated from its day-to-day trading", "usd", lambda b: b.ocf),
        fig("capex", "Capital spending", "Cash spent on plant, equipment and facilities", "usd", lambda b: b.capex),
        fig("fcf", "Free cash flow", "Cash from operations minus capital spending: what is left for owners", "usd", lambda b: b.fcf),
        fig("fcf_margin", "Free-cash-flow margin", "Free cash flow per dollar of sales", "pct", lambda b: _div(b.fcf, _pos(b.revenue)), "fcf_margin"),
        fig("cash_conversion", "Cash conversion", "Free cash flow as a share of net profit: do profits turn into cash?", "pct", lambda b: _div(b.fcf, _pos(b.net_income)), "cash_conversion"),
    ]
    balance = [
        fig("cash", "Cash", "Cash and equivalents on the balance sheet", "usd", lambda b: b.cash),
        fig("debt", "Total debt", "Borrowings, current and long-term", "usd", lambda b: b.debt),
        fig("net_debt", "Net debt", "Debt minus cash; negative means more cash than debt", "usd", lambda b: b.net_debt),
        fig("equity", "Shareholders' equity", "What belongs to shareholders on the books", "usd", lambda b: b.equity),
        fig("assets", "Total assets", "Everything the company owns", "usd", lambda b: b.assets),
        fig("working_capital", "Working capital", "Short-term assets minus bills due within a year", "usd", lambda b: _sub(b.cur_assets, b.cur_liab)),
        fig("current_ratio", "Short-term cushion", "Short-term assets divided by bills due within a year", "x", lambda b: _div(b.cur_assets, b.cur_liab), "current_ratio"),
        fig("debt_to_ebitda", "Debt vs earnings", "Years of EBITDA it would take to repay all debt", "x",
            lambda b: (_div(b.debt, _pos(b.ebitda)) if b.debt is not None and b.debt.value > 0 else
                       (Result(0.0, b.debt.inputs) if b.debt is not None else None)), "debt_to_ebitda", ebitda_approx),
    ]
    reinvest = [
        fig("rnd", "Research and development", "Spending on developing new products and technology", "usd", lambda b: b.rnd),
        fig("rnd_share", "R&D as a share of sales", "Research spending per dollar of sales", "pct", lambda b: _div(b.rnd, _pos(b.revenue))),
        fig("capex_share", "Capital spending as a share of sales", "Spending on facilities per dollar of sales", "pct", lambda b: _div(b.capex, _pos(b.revenue))),
        fig("roic", "Return on capital", "Operating profit after tax per dollar of capital invested", "pct", lambda b: _roic(ctx, b), "roic"),
        fig("roce", "Return on capital employed", "Operating profit per dollar of capital employed (total assets less short-term bills)", "pct",
            lambda b: _div(b.op_income, _pos(_sub(b.assets, b.cur_liab))), "roce", cur.op_approx),
        fig("roe", "Return on equity", "Net profit per dollar of shareholders' equity", "pct", lambda b: _div(b.net_income, _pos(b.equity)), "roe"),
    ]
    if cur.dividends is not None:
        reinvest.append(fig("dividends", "Dividends paid", "Cash returned to shareholders as dividends", "usd", lambda b: b.dividends))
    for f in (*growth, *profit, *cash, *balance, *reinvest):          # a figure with no value is a gap, not zero
        if f.res is None:
            f.history = []
    if cur.op_approx:
        notes.append("This company does not report operating income. It is shown as revenue minus total costs "
                     "(or pre-tax profit plus interest), so operating margin, EBITDA and debt vs earnings are approximate.")
    if cur.da_approx:
        notes.append("This company does not report a depreciation-and-amortisation total, so EBITDA adds back depreciation "
                     "only and is slightly understated.")
    if cur.gross_profit is None:
        notes.append("This company does not report a gross profit line, so gross margin is not shown.")

    risk_res = risk.compute(ctx)
    risk_res["dividend_cut_history_5y"] = dividends.count_cuts(ctx)     # the single-quarter rule mistakes payment timing for cuts
    flags = _flags(risk_res, plans)
    economy = _economy(scenarios.compute(ctx))
    market = _market(quote, shares, cur)
    sections = [
        {"id": "growth", "title": "Is the business growing?", "figures": [f.as_dict() for f in growth], "reading": _read_growth(growth)},
        {"id": "profit", "title": "How profitable is it?", "figures": [f.as_dict() for f in profit], "reading": _read_profit(profit)},
        {"id": "cash", "title": "Does profit turn into cash?", "figures": [f.as_dict() for f in cash], "reading": _read_cash(cash)},
        {"id": "balance", "title": "How strong is the balance sheet?", "figures": [f.as_dict() for f in balance], "reading": _read_balance(balance)},
        {"id": "reinvest", "title": "What does it invest, and what does it earn on it?", "figures": [f.as_dict() for f in reinvest], "reading": _read_reinvest(reinvest)},
    ]
    all_figs = [f for s in sections for f in s["figures"]]
    toned = [f for f in all_figs if f["tone"]]
    out = {
        "supported": True, "company": profile, "as_of": as_of.isoformat(),
        "data_through": ends[-1].isoformat(), "points": [e.isoformat() for e in ends],
        "scorecard": [f for f in all_figs if f["key"] in ("revenue_growth", "operating_margin", "fcf_margin", "debt_to_ebitda", "roic", "current_ratio")],
        "tally": {t: sum(1 for f in toned if f["tone"] == t) for t in ("good", "watch", "warn")},
        "sections": sections, "risk_flags": flags, "economy": economy, "market": market,
        "plans": None if plans is None else plans.as_dict(), "notes": notes, "share_history": share_history or [],
        "missing": [f["label"] for f in all_figs if f["value"] is None],
    }
    out["analysis"] = analyse(out)
    out["quick_check"] = quick_check.run(out)
    return out


def _roic(ctx: Context, b: Base) -> Result | None:
    """Operating profit after tax over invested capital (equity + debt - cash), tax at the filer's own rate when it
    reports one, else the US statutory rate: the same definition the Fundamentals analyst is given."""
    if b.op_income is None or b.equity is None or b.debt is None or b.cash is None:
        return None
    ic = b.equity.value + b.debt.value - b.cash.value
    if ic <= 0:
        return None
    tax = ctx.ttm("income_tax_expense", b.end)
    pretax = ctx.ttm("pretax_income", b.end)
    rate = fundamentals.DEFAULT_TAX_RATE
    if tax is not None and pretax is not None and pretax.value > 0:
        rate = min(max(tax.value / pretax.value, 0.0), 0.5)
    return combine(b.op_income.value * (1 - rate) / ic, b.op_income, b.equity, b.debt, b.cash)


# ---- risk, economy, market -----------------------------------------------------------------------------------
def _flags(res: dict, plans) -> list[dict]:
    out = []

    def add(key, label, r, fmt, tone, meaning):
        if r is not None:
            out.append({"key": key, "label": label, "value": r.value, "detail": fmt(r.value), "tone": tone(r.value),
                        "meaning": meaning, "sources": sorted(r.inputs)[:3]})

    add("interest_coverage", "Interest cover", res.get("interest_coverage"), lambda v: f"{v:.1f}× earnings cover the interest bill",
        lambda v: "good" if v >= 8 else "warn" if v < 3 else "watch", "Under 3× is thin: a weak year could strain payments")
    add("cash_runway", "Cash runway", res.get("cash_runway_quarters"),
        lambda v: "Not burning cash" if v >= 40 else f"About {v:.0f} quarters of cash at the current burn",
        lambda v: "good" if v >= 16 else "warn" if v < 8 else "watch", "How long cash lasts if the company is losing money")
    add("current_ratio", "Short-term cushion", res.get("current_ratio"), lambda v: f"{v:.2f}× short-term assets over bills due",
        lambda v: "good" if v >= 1.5 else "warn" if v < 1.0 else "watch", "Under 1× means bills due within a year exceed liquid assets")
    add("dividend_cuts", "Dividend cuts, 5 years", res.get("dividend_cut_history_5y"),
        lambda v: "None" if v == 0 else f"{int(v)} cut{'s' if v > 1 else ''}", lambda v: "good" if v == 0 else "watch",
        "A cut is a sign that management lost confidence in cash flow")
    add("auditor_changes", "Auditor changes, 5 years", res.get("auditor_changes_5y"),
        lambda v: "None" if v == 0 else f"{int(v)} change{'s' if v > 1 else ''}", lambda v: "good" if v == 0 else "watch",
        "Auditor changes are sometimes a warning about accounting disputes")
    add("leverage_trend", "Debt-load trend", res.get("leverage_trend_8q"),
        lambda v: "Debt falling against earnings" if v < 0 else "Debt rising against earnings" if v > 0.05 else "Stable",
        lambda v: "good" if v <= 0 else "warn" if v > 0.5 else "watch", "Is debt growing faster than earnings?")
    if plans is not None:
        n = plans.going_concern_hits
        out.append({"key": "going_concern", "label": "Going-concern warning", "value": n,
                    "detail": "None found in the latest annual report" if n == 0 else f"{n} passage{'s' if n > 1 else ''} found in the latest annual report",
                    "tone": "good" if n == 0 else "warn", "meaning": "The auditor doubts the company can keep operating",
                    "sources": [plans.source["accession"]]})
    return out


def _economy(res: dict) -> list[dict]:
    spec = [("gdp_growth_yoy", "US economic growth", "Real GDP versus a year earlier", "pct"),
            ("unemployment_rate", "US unemployment", "Share of the workforce without a job", "pct"),
            ("yield_curve_10y_2y", "Yield curve (10-year minus 2-year)", "Below zero has often come before slowdowns", "pct"),
            ("credit_spread_baa", "Corporate credit spread", "Extra interest firms pay over Treasuries; rising means stress", "pct"),
            ("revenue_macro_beta", "Sensitivity of sales to the economy", "How strongly this company's revenue has moved with US GDP (1 = in step)", "x")]
    return [{"key": k, "label": l, "meaning": m, "unit": u, "value": res[k].value, "sources": sorted(res[k].inputs)[:2]}
            for k, l, m, u in spec if res.get(k) is not None]


def _market(quote, shares, cur: Base) -> dict | None:
    if quote is None:
        return None
    out = {"price": quote.price, "currency": quote.currency, "price_date": quote.as_of, "symbol": quote.symbol,
           "high_52w": quote.high_52w, "low_52w": quote.low_52w, "history": [{"date": d, "close": c} for d, c in quote.history]}
    if shares:
        count, end, accn = shares
        mcap = quote.price * count
        ev = mcap + (cur.net_debt.value if cur.net_debt is not None else 0.0)
        ratio = lambda num, den: None if num is None or den is None or den.value <= 0 else num / den.value   # noqa: E731
        out.update({
            "shares": count, "shares_as_of": end, "shares_source": accn, "market_cap": mcap, "enterprise_value": ev,
            "pe": ratio(mcap, cur.net_income), "ev_to_ebitda": ratio(ev, cur.ebitda), "price_to_sales": ratio(mcap, cur.revenue),
            "fcf_yield": None if cur.fcf is None else cur.fcf.value / mcap,
            "dividend_yield": None if cur.dividends is None else cur.dividends.value / mcap,
        })
    return out


# ---- plain sentences, written from the numbers -----------------------------------------------------------------
def _v(figs: list[Fig], key: str) -> Fig:
    return next(f for f in figs if f.key == key)


def _money(x: float) -> str:
    a = abs(x)
    s = f"${a / 1e12:.2f} trillion" if a >= 1e12 else f"${a / 1e9:.1f} billion" if a >= 1e9 else f"${a / 1e6:.0f} million"
    return ("-" if x < 0 else "") + s


def _pc(x: float) -> str:
    return f"{x * 100:.1f}%"


def _trend(f: Fig, unit_pts: bool = True) -> str | None:
    h = [x for _, x in f.history if x is not None]
    if len(h) < 3:
        return None
    first, last = h[0], h[-1]
    d = (last - first) * 100
    if abs(d) < 0.5:
        return f"{f.label.lower()} has been steady at about {_pc(last)}"
    return f"{f.label.lower()} moved from {_pc(first)} to {_pc(last)} over {len(h) - 1} years"


def _read_growth(f: list[Fig]) -> list[str]:
    rev, g, c3 = _v(f, "revenue"), _v(f, "revenue_growth"), _v(f, "revenue_cagr_3y")
    out = []
    if rev.res and g.res:
        out.append(f"Sales were {_money(rev.res.value)} over the last 12 months, "
                   f"{'up' if g.res.value >= 0 else 'down'} {_pc(abs(g.res.value))} on the 12 months before.")
    h = [x for _, x in g.history if x is not None]
    if len(h) >= 3:
        up = sum(1 for x in h if x > 0)
        out.append(f"Revenue grew in {up} of the last {len(h)} years" + (", so growth has been steady." if up == len(h) else "."))
    if c3.res:
        out.append(f"Over three years it has grown {_pc(c3.res.value)} a year on average.")
    return out


def _read_profit(f: list[Fig]) -> list[str]:
    om, nm, gm = _v(f, "operating_margin"), _v(f, "net_margin"), _v(f, "gross_margin")
    out = []
    if om.res:
        out.append(f"For every dollar of sales the core business keeps {om.res.value * 100:.0f} cents as operating profit"
                   + (" (approximate: see notes)." if om.approx else "."))
    t = _trend(om)
    if t:
        out.append(t[0].upper() + t[1:] + ".")
    if gm.res and nm.res:
        out.append(f"Gross margin is {_pc(gm.res.value)} and net margin {_pc(nm.res.value)}.")
    return out


def _read_cash(f: list[Fig]) -> list[str]:
    fcf, fm, cc = _v(f, "fcf"), _v(f, "fcf_margin"), _v(f, "cash_conversion")
    out = []
    if fcf.res:
        out.append(f"Free cash flow over the last 12 months was {_money(fcf.res.value)}" +
                   (f", {_pc(fm.res.value)} of sales." if fm.res else "."))
    if cc.res:
        out.append(f"Each dollar of net profit turned into {cc.res.value:.2f} dollars of free cash.")
    return out


def _read_balance(f: list[Fig]) -> list[str]:
    nd, cr, de = _v(f, "net_debt"), _v(f, "current_ratio"), _v(f, "debt_to_ebitda")
    out = []
    if nd.res:
        out.append("The company holds more cash than debt: " + _money(-nd.res.value) + " net cash." if nd.res.value < 0
                   else f"Net debt is {_money(nd.res.value)}.")
    if de.res and de.res.value > 0:
        out.append(f"Repaying all debt would take about {de.res.value:.1f} years of EBITDA.")
    if cr.res:
        out.append(f"Short-term assets cover bills due within a year {cr.res.value:.2f} times.")
    return out


def _read_reinvest(f: list[Fig]) -> list[str]:
    rnd, rs, cs, roic = _v(f, "rnd"), _v(f, "rnd_share"), _v(f, "capex_share"), _v(f, "roic")
    out = []
    if rnd.res and rs.res:
        out.append(f"It spends {_money(rnd.res.value)} a year on research and development, {_pc(rs.res.value)} of sales.")
    if cs.res:
        out.append(f"Capital spending is {_pc(cs.res.value)} of sales.")
    if roic.res:
        out.append(f"Each dollar invested in the business earns {_pc(roic.res.value)} a year after tax.")
    return out
