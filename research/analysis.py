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
    "dalio.03": "Dalio, How the Economic Machine Works", "dalio.04": "Dalio, Principles",
    "graham.01": "Graham, The Intelligent Investor ch. 20 (citation not yet verified)",
    "graham.02": "Graham, The Intelligent Investor ch. 11 and 14 (not yet verified)",
    "graham.03": "Graham, The Intelligent Investor ch. 14 (not yet verified)",
    "graham.04": "Graham, The Intelligent Investor ch. 14 (not yet verified)",
    "graham.05": "Graham, The Intelligent Investor ch. 14 (not yet verified)",
    "graham.06": "Graham, The Intelligent Investor ch. 14 (not yet verified)",
}
INVESTORS = [("buffett", "Warren Buffett", "Is it a durable business that turns profit into cash?"),
             ("munger", "Charlie Munger", "How could this business fail?"),
             ("graham", "Benjamin Graham", "Is there a margin of safety in the price?"),
             ("dalio", "Ray Dalio", "How exposed is it to the economic cycle?")]


def principle_text(pid: str) -> str:
    """The rule in our own words, from principles/<investor>.md."""
    name = pid.split(".")[0]
    try:
        for line in (PRINCIPLES_DIR / f"{name}.md").read_text(encoding="utf-8").splitlines():
            if line.startswith(pid + " |"):
                return line.split("|")[1].strip()
    except OSError:
        pass
    return pid


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
    return {"id": pid, "principle": principle_text(pid), "source": CITATION.get(pid, ""), "check": what,
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
def graham(f: Facts) -> list[dict]:
    val, m = f.val, f.market
    out = []
    pos = val.get("position") if val.get("available") else None
    pv = val.get("price_vs_base")
    out.append(_check("graham.01", "Does the price leave a cushion against being wrong?",
                      {"below_bear": "pass", "below_base": "pass", "near_base": "partial", "above_base": "fail", "above_bull": "fail"}.get(pos or "", "unknown"),
                      "n/a" if pv is None else (f"price is {pv + 1:.1f}× the base-case value" if pv > 1 else
                                                f"price is {abs(pv) * 100:.0f}% {'above' if pv > 0 else 'below'} the base-case value")))
    ig, g0 = val.get("implied_growth"), (val["scenarios"][1]["start_growth"] if val.get("available") else None)
    if ig is not None and g0 is not None:
        r = "pass" if ig <= g0 else "partial" if ig <= g0 + 0.03 else "fail"
        out.append(_check("graham.02", "Is it paying for growth the business has not delivered?", r,
                          f"price assumes {_pct(ig)} a year; the company has delivered about {_pct(g0)}"))
    elif g0 is not None and pos == "above_bull":
        out.append(_check("graham.02", "Is it paying for growth the business has not delivered?", "fail",
                          f"the price assumes more than 45% a year; the company has delivered about {_pct(g0)}"))
    else:
        out.append(_check("graham.02", "Is it paying for growth the business has not delivered?", "unknown", "not available"))
    ni, gm = f.hist("net_income"), f.hist("revenue_growth")
    if len(ni) >= 4:
        loss = any(x <= 0 for x in ni[-5:])
        out.append(_check("graham.03", "Steady earnings across the years?", "fail" if loss else "pass",
                          "a loss year in the last five" if loss else "profitable in each of the last five years"))
    pe3 = None
    if m and m.get("market_cap") and len(ni) >= 3 and sum(ni[-3:]) > 0:
        pe3 = m["market_cap"] / (sum(ni[-3:]) / 3)
    out.append(_check("graham.04", "Price against three-year average earnings, not one year",
                      "unknown" if pe3 is None else "pass" if pe3 <= 20 else "partial" if pe3 <= 30 else "fail",
                      "n/a" if pe3 is None else f"{pe3:.1f}× average profit of the last three years"))
    cr = f.v("current_ratio")
    out.append(_check("graham.05", "A defensive company has a strong balance sheet",
                      _worst("pass" if cr is not None and cr >= 2 else "partial" if cr is not None and cr >= 1.5 else "fail" if cr is not None else "unknown",
                             _tone_result(f.tone("debt_to_ebitda"))),
                      f"short-term cushion {'n/a' if cr is None else f'{cr:.2f}×'}"))
    div = f.hist("dividends")
    dc = f.flags.get("dividend_cuts")
    if div:
        out.append(_check("graham.06", "An unbroken dividend record", "pass" if dc and dc["value"] == 0 and all(x > 0 for x in div[-5:]) else "partial",
                          "pays a dividend with no cuts in five years" if dc and dc["value"] == 0 else "dividend has been cut"))
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


LENS = {"buffett": buffett, "munger": munger, "graham": graham, "dalio": dalio}


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
        rows.append({"name": s["name"], "start_growth": s["start_growth"], "value_per_share": s["value_per_share"],
                     "revenue": {str(y): pick(s["revenue_path"], y) for y in (1, 3, 5, 10)},
                     "fcf": {str(y): pick(s["fcf_path"], y) for y in (1, 3, 5, 10)}})
    return {"scenarios": rows}


def analyse(report: dict) -> dict:
    f0 = Facts(report, {})
    shares = (report.get("market") or {}).get("shares")
    price = (report.get("market") or {}).get("price")
    nd = f0.v("net_debt")
    val = V.build(fcf_history=f0.hist("fcf"), revenue=f0.v("revenue"), cagr3=f0.v("revenue_cagr_3y"), cagr5=f0.v("revenue_cagr_5y"),
                  net_debt=nd, shares=shares, price=price)
    if val.get("position"):
        val["position_text"] = V.POSITION_TEXT[val["position"]]
    f = Facts(report, val)
    lenses, fits = [], {}
    for key, name, question in INVESTORS:
        checks = LENS[key](f)
        x = fit(checks)
        fits[key] = x
        lenses.append({"key": key, "name": name, "question": question, "fit": x, "word": fit_word(x, key), "checks": checks})
    return {"valuation": val, "lenses": lenses, "overall": overall(fits, val), "future": future(val)}
