"""Tiny statistics helpers. Pure Python on purpose: a handful of OLS slopes does not need numpy."""
from __future__ import annotations

from math import sqrt


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def stdev(xs: list[float]) -> float:
    """Sample standard deviation (n - 1). Needs at least two values."""
    m = mean(xs)
    return sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def slope(ys: list[float]) -> float:
    """OLS slope of ys against 0, 1, 2, ... (per step). Needs at least two values."""
    return slope_xy(list(range(len(ys))), ys)


def slope_xy(xs: list[float], ys: list[float]) -> float | None:
    """OLS slope of ys on xs, or None if xs has no variance."""
    mx, my = mean(xs), mean(ys)
    var = sum((x - mx) ** 2 for x in xs)
    if var == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var
