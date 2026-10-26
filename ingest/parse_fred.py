"""Turn a FRED / ALFRED `series/observations` response into macro rows (README 4.1).

Revised series (GDP, unemployment) must be fetched with the whole real-time window, so every
vintage comes back:

    https://api.stlouisfed.org/fred/series/observations?series_id=GDPC1&file_type=json
        &realtime_start=1776-07-04&realtime_end=9999-12-31&api_key=...

Each observation then has `realtime_start` (the first day that value was the published one):
that is our `vintage_date`. Market rates (T10Y2Y, BAA10Y) are never revised, so their vintage
is the observation date itself. FRED writes a missing value as ".", which is skipped.
"""
from __future__ import annotations

from datetime import date

from store.concepts import MACRO_SERIES

_REVISED = {series_id: revised for series_id, revised, _ in MACRO_SERIES.values()}


def series_is_revised(series_id: str) -> bool:
    return _REVISED[series_id]


def parse_fred(data: dict, series_id: str) -> list[dict]:
    revised = series_is_revised(series_id)
    seen: set[tuple] = set()
    rows = []
    for o in data.get("observations", []):
        if o.get("value") in (None, "", "."):
            continue
        obs = date.fromisoformat(o["date"])
        vintage = date.fromisoformat(o["realtime_start"]) if revised else obs
        key = (obs, vintage)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"series_id": series_id, "value": float(o["value"]), "obs_date": obs, "vintage_date": vintage})
    rows.sort(key=lambda r: (r["obs_date"], r["vintage_date"]))
    return rows
