"""FRED/ALFRED macro (with vintage_date) and Stooq prices (context only). Raw responses cached first.

ALFRED: one request with realtime_start=1776-07-04 / realtime_end=9999-12-31 returns every observation
with the realtime_start..realtime_end window in which that value was current; `realtime_start` is the
vintage_date. Each revision is a new row. Without FRED_API_KEY, live fetch is skipped (cache still used).
"""
from __future__ import annotations

import csv
import io
import json
import os
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent / "data" / "raw"
FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
STOOQ_URL = "https://stooq.com/q/d/l/"
from .concepts import MACRO_SERIES_IDS, VINTAGED_SERIES  # noqa: E402  (A's store/concepts.py)

DEFAULT_SERIES = list(MACRO_SERIES_IDS)  # GDPC1, UNRATE (vintaged) + T10Y2Y, BAA10Y (market)


class MacroSkipped(RuntimeError):
    pass


class _Cached:
    def __init__(self, cache_dir, offline, opener, ua):
        self.dir = Path(cache_dir) if cache_dir else CACHE
        self.offline, self._open, self.ua = offline, opener or urllib.request.urlopen, ua

    def _fetch(self, sub: str, name: str, url: str, headers=None) -> bytes:
        p = self.dir / sub / name
        if p.is_file():
            return p.read_bytes()
        if self.offline:
            raise MacroSkipped(f"offline and not cached: {url.split('?')[0]}")
        req = urllib.request.Request(url, headers=headers or {})
        with self._open(req, timeout=30) as r:
            body = r.read()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
        return body


class FredClient(_Cached):
    def __init__(self, api_key=None, cache_dir=None, offline=False, opener=None):
        super().__init__(cache_dir, offline, opener, None)
        self.api_key = api_key if api_key is not None else os.environ.get("FRED_API_KEY", "")

    def raw(self, series_id: str) -> dict:
        name = f"{series_id}.json"
        cached = (self.dir / "fred" / name).is_file()
        if not cached and not self.api_key:
            raise MacroSkipped("FRED_API_KEY not set and series not cached")
        params = {"series_id": series_id, "api_key": self.api_key or "x", "file_type": "json"}
        if series_id in VINTAGED_SERIES:  # unrevised market series: FRED rejects the all-vintages window (HTTP 400)
            params.update(realtime_start="1776-07-04", realtime_end="9999-12-31")
        q = urllib.parse.urlencode(params)
        return json.loads(self._fetch("fred", name, f"{FRED_URL}?{q}"))  # key never in the cache path

    def series(self, series_id: str, vintaged: bool | None = None) -> list[dict]:
        """`vintaged` defaults to A's MACRO_SERIES flag: unrevised market series get vintage_date = obs_date."""
        v = series_id in VINTAGED_SERIES if vintaged is None else vintaged
        return parse_alfred(series_id, self.raw(series_id), vintaged=v)


def parse_alfred(series_id: str, payload: dict, vintaged: bool = True) -> list[dict]:
    """vintaged=True: one row per revision, vintage_date = ALFRED realtime_start.
    vintaged=False (market rates, never revised): the latest value per obs_date, vintage_date = obs_date."""
    rows = []
    for o in payload.get("observations", []):
        if o.get("value") in (None, ".", ""):  # FRED's missing marker
            continue
        obs = date.fromisoformat(o["date"])
        rows.append({"series_id": series_id, "value": float(o["value"]), "obs_date": obs,
                     "vintage_date": date.fromisoformat(o["realtime_start"]) if vintaged else obs})
    if not vintaged:
        latest: dict = {}
        for r in rows:  # ALFRED lists older vintages first; the last one is the final value
            latest[r["obs_date"]] = r
        rows = list(latest.values())
    rows.sort(key=lambda r: (r["obs_date"], r["vintage_date"]))
    return rows


class StooqClient(_Cached):
    def __init__(self, cache_dir=None, offline=False, opener=None):
        super().__init__(cache_dir, offline, opener, None)

    def prices(self, ticker: str) -> list[dict]:
        sym = f"{ticker.lower()}.us"
        body = self._fetch("stooq", f"{sym}.csv", f"{STOOQ_URL}?s={sym}&i=d").decode("utf-8", "replace")
        return parse_stooq(body)


def parse_stooq(text: str) -> list[dict]:
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        try:
            out.append({"date": date.fromisoformat(r["Date"]), "close": float(r["Close"])})
        except (KeyError, ValueError, TypeError):
            continue  # "No data" bodies and malformed lines
    return out
