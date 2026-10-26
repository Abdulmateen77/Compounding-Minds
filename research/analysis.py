"""The investor lenses, the valuation and the overall view: all rules and arithmetic, no model.

Each lens is the checklist from principles/<investor>.md turned into checks over the report's own figures. A check
returns pass / partial / fail / unknown, names the principle it comes from, and shows the number it looked at. A
lens's fit is the share of known checks passed (partial counts half). The overall view combines the lenses with the
valuation in a few plain rules (see `overall`). It describes the evidence and the price; it is not personal advice.
"""
from __future__ import annotations

import re
import statistics
from pathlib import Path

from . import valuation as V

PRINCIPLES_DIR = Path(__file__).resolve().parent.parent / "principles"

# Where each rule really comes from, as verified in principles/SOURCES.md (the rule files keep older wording because
# they are the agents' prompts and must not change after the replay).
CITATION = {
    "buffett.01": "Berkshire letter 1986, appendix on owner earnings", "buffett.02": "Berkshire acquisition criteria (2014 letter)",
    "buffett.03": "Berkshire letter 1986, owner earnings", "buffett.04": "Berkshire acquisition criteria (2014 letter)",
    "buffett.05": "Berkshire owner's manual, principle 7", "buffett.06": "Derived from buffett.01 and buffett.03",
    "munger.01": "Munger, Harvard School speech, 1986 (“invert, always invert”)", "munger.02": "Munger, Harvard School speech, 1986",
    "munger.03": "Munger, Wesco Financial letter, 1990", "munger.04": "Derived rule", "munger.05": "Derived rule",
    "munger.06": "Munger, “A Lesson on Elementary Worldly Wisdom”, 1994",
    "dalio.01": "Dalio, Principles (decisions as bets)", "dalio.02": "Dalio, How the Economic Machine Works",
    "dalio.03": "Dalio, How the Economic Machine Works", "dalio.04": "Dalio, Principles (text not yet verified)",
    "graham.01": "Graham, The Intelligent Investor ch. 20 (“margin of safety”)",
    "graham.02": "Graham, The Intelligent Investor (chapter not yet verified)",
    "graham.03": "Graham, The Intelligent Investor ch. 14 (earnings stability)",
    "graham.04": "Graham, The Intelligent Investor ch. 14 (moderate price against average earnings; our thresholds)",
    "graham.05": "Graham, The Intelligent Investor ch. 14 (strong financial condition)",
    "graham.06": "Graham, The Intelligent Investor ch. 14 (dividend record)",
}
INVESTORS = [("buffett", "Warren Buffett", "Is it a durable business that turns profit into cash?"),
             ("munger", "Charlie Munger", "How could this business fail?"),
             ("lynch", "Peter Lynch", "What kind of stock is it, and is the price fair for its growth?"),
             ("dalio", "Ray Dalio", "How exposed is it to the cycle, and what is the range of outcomes?"),
             ("jhunjhunwala", "Rakesh Jhunjhunwala", "A long-term outperformer with honest leadership, cash and high returns?")]
# What each investor looks for, three points each, distilled from principles/guides/<investor>.md, and the book it is from.
LOOKS_FOR = {
    "buffett": ["A simple business with a durable moat and a long, consistent record",
                "High returns on capital without leaning on debt, and profit that turns into cash",
                "A price clearly below a conservative value, for a ten-year hold"],
    "munger": ["Every way the business could fail, checked before any upside",
               "Interest cover, cash runway and debt that is not rising against earnings",
               "Honest, owner-minded managers and a clean record (auditors, dividends)"],
    "graham": ["A margin of safety: price well below a cautious value",
               "Current ratio of 2 or more and debt within working capital",
               "Profits every year and a price under 15 times average earnings"],
    "lynch": ["Which of six kinds of stock it is, judged by that kind's numbers",
              "A P/E no higher than the growth rate",
              "Low debt and net cash, and no hot-stock hype"],
    "dalio": ["The range of outcomes, not a single forecast",
              "How strongly sales move with the economy and where the cycle stands",
              "A bet that survives the bad case"],
    "jhunjhunwala": ["Growth well above the market's, for years",
                     "Return on capital above 20% and strong free cash flow",
                     "Honest leadership, low debt and a sensible P/E"],
}
BOOK = {"buffett": "The Warren Buffett Way", "munger": "Poor Charlie's Almanack", "graham": "The Intelligent Investor",
        "lynch": "One Up on Wall Street", "dalio": "Principles", "jhunjhunwala": "your notes on his interview"}
# Lenses tested against what happened next (research/backtest.py). The others are shown without that claim.
BACKTESTED = {"buffett", "munger"}
CAVEAT = {"jhunjhunwala": "From your notes on his interview. The figures there are the speaker's claims and are unverified."}


GUIDES_DIR = PRINCIPLES_DIR / "guides"


def _find_line(pid: str) -> list[str] | None:
    """The `id | rule | how we check | source` line for a principle: the guide first, then the agents' file."""
    name = pid.split(".")[0]
    for folder in (GUIDES_DIR, PRINCIPLES_DIR):
        try:
            for line in (folder / f"{name}.md").read_text(encoding="utf-8").splitlines():
                if line.startswith(pid + " |"):
                    return [x.strip() for x in line.split("|")]
        except OSError:
            continue
    return None


def principle_text(pid: str) -> str:
    """The rule in our own words."""
    row = _find_line(pid)
    return row[1] if row and len(row) > 1 else pid


def principle_source(pid: str) -> str:
    row = _find_line(pid)
    return row[3] if row and len(row) > 3 else ""


def guide_text(key: str) -> str:
    """A guide without its machine-readable checks and source map: what the model is given to write from."""
    try:
        text = (GUIDES_DIR / f"{key}.md").read_text(encoding="utf-8")
    except OSError:
        return ""
    for marker in ("## Checks", "## Source map"):
        i = text.find(marker)
        if i != -1:
            text = text[:i]
    return text.strip()


class Facts:
    """Convenient access to the report's figures."""

    def __init__(self, report: dict, val: dict):
        self.figs = {f["key"]: f for s in report["sections"] for f in s["figures"]}
        self.flags = {f["key"]: f for f in report.get("risk_flags", [])}
        self.econ = {e["key"]: e for e in report.get("economy", [])}
        self.market, self.val = report.get("market"), val

    def v(self, key: str) -> float | None:
        f = self.figs.get(key)
        return None if f is None else f["value"]

    def hist(self, key: str) -> list[float]:
        f = self.figs.get(key)
        return [] if f is None else [h["value"] for h in f["history"] if h["value"] is not None]

    def tone(self, key: str) -> str | None:
        f = self.figs.get(key)
        return None if f is None else f["tone"]


def _check(pid: str, what: str, result: str, shown: str) -> dict:
    return {"id": pid, "principle": principle_text(pid), "source": CITATION.get(pid) or principle_source(pid), "check": what,
            "result": result, "shown": shown}


def _tone_result(tone: str | None) -> str:
    return {"good": "pass", "watch": "partial", "warn": "fail"}.get(tone or "", "unknown")


def _worst(*results: str) -> str:
    known = [r for r in results if r != "unknown"]
    if not known:
        return "unknown"
    return "fail" if "fail" in known else "partial" if "partial" in known else "pass"


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


# ---- Buffett -------------------------------------------------------------------------------------------------
def buffett(f: Facts) -> list[dict]:
    cc, roic, lev = f.v("cash_conversion"), f.v("roic"), f.v("debt_to_ebitda")
    fm, cx = f.hist("fcf_margin"), f.hist("capex_share")
    ni, om = f.hist("net_income"), f.hist("operating_margin")
    out = [
        _check("buffett.01", "Does profit turn into free cash?", _tone_result(f.tone("cash_conversion")),
               "n/a" if cc is None else f"{cc:.2f} dollars of free cash per dollar of profit"),
        _check("buffett.02", "Good return on capital without heavy debt?",
               _worst(_tone_result(f.tone("roic")), _tone_result(f.tone("debt_to_ebitda"))),
               f"return on capital {_pct(roic)}, debt {'n/a' if lev is None else f'{lev:.1f}× EBITDA'}"),
    ]
    if len(fm) >= 3 and len(cx) >= 3:
        up, capex_up = fm[-1] >= fm[-3], cx[-1] > cx[-3] * 1.1
        r = "pass" if up and not capex_up else "fail" if (not up and capex_up) else "partial"
        out.append(_check("buffett.03", "Is cash conversion improving without rising reinvestment?", r,
                          f"cash margin {_pct(fm[-3])} → {_pct(fm[-1])}, capital spending {_pct(cx[-3])} → {_pct(cx[-1])} of sales"))
    else:
        out.append(_check("buffett.03", "Is cash conversion improving without rising reinvestment?", "unknown", "not enough history"))
    if len(ni) >= 4 and len(om) >= 4:
        loss = any(x <= 0 for x in ni[-5:])
        spread = max(om[-5:]) - min(om[-5:])
        out.append(_check("buffett.04", "Consistent earning power, not one good year?",
                          "fail" if loss else "pass" if spread <= 0.08 else "partial",
                          f"{'a loss year in the last five' if loss else 'profitable every year'}; operating margin ranged {_pct(min(om[-5:]))} to {_pct(max(om[-5:]))}"))
    else:
        out.append(_check("buffett.04", "Consistent earning power, not one good year?", "unknown", "not enough history"))
    ic = f.flags.get("interest_coverage")
    out.append(_check("buffett.05", "Leverage that could force a sale at the wrong time?",
                      _worst(_tone_result(f.tone("debt_to_ebitda")), _tone_result(ic["tone"] if ic else None)),
                      f"debt {'n/a' if lev is None else f'{lev:.1f}× EBITDA'}" + (f", interest cover {ic['value']:.1f}×" if ic else "")))
    if len(fm) >= 3 and len(cx) >= 3:
        r = "pass" if fm[-1] > fm[-3] and cx[-1] < cx[-3] else "fail" if fm[-1] < fm[-3] and cx[-1] > cx[-3] else "partial"
        out.append(_check("buffett.06", "Margins rising while capital intensity falls?", r,
                          f"cash margin {'up' if fm[-1] > fm[-3] else 'down'}, capital spending {'down' if cx[-1] < cx[-3] else 'up'} over two years"))
    return out


# ---- Munger --------------------------------------------------------------------------------------------------
def munger(f: Facts) -> list[dict]:
    fl = f.flags
    g = lambda k: fl.get(k)                                                       # noqa: E731
    out = []
    ic, rw, lt = g("interest_coverage"), g("cash_runway"), g("leverage_trend")
    if ic:
        out.append(_check("munger.02", "Could a bad year strain the interest bill?", _tone_result(ic["tone"]), ic["detail"]))
    if rw or lt:
        r = _worst(_tone_result(rw["tone"]) if rw else "unknown", _tone_result(lt["tone"]) if lt else "unknown")
        out.append(_check("munger.03", "Short cash runway while debt rises?", r,
                          "; ".join(x["detail"] for x in (rw, lt) if x)))
    dc, ac = g("dividend_cuts"), g("auditor_changes")
    if dc or ac:
        r = _worst(_tone_result(dc["tone"]) if dc else "unknown", _tone_result(ac["tone"]) if ac else "unknown")
        out.append(_check("munger.04", "Dividend cuts or auditor changes in the past five years?", r,
                          "; ".join(f"{x['label'].split(',')[0].lower()}: {x['detail'].lower()}" for x in (dc, ac) if x)))
    gc = g("going_concern")
    if gc:
        out.append(_check("munger.05", "Going-concern language in the latest annual report?", _tone_result(gc["tone"]), gc["detail"]))
    cr = g("current_ratio")
    if cr and ic:
        r = "pass" if cr["value"] >= 2 and ic["value"] >= 10 else "partial" if cr["value"] >= 1 else "fail"
        out.append(_check("munger.06", "A strong balance sheet means a low base rate of distress", r,
                          f"short-term cushion {cr['value']:.2f}×, interest cover {ic['value']:.1f}×"))
    elif cr:
        out.append(_check("munger.06", "A strong balance sheet means a low base rate of distress",
                          "pass" if cr["value"] >= 2 else "partial" if cr["value"] >= 1 else "fail",
                          f"short-term cushion {cr['value']:.2f}×"))
    return out


# ---- Graham --------------------------------------------------------------------------------------------------
def _pe3(f: Facts) -> float | None:
    m, ni = f.market, f.hist("net_income")
    if m and m.get("market_cap") and len(ni) >= 3 and sum(ni[-3:]) > 0:
        return m["market_cap"] / (sum(ni[-3:]) / 3)
    return None


def money_short(x: float) -> str:
    a = abs(x)
    s = f"${a / 1e12:.1f}T" if a >= 1e12 else f"${a / 1e9:.1f}B" if a >= 1e9 else f"${a / 1e6:.0f}M"
    return ("-" if x < 0 else "") + s


def graham(f: Facts) -> list[dict]:
    """Graham's seven tests for a cautious investor (Intelligent Investor ch. 14) and the margin of safety (ch. 20)."""
    val, m, out = f.val, f.market, []
    cr, wc, debt = f.v("current_ratio"), f.v("working_capital"), f.v("debt")
    if cr is not None:
        r = "pass" if cr >= 2 else "partial" if cr >= 1.5 else "fail"
        if wc is not None and debt is not None and debt > wc:
            r = _worst(r, "partial")
        shown = f"short-term cushion {cr:.2f}×"
        if wc is not None and debt is not None:
            shown += f"; debt {money_short(debt)} against working capital {money_short(wc)}"
        out.append(_check("graham.g2", "Strong financial condition: current ratio of at least 2, debt within working capital", r, shown))
    ni = f.hist("net_income")
    if len(ni) >= 4:
        loss = any(x <= 0 for x in ni[-5:])
        out.append(_check("graham.g3", "Earnings stability: a profit in every year", "fail" if loss else "pass",
                          "a loss year in the last five" if loss else "profitable in each of the last five years"))
    div, dc = f.hist("dividends"), f.flags.get("dividend_cuts")
    if div:
        ok = dc is not None and dc["value"] == 0 and all(x > 0 for x in div[-5:])
        out.append(_check("graham.g4", "Dividend record: unbroken payments", "pass" if ok else "partial",
                          "pays a dividend with no cuts in five years (Graham asked for twenty)" if ok else "the dividend has been cut or interrupted"))
    if len(ni) >= 6 and sum(ni[:3]) > 0:
        gr = sum(ni[-3:]) / sum(ni[:3]) - 1
        out.append(_check("graham.g5", "Earnings growth of at least a third over the period",
                          "pass" if gr >= 1 / 3 else "partial" if gr > 0 else "fail",
                          f"profit up {gr * 100:.0f}% between the first and last three years we have (about six years; Graham used ten)"))
    pe3 = _pe3(f)
    out.append(_check("graham.g6", "Price no more than 15 times the average of the last three years' profit",
                      "unknown" if pe3 is None else "pass" if pe3 <= 15 else "partial" if pe3 <= 22.5 else "fail",
                      "n/a" if pe3 is None else f"{pe3:.1f}× average profit of the last three years"))
    eq = f.v("equity")
    if m and m.get("market_cap") and eq and eq > 0:
        pb = m["market_cap"] / eq
        prod = None if pe3 is None else pe3 * pb
        ok = pb <= 1.5 or (prod is not None and prod <= 22.5)
        out.append(_check("graham.g7", "Price no more than 1.5 times book value (or P/E times P/B no more than 22.5)",
                          "pass" if ok else "partial" if (prod is not None and prod <= 45) or pb <= 3 else "fail",
                          f"{pb:.1f}× book value" + ("" if prod is None else f"; P/E times P/B = {prod:.0f}")))
    pos = val.get("position") if val.get("available") else None
    pv = val.get("price_vs_base")
    if pv is None:
        shown = "n/a"
    elif pv > 1:
        shown = f"price is {pv + 1:.1f}× the base-case value"
    else:
        shown = f"price is {abs(pv) * 100:.0f}% {'above' if pv > 0 else 'below'} the base-case value"
    out.append(_check("graham.g8", "Margin of safety: a price well below a cautious estimate of value",
                      {"below_bear": "pass", "below_base": "pass", "near_base": "partial", "above_base": "fail", "above_bull": "fail"}.get(pos or "", "unknown"),
                      shown))
    ig = val.get("implied_growth")
    g0 = val["scenarios"][1]["start_growth"] if val.get("available") else None
    if ig is not None and g0 is not None:
        out.append(_check("graham.g8b", "Is it paying for growth the business has not delivered?",
                          "pass" if ig <= g0 else "partial" if ig <= g0 + 0.03 else "fail",
                          f"price assumes {_pct(ig)} a year; the company has delivered about {_pct(g0)}"))
    elif g0 is not None and pos == "above_bull":
        out.append(_check("graham.g8b", "Is it paying for growth the business has not delivered?", "fail",
                          f"the price assumes more than 45% a year; the company has delivered about {_pct(g0)}"))
    return out


# ---- Lynch ---------------------------------------------------------------------------------------------------
CYCLICAL_SIC = ("10", "12", "13", "15", "16", "17", "24", "26", "29", "30", "33", "37", "40", "45")


def lynch_category(f: Facts, sic: str | None) -> tuple[str, str]:
    """Lynch's six kinds of stock, as far as the financial statements can tell. A best guess with the reason."""
    ni, om, rg = f.hist("net_income"), f.hist("operating_margin"), f.hist("revenue_growth")
    g3, g5 = f.v("revenue_cagr_3y"), f.v("revenue_cagr_5y")
    g = g3 if g3 is not None else g5
    latest_ni = f.v("net_income")
    if latest_ni is not None and latest_ni <= 0 and any(x > 0 for x in ni[:-1]):
        return "Turnaround", "profit has turned negative after profitable years; the question is whether it survives and recovers"
    if ni and all(x <= 0 for x in ni[-4:]):
        return "No profits yet", "it has not made a profit in recent years, so none of Lynch's six kinds fits well"
    swings = len(om) >= 4 and (max(om[-5:]) - min(om[-5:])) >= 0.10
    falls = sum(1 for x in rg[-6:] if x < 0)
    if (sic and sic[:2] in CYCLICAL_SIC) or falls >= 2 or swings:
        if sic and sic[:2] in CYCLICAL_SIC:
            why = "its industry rises and falls with the economy"
        elif falls >= 2:
            why = f"sales fell in {falls} of the last {len(rg[-6:])} years"
        else:
            why = f"its operating margin has swung by {(max(om[-5:]) - min(om[-5:])) * 100:.0f} points"
        return "Cyclical", why
    if g is None:
        return "Unclear", "not enough revenue history"
    if g >= 0.15:
        return "Fast grower", f"sales have grown {g * 100:.0f}% a year, close to Lynch's 20 to 25 percent territory"
    if g >= 0.05:
        return "Stalwart", f"sales have grown {g * 100:.0f}% a year: a large steady company in the 10 to 12 percent range"
    return "Slow grower", f"sales have grown only {g * 100:.0f}% a year, about the pace of the economy"


def lynch(f: Facts, sic: str | None = None) -> tuple[list[dict], dict]:
    m, out = f.market, []
    cat, why = lynch_category(f, sic)
    mcap = (m or {}).get("market_cap")
    pe = (m or {}).get("pe")
    ni = f.hist("net_income")
    growth = None
    if len(ni) >= 4 and ni[-4] > 0 and ni[-1] > 0:
        growth = (ni[-1] / ni[-4]) ** (1 / 3) - 1                  # profit growth over the last three years
    elif f.v("revenue_cagr_3y") is not None:
        growth = f.v("revenue_cagr_3y")
    note = {"category": cat, "why": why}
    if pe is None or growth is None:
        r, shown = "unknown", "n/a"
    elif growth <= 0:
        r, shown = ("fail" if pe > 15 else "partial"), f"P/E {pe:.1f} with no profit growth"
    else:
        ratio = pe / (growth * 100)
        r = "pass" if ratio <= 1 else "partial" if ratio <= 2 else "fail"
        shown = f"P/E {pe:.1f} against growth of {growth * 100:.1f}% a year (ratio {ratio:.2f})"
    out.append(_check("lynch.g2", "Is the P/E near the growth rate? (half is very good, double is a warning)", r, shown))
    dy = (m or {}).get("dividend_yield") or 0.0
    if pe is not None and growth is not None and pe > 0:
        r3 = (growth * 100 + dy * 100) / pe
        out.append(_check("lynch.g3", "(Growth plus dividend yield) over P/E: 2 or better is good, under 1 is poor",
                          "pass" if r3 >= 2 else "partial" if r3 >= 1 else "fail", f"{r3:.2f}"))
    eq, debt, cash = f.v("equity"), f.v("debt"), f.v("cash")
    if eq is not None and debt is not None and eq + debt > 0:
        share = debt / (eq + debt)
        out.append(_check("lynch.g4", "Balance sheet: debt a small share of capital (a normal company is about a quarter)",
                          "pass" if share <= 0.25 else "partial" if share <= 0.5 else "fail", f"debt is {share * 100:.0f}% of equity plus debt"))
    if mcap and cash is not None and debt is not None:
        nc = (cash - debt) / mcap
        out.append(_check("lynch.g5", "Cash net of debt lowers the price you really pay",
                          "pass" if nc > 0 else "partial" if nc >= -0.25 else "fail",
                          f"{'net cash' if nc > 0 else 'net debt'} equal to {abs(nc) * 100:.1f}% of market value"))
    now, c5 = f.v("revenue_growth"), f.v("revenue_cagr_5y")
    if pe is not None and now is not None:
        hot = pe >= 50
        shown = f"P/E {pe:.0f}; growth now {_pct(now)}" + ("" if c5 is None else f" against {_pct(c5)} a year over five years")
        out.append(_check("lynch.g6", "Beware the hot stock: a very high P/E with growth that is slowing",
                          "fail" if hot and c5 is not None and now < c5 else "partial" if hot else "pass", shown))
    om = f.hist("operating_margin")
    lev = f.v("debt_to_ebitda")
    if cat == "Cyclical" and len(om) >= 4:
        peak = om[-1] >= max(om[-5:]) - 0.01
        out.append(_check("lynch.g7", "Cyclicals: beware buying at peak earnings, when the P/E looks lowest",
                          "fail" if peak else "pass",
                          "operating margin is at the top of its five-year range" if peak else "operating margin is below its five-year high"))
    elif cat == "Fast grower":
        fm = f.v("fcf_margin")
        fin = "pass" if debt is not None and eq is not None and debt <= eq * 0.33 else "partial"
        cashr = "pass" if fm is not None and fm > 0 else "fail" if fm is not None else "unknown"
        out.append(_check("lynch.g7", "Fast growers: strong enough finances to fund the expansion", _worst(fin, cashr),
                          f"free-cash-flow margin {_pct(fm)}"))
    elif cat == "Turnaround":
        ic = f.flags.get("interest_coverage")
        out.append(_check("lynch.g7", "Turnarounds: survival decides everything, and debt decides survival",
                          _worst(_tone_result(f.tone("debt_to_ebitda")), _tone_result(ic["tone"] if ic else None)),
                          "debt " + ("n/a" if lev is None else f"{lev:.1f}× EBITDA")))
    return out, note


# ---- Jhunjhunwala --------------------------------------------------------------------------------------------
def jhunjhunwala(f: Facts) -> list[dict]:
    m, out = f.market, []
    g3, pe, roic = f.v("revenue_cagr_3y"), (m or {}).get("pe"), f.v("roic")
    cc, lev = f.v("cash_conversion"), f.v("debt_to_ebitda")
    out.append(_check("jhunjhunwala.g1", "Growth well above the market's, sustained for years",
                      "unknown" if g3 is None else "pass" if g3 >= 0.20 else "partial" if g3 >= 0.12 else "fail",
                      "n/a" if g3 is None else f"sales have grown {g3 * 100:.1f}% a year over three years (market pace about 12%)"))
    out.append(_check("jhunjhunwala.g2", "Price matters more than popularity: avoid very high P/Es",
                      "unknown" if pe is None else "pass" if pe <= 20 else "partial" if pe <= 50 else "fail",
                      "n/a" if pe is None else f"P/E {pe:.1f} (the note says to compare within the sector)"))
    out.append(_check("jhunjhunwala.g3", "Strong free cash flow",
                      _worst(_tone_result(f.tone("fcf_margin")), _tone_result(f.tone("cash_conversion"))),
                      f"free-cash-flow margin {_pct(f.v('fcf_margin'))}; cash conversion " + ("n/a" if cc is None else f"{cc:.2f}")))
    out.append(_check("jhunjhunwala.g4", "Return on capital employed above about 20 percent",
                      "unknown" if roic is None else "pass" if roic >= 0.20 else "partial" if roic >= 0.12 else "fail",
                      "n/a" if roic is None else f"return on capital {roic * 100:.1f}%"))
    ic = f.flags.get("interest_coverage")
    shown = "debt " + ("n/a" if lev is None else f"{lev:.1f}× EBITDA") + (f", interest cover {ic['value']:.1f}×" if ic else "")
    out.append(_check("jhunjhunwala.g5", "Avoid heavy or unmanaged debt",
                      _worst(_tone_result(f.tone("debt_to_ebitda")), _tone_result(ic["tone"] if ic else None)), shown))
    out.append(_check("jhunjhunwala.g6", "Promoters hold more than about half; institutions high, retail low", "unknown",
                      "ownership data is not in the filings we load"))
    out.append(_check("jhunjhunwala.g7", "A near-monopoly with a large order book", "unknown", "needs the reader's judgement of the business"))
    return out


# ---- Dalio ---------------------------------------------------------------------------------------------------
def dalio(f: Facts) -> list[dict]:
    out = []
    g = f.hist("revenue_growth")
    if len(g) >= 4:
        sd = statistics.pstdev(g[-5:])
        out.append(_check("dalio.01", "How wide is the range of past outcomes?", "pass" if sd <= 0.06 else "partial" if sd <= 0.15 else "fail",
                          f"yearly revenue growth has ranged {_pct(min(g[-5:]))} to {_pct(max(g[-5:]))}"))
    beta = f.econ.get("revenue_macro_beta")
    if beta:
        b = abs(beta["value"])
        out.append(_check("dalio.02", "Does the economy move this company's sales?", "pass" if b <= 1.5 else "partial" if b <= 3 else "fail",
                          f"sales have moved {b:.1f}× as much as US GDP"))
    yc, cs = f.econ.get("yield_curve_10y_2y"), f.econ.get("credit_spread_baa")
    if yc and cs:
        r = "fail" if yc["value"] < 0 else "partial" if cs["value"] > 0.025 else "pass"
        out.append(_check("dalio.03", "Is the cycle flashing warning signs?", r,
                          f"yield curve {yc['value'] * 100:+.2f} points, corporate credit spread {cs['value'] * 100:.2f} points"))
    c5, now = f.v("revenue_cagr_5y"), f.v("revenue_growth")
    if c5 is not None and now is not None:
        out.append(_check("dalio.04", "Is recent growth above or below its long-run pace?", "pass" if now >= c5 else "partial",
                          f"growth now {_pct(now)} against {_pct(c5)} a year over five years"))
    return out


LENS = {"buffett": buffett, "munger": munger, "graham": graham, "dalio": dalio, "jhunjhunwala": jhunjhunwala}


def fit(checks: list[dict]) -> float | None:
    known = [c for c in checks if c["result"] != "unknown"]
    if len(known) < 2:
        return None
    return sum({"pass": 1.0, "partial": 0.5, "fail": 0.0}[c["result"]] for c in known) / len(known)


def fit_word(x: float | None, kind: str) -> str:
    if x is None:
        return "Not enough data"
    if kind == "munger":
        return "Few ways to fail" if x >= 0.7 else "Some risks to watch" if x >= 0.4 else "Real risks"
    return "Fits well" if x >= 0.7 else "Partly fits" if x >= 0.4 else "Does not fit"


# ---- the overall view ----------------------------------------------------------------------------------------
def overall(fits: dict[str, float | None], val: dict) -> dict:
    q, s = fits.get("buffett"), fits.get("munger")
    pos = val.get("position") if val.get("available") else None
    cheap, rich = pos in ("below_bear", "below_base", "near_base"), pos in ("above_base", "above_bull")
    if s is not None and s < 0.4:
        return {"key": "avoid", "tone": "warn", "headline": "Avoid for now: real signs of financial trouble",
                "why": "The failure checks flag real risks. A good price does not fix a business that may not survive a bad year."}
    if q is not None and q >= 0.65 and cheap:
        return {"key": "look", "tone": "good", "headline": "Worth a closer look: a strong business at a price the numbers can support",
                "why": "It passes most of the quality checks, and the share price is not above what its record supports."}
    if q is not None and q >= 0.65 and rich:
        return {"key": "wait", "tone": "watch", "headline": "A good business, but the price already assumes a lot",
                "why": "Quality is high, but the share price is above what its record supports. Waiting for a lower price, or accepting a lower return, is the careful position."}
    if q is not None and q < 0.4:
        return {"key": "weak", "tone": "warn", "headline": "Weak on the quality checks: be careful",
                "why": "It fails most of the checks that separate durable businesses from ordinary ones."}
    return {"key": "mixed", "tone": "watch", "headline": "Mixed evidence: some strengths, some doubts",
            "why": "The checks do not point one way. The decision depends on which strengths and weaknesses matter to you."}


def future(val: dict) -> dict | None:
    if not val.get("available"):
        return None
    rows = []
    for s in val["scenarios"]:
        pick = lambda p, i: None if p is None else p[i - 1]                       # noqa: E731
        rows.append({"name": s["name"], "start_growth": s["start_growth"], "value_per_share": s["value_per_share"], "equity_value": s["equity_value"],
                     "revenue": {str(y): pick(s["revenue_path"], y) for y in (1, 3, 5, 10)},
                     "fcf": {str(y): pick(s["fcf_path"], y) for y in (1, 3, 5, 10)}})
    return {"scenarios": rows}


CALL = {"invest": "Would invest", "wait": "Would wait", "avoid": "Would not invest"}
PRICE_MINDED = {"buffett", "lynch", "jhunjhunwala"}      # their own rules include the price paid


def decide(key: str, fit: float | None, val: dict) -> dict:
    """Each investor's call on their own checks. Price-minded investors wait when the price is above even the optimistic case."""
    if fit is None:
        return {"call": "wait", "label": "Not enough data", "why": "Too few of this investor's checks could be run."}
    if fit >= 0.7:
        if key in PRICE_MINDED and val.get("available") and val.get("position") == "above_bull":
            return {"call": "wait", "label": CALL["wait"], "why": "Passes most checks, but the price is above even the optimistic case."}
        return {"call": "invest", "label": CALL["invest"], "why": "Passes most of this investor's checks."}
    if fit >= 0.4:
        return {"call": "wait", "label": CALL["wait"], "why": "Some checks pass and some fail: not enough to commit."}
    return {"call": "avoid", "label": CALL["avoid"], "why": "Fails most of this investor's checks."}


def panel(lenses: list[dict]) -> dict:
    n = {k: sum(1 for l in lenses if l["decision"]["call"] == k) for k in CALL}
    total = len(lenses)
    if n["invest"] > total / 2:
        head, tone = f"{n['invest']} of {total} investors would invest", "good"
    elif n["avoid"] > total / 2:
        head, tone = f"{n['avoid']} of {total} investors would not invest", "warn"
    else:
        head, tone = f"The panel is split: {n['invest']} would invest, {n['wait']} would wait, {n['avoid']} would not", "watch"
    return {"counts": n, "total": total, "headline": head, "tone": tone}


def analyse(report: dict) -> dict:
    f0 = Facts(report, {})
    shares = (report.get("market") or {}).get("shares")
    price = (report.get("market") or {}).get("price")
    val = V.build(fcf_history=f0.hist("fcf"), revenue=f0.v("revenue"), cagr3=f0.v("revenue_cagr_3y"), cagr5=f0.v("revenue_cagr_5y"),
                  net_debt=f0.v("net_debt"), shares=shares, price=price)
    if val.get("position"):
        val["position_text"] = V.POSITION_TEXT[val["position"]]
    f = Facts(report, val)
    lenses, fits = [], {}
    for key, name, question in INVESTORS:
        extra = {}
        if key == "lynch":
            checks, note = lynch(f, (report.get("company") or {}).get("sic"))
            extra["note"] = note
        else:
            checks = LENS[key](f)
        x = fit(checks)
        fits[key] = x
        lenses.append({"key": key, "name": name, "question": question, "fit": x, "word": fit_word(x, key), "checks": checks,
                       "backtested": key in BACKTESTED, "caveat": CAVEAT.get(key), "looks_for": LOOKS_FOR.get(key, []),
                       "book": BOOK.get(key), "decision": decide(key, x, val), **extra})
    return {"valuation": val, "lenses": lenses, "overall": overall(fits, val), "future": future(val), "panel": panel(lenses)}
