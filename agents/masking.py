"""Hide calendar time from prompts so the model can't recall what happened (README 7, 16).

Absolute dates become positions relative to the as-of quarter:
    2019-06-30 at as_of 2019-06-30  -> Q0
    2019-03-31                       -> Q-1
    2019Q4 / 2019-Q4 / Q4 2019       -> Q+2
    a bare year like 2018            -> Y-1   (relative to the as-of year)

Apply this to free text only (names, units, lessons, reasoning). Never run it over
numeric metric values: a value such as 2019.0 must reach the model unchanged.
"""
from __future__ import annotations

import re
from datetime import date

# Boundaries are "not a digit or dot" rather than \b, so names like revenue_2018Q4 match too.
_ISO = re.compile(r"(?<![\d.])((?:19|20)\d{2})-(\d{2})-(\d{2})(?!\d)")
_YQ = re.compile(r"(?<![\d.])((?:19|20)\d{2})[ -]?Q([1-4])(?!\d)")
_QY = re.compile(r"(?<![A-Za-z0-9])Q([1-4])[ -]((?:19|20)\d{2})(?![\d.])")
_YEAR = re.compile(r"(?<![\d.])((?:19|20)\d{2})(?![\d.])")


def _q_index(year: int, quarter: int) -> int:
    return year * 4 + (quarter - 1)


def quarter_of(d: date) -> int:
    return _q_index(d.year, (d.month - 1) // 3 + 1)


def _q_label(k: int) -> str:
    return "Q0" if k == 0 else f"Q{k:+d}"


def _y_label(k: int) -> str:
    return "Y0" if k == 0 else f"Y{k:+d}"


def relative_quarter(d: date, as_of: date) -> str:
    return _q_label(quarter_of(d) - quarter_of(as_of))


def mask_dates(text: str, as_of: date) -> str:
    base = quarter_of(as_of)
    text = _ISO.sub(lambda m: _q_label(quarter_of(date(int(m[1]), int(m[2]), int(m[3]))) - base), text)
    text = _YQ.sub(lambda m: _q_label(_q_index(int(m[1]), int(m[2])) - base), text)
    text = _QY.sub(lambda m: _q_label(_q_index(int(m[2]), int(m[1])) - base), text)
    return _YEAR.sub(lambda m: _y_label(int(m[1]) - as_of.year), text)


def has_calendar_year(text: str) -> bool:
    return bool(_YEAR.search(text) or _ISO.search(text))
