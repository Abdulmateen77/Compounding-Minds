"""What the business could be worth, and what the market price already assumes. All Python, all assumptions shown.

Method (a plain discounted-cash-flow, the idea behind Buffett's "owner earnings" and Graham's intrinsic value):
  * start from normalised free cash flow: the median of the last three year-end trailing-twelve-month figures, so one
    unusual year (a big tax payment, a one-off windfall) does not distort it
  * grow it for ten years from a starting rate that fades in a straight line to a long-run rate
  * discount at the investor's required return and add a terminal value
  * add cash, subtract debt, divide by shares
Three starting growth rates (bear, base, bull) come from the company's own history, never from a model.
The reverse calculation asks the opposite question: what growth is the current price already assuming?
Nothing here predicts a price. It is "what is the business worth under these assumptions".
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass

YEARS = 10
DISCOUNT = 0.08             # required yearly return, a middle-of-the-road long-run hurdle; the page shows 7% and 10% too
LONG_RUN = 0.025            # growth after year ten, about the economy's long-run pace
GROWTH_FLOOR, GROWTH_CAP = -0.05, 0.20
DISCOUNT_GRID = (0.07, 0.08, 0.10)


@dataclass(frozen=True)
class Scenario:
    name: str
    start_growth: float
    value_per_share: float | None
    fcf_path: list[float]          # years 1..10
    revenue_path: list[float] | None


def _clamp(x: float, lo: float = GROWTH_FLOOR, hi: float = GROWTH_CAP) -> float:
    return max(lo, min(hi, x))


def fcf_path(base: float, start_growth: float, years: int = YEARS) -> list[float]:
    """Growth fades in a straight line from `start_growth` in year 1 to LONG_RUN in the final year."""
    out, cur = [], base
    for t in range(1, years + 1):
        g = start_growth + (LONG_RUN - start_growth) * (t - 1) / (years - 1)
        cur *= 1 + g
        out.append(cur)
    return out


def present_value(path: list[float], rate: float, terminal_growth: float = LONG_RUN) -> float:
    pv = sum(cf / (1 + rate) ** t for t, cf in enumerate(path, 1))
    terminal = path[-1] * (1 + terminal_growth) / (rate - terminal_growth)
    return pv + terminal / (1 + rate) ** len(path)


def equity_per_share(path: list[float], rate: float, net_debt: float, shares: float) -> float:
    return (present_value(path, rate) - net_debt) / shares


def implied_growth(price: float, base: float, net_debt: float, shares: float, rate: float = DISCOUNT) -> float | None:
    """The starting growth rate that makes the model's value equal today's price (bisection). None when no rate in
    the allowed range does (the price is below the bear case, or beyond the bull case)."""
    target = price * shares + net_debt
    lo, hi = GROWTH_FLOOR, 0.45
    f = lambda g: present_value(fcf_path(base, g), rate) - target       # noqa: E731
    if f(lo) > 0:
        return None            # even shrinking cash flow is worth more than the price
    if f(hi) < 0:
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if f(mid) < 0 else (lo, mid)
    return (lo + hi) / 2


def base_growth(cagr3: float | None, cagr5: float | None) -> float | None:
    """The starting growth for the base case: the average of the 3-year and 5-year revenue growth rates the company
    has actually delivered, held inside a sensible band. Revenue growth is the anchor because cash flow is noisy."""
    xs = [x for x in (cagr3, cagr5) if x is not None]
    return None if not xs else _clamp(sum(xs) / len(xs))


def build(*, fcf_history: list[float], revenue: float | None, cagr3: float | None, cagr5: float | None,
          net_debt: float | None, shares: float | None, price: float | None) -> dict:
    """Everything the page shows. `fcf_history`: year-end trailing-twelve-month free cash flow, oldest first."""
    recent = [x for x in fcf_history[-3:] if x is not None]
    if len(recent) < 2 or net_debt is None:
        return {"available": False, "reason": "Not enough free-cash-flow history to value it."}
    base_fcf = statistics.median(recent)
    g0 = base_growth(cagr3, cagr5)
    if g0 is None:
        return {"available": False, "reason": "Not enough revenue history to anchor the growth assumption."}
    if base_fcf <= 0:
        return {"available": False, "reason": "Free cash flow has been zero or negative in a typical recent year, so a cash-flow "
                                              "valuation is not meaningful. Judge it on growth and the balance sheet instead.",
                "normalised_fcf": base_fcf}
    sc = [("Bear", _clamp(g0 - 0.05)), ("Base", g0), ("Bull", _clamp(g0 + 0.04, hi=0.25))]
    out = {"available": True, "normalised_fcf": base_fcf, "discount_rate": DISCOUNT, "long_run_growth": LONG_RUN,
           "years": YEARS, "scenarios": []}
    for name, g in sc:
        path = fcf_path(base_fcf, g)
        rev_path = None
        if revenue:
            r, rev_path = revenue, []
            for t in range(1, YEARS + 1):
                gt = g + (LONG_RUN - g) * (t - 1) / (YEARS - 1)
                r *= 1 + gt
                rev_path.append(r)
        out["scenarios"].append({
            "name": name, "start_growth": g, "fcf_path": path, "revenue_path": rev_path,
            "value_per_share": None if not shares else equity_per_share(path, DISCOUNT, net_debt, shares)})
    if shares:
        base = out["scenarios"][1]
        out["sensitivity"] = [{"rate": r, "values": [equity_per_share(fcf_path(base_fcf, g), r, net_debt, shares) for _, g in sc]}
                              for r in DISCOUNT_GRID]
    if price and shares:
        ig = implied_growth(price, base_fcf, net_debt, shares)
        base_v = out["scenarios"][1]["value_per_share"]
        out["price"] = price
        out["implied_growth"] = ig
        out["price_vs_base"] = None if not base_v or base_v <= 0 else price / base_v - 1
        out["position"] = _position(price, [s["value_per_share"] for s in out["scenarios"]])
    return out


def _position(price: float, values: list[float | None]) -> str:
    bear, base, bull = values
    if base is None or base <= 0:
        return "unknown"
    if bull is not None and price > bull:
        return "above_bull"
    if price > base * 1.15:
        return "above_base"
    if price >= (bear if bear is not None else base * 0.7) and price >= base * 0.85:
        return "near_base"
    if bear is not None and price >= bear:
        return "below_base"
    return "below_bear"


POSITION_TEXT = {
    "above_bull": "The price is above even the optimistic case: the market is assuming more than this company's history supports.",
    "above_base": "The price is above the base case: you are paying for growth beyond what it has delivered recently.",
    "near_base": "The price is close to the base case: the market is roughly assuming what the company has delivered.",
    "below_base": "The price is below the base case but within the range: there is some cushion if the business keeps delivering.",
    "below_bear": "The price is below even the pessimistic case: either the market doubts the cash flow, or it is cheap.",
    "unknown": "The base case is not meaningful for this company.",
}
