"""The 5-minute check: five quick tests of whether a company is worth deeper research, or one to avoid.

From the method described by Pratik Chauhan (a video summary the user supplied; thresholds as stated there, not
checked against the original): low debt, a high and steady return on capital employed, steady sales growth,
promoters who own a large stake without pledging it, and little dilution of existing shareholders. The method is meant
for manufacturing and other non-financial companies, so for banks and insurers the check says it does not apply.

Each test returns pass / partial / fail / unknown with the number it used. Python computes every figure.
"""
from __future__ import annotations

SOURCE = "Pratik Chauhan's 5-minute fundamental check (from a video summary; thresholds as stated there)"
FINANCIAL_SIC = ("60", "61", "62", "63", "64", "65", "67")      # banks, credit, brokers, insurers, real estate trusts
FOR_FINANCIALS = ("For banks and insurers, debt is the raw material of the business, so these tests do not apply. "
                  "Look instead at return on equity, the price against book value, capital strength and loan or claim losses.")


def _hist(figs: dict, key: str) -> list[float]:
    f = figs.get(key)
    return [] if f is None else [h["value"] for h in f["history"] if h["value"] is not None]


def _v(figs: dict, key: str) -> float | None:
    f = figs.get(key)
    return None if f is None else f["value"]


def _item(key: str, label: str, rule: str, result: str, found: str) -> dict:
    return {"key": key, "label": label, "rule": rule, "result": result, "found": found}


def run(report: dict) -> dict:
    sic = (report.get("company") or {}).get("sic") or ""
    if sic[:2] in FINANCIAL_SIC:
        return {"applies": False, "note": FOR_FINANCIALS, "items": [], "source": SOURCE}
    figs = {f["key"]: f for s in report["sections"] for f in s["figures"]}
    items = []

    debt, equity = _v(figs, "debt"), _v(figs, "equity")
    if debt is not None and equity is not None and equity > 0:
        de = debt / equity
        items.append(_item("debt_to_equity", "Debt to equity", "Close to zero: heavily indebted companies have struggled to protect shareholders",
                           "pass" if de <= 0.3 else "partial" if de <= 1.0 else "fail", f"{de:.2f} (debt {_money(debt)} against equity {_money(equity)})"))
    elif equity is not None and equity <= 0:
        items.append(_item("debt_to_equity", "Debt to equity", "Close to zero", "fail", "shareholders' equity is negative"))
    else:
        items.append(_item("debt_to_equity", "Debt to equity", "Close to zero", "unknown", "not reported"))

    roce = _hist(figs, "roce")
    if roce:
        good = sum(1 for x in roce if x >= 0.20)
        r = "pass" if good == len(roce) else "partial" if roce[-1] >= 0.20 or good >= len(roce) / 2 else "fail"
        items.append(_item("roce", "Return on capital employed", "At least 20% every year (the method asks for ten years; we have up to seven)",
                           r, f"{roce[-1] * 100:.1f}% now; 20% or more in {good} of the last {len(roce)} years"))
    else:
        items.append(_item("roce", "Return on capital employed", "At least 20% every year", "unknown", "not enough data"))

    growth = _hist(figs, "revenue_growth")
    if len(growth) >= 3:
        up = sum(1 for x in growth if x > 0)
        items.append(_item("sales_growth", "Sales growth", "Revenue up year after year",
                           "pass" if up == len(growth) else "partial" if up >= len(growth) - 1 else "fail",
                           f"sales grew in {up} of the last {len(growth)} years"))
    else:
        items.append(_item("sales_growth", "Sales growth", "Revenue up year after year", "unknown", "not enough history"))

    items.append(_item("promoter", "Promoter holding and pledging", "Founders or controlling owners hold a large stake, and none of it is pledged",
                       "unknown", "not in the SEC data we load: US filings seldom report pledging, and insider stakes sit in proxy filings we do not read yet"))

    sh = report.get("share_history") or []
    if len(sh) >= 3 and sh[0]["value"] > 0:
        years = max(len(sh) - 1, 1)
        per_year = (sh[-1]["value"] / sh[0]["value"]) ** (1 / years) - 1
        r = "pass" if per_year <= 0.01 else "partial" if per_year <= 0.03 else "fail"
        what = "fallen" if per_year < -0.001 else "risen" if per_year > 0.001 else "stayed flat"
        items.append(_item("dilution", "Equity dilution", "Few new shares issued: dilution shrinks existing owners' stakes", r,
                           f"shares outstanding have {what}, {per_year * 100:+.1f}% a year over {years} years"
                           + (" (buybacks)" if per_year < -0.001 else "")))
    else:
        items.append(_item("dilution", "Equity dilution", "Few new shares issued", "unknown", "not enough share-count history"))

    known = [i for i in items if i["result"] != "unknown"]
    score = None if len(known) < 2 else sum({"pass": 1.0, "partial": 0.5, "fail": 0.0}[i["result"]] for i in known) / len(known)
    verdict = (None if score is None else "Worth deeper research" if score >= 0.75 else "Mixed: research with care" if score >= 0.4
               else "Fails the quick check")
    return {"applies": True, "items": items, "score": score, "verdict": verdict, "source": SOURCE,
            "note": "A screen for deciding what to research further, not a reason to buy."}


def _money(x: float) -> str:
    a = abs(x)
    s = f"${a / 1e12:.2f}T" if a >= 1e12 else f"${a / 1e9:.1f}B" if a >= 1e9 else f"${a / 1e6:.0f}M"
    return ("-" if x < 0 else "") + s
