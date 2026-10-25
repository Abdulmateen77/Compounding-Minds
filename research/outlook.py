"""The 5-year outlook: how likely the business is to be bigger, and what it could be worth per share along the way.

Two pieces, both Python and both shown with their method:

1. **Will the business grow or shrink?** A bootstrap over the company's own record: draw five years of revenue growth,
   with replacement, from the yearly growth rates it has actually had (up to ten), many thousands of times. The share of
   draws that end above today's revenue is the chance it is bigger in five years, given its own history. Its own history
   is the only input, so the range is wide for an uneven record and narrow for a steady one, which is the point.
2. **Value per share, year by year.** The same discounted-cash-flow model as the valuation section, read at each of the
   next five years for the bear, base and bull cases, set beside today's price.

This is not a share-price forecast. A price can sit far from value for years. The page says so.
"""
from __future__ import annotations

import random

from . import valuation as V

DRAWS = 20_000
YEARS = 5
SEED = 7                      # fixed, so the same company gives the same numbers every time


def growth_odds(yearly: list[float], years: int = YEARS, draws: int = DRAWS, seed: int = SEED) -> dict | None:
    """Bootstrap the five-year revenue change from the company's own yearly growth rates."""
    g = [x for x in yearly if x is not None and x > -0.9]
    if len(g) < 4:
        return None
    rng = random.Random(seed)
    outcomes = []
    for _ in range(draws):
        level = 1.0
        for _ in range(years):
            level *= 1 + rng.choice(g)
        outcomes.append(level - 1)
    outcomes.sort()
    q = lambda p: outcomes[min(len(outcomes) - 1, int(p * len(outcomes)))]        # noqa: E731
    return {"years": years, "history_years": len(g), "chance_higher": sum(1 for x in outcomes if x > 0) / len(outcomes),
            "chance_down_a_fifth": sum(1 for x in outcomes if x < -0.2) / len(outcomes),
            "median_change": q(0.5), "low_change": q(0.1), "high_change": q(0.9),
            "worst_year": min(g), "best_year": max(g)}


def value_path(val: dict, shares: float | None, net_debt: float | None, years: int = YEARS) -> list[dict]:
    """Value per share at the end of each of the next `years` years, per case (the cash flows still to come, discounted
    to that year, plus the terminal value, less today's net debt). Empty when the valuation is not available."""
    if not val.get("available") or not shares or net_debt is None:
        return []
    rate, out = val["discount_rate"], []
    for s in val["scenarios"]:
        path = s["fcf_path"]
        points = []
        for t in range(0, years + 1):
            rest = path[t:]
            pv = sum(cf / (1 + rate) ** (i + 1) for i, cf in enumerate(rest))
            terminal = path[-1] * (1 + V.LONG_RUN) / (rate - V.LONG_RUN)
            pv += terminal / (1 + rate) ** len(rest)
            points.append({"year": t, "value": (pv - net_debt) / shares})
        out.append({"name": s["name"], "start_growth": s["start_growth"], "points": points})
    return out


def build(*, yearly_growth: list[float], val: dict, shares: float | None, net_debt: float | None, price: float | None) -> dict:
    odds = growth_odds(yearly_growth)
    path = value_path(val, shares, net_debt)
    base5 = next((p["points"][-1]["value"] for p in path if p["name"] == "Base"), None)
    implied = None
    if price and base5 and base5 > 0:
        implied = (base5 / price) ** (1 / YEARS) - 1
    return {"odds": odds, "value_path": path, "price": price, "base_value_in_5y": base5,
            "return_if_price_meets_base": implied, "verdict": _verdict(odds, implied)}


def _verdict(odds: dict | None, implied: float | None) -> dict:
    """One plain reading of the five years ahead, from the two numbers above."""
    if odds is None:
        return {"tone": "watch", "headline": "Too little history to judge the next five years",
                "why": "The company has fewer than four years of comparable revenue, so its own record says little yet."}
    p = odds["chance_higher"]
    grow = "very likely" if p >= 0.85 else "likely" if p >= 0.65 else "about as likely as not" if p >= 0.4 else "unlikely"
    head = f"The business is {grow} to be bigger in five years ({p * 100:.0f}% on its own record)"
    if implied is None:
        return {"tone": "good" if p >= 0.65 else "watch" if p >= 0.4 else "warn", "headline": head,
                "why": "There is no reliable share count or price, so the page cannot compare value with price."}
    if implied >= 0.08:
        tone, why = ("good" if p >= 0.65 else "watch"), (f"If the share price ended at the base-case value in five years, that would be "
                                                          f"about {implied * 100:+.0f}% a year: the price leaves room.")
    elif implied >= 0:
        tone, why = "watch", (f"If the share price ended at the base-case value in five years, that would be only about "
                              f"{implied * 100:+.0f}% a year: a good business can still be a modest investment at this price.")
    else:
        tone, why = "warn", (f"The base-case value in five years is below today's price (about {implied * 100:+.0f}% a year if the "
                             f"price met it): the price already assumes more than the company's record supports.")
    return {"tone": tone, "headline": head, "why": why}
