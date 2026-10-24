"""Price and market value: context for the multiples, never a prediction target.

Price comes from Yahoo Finance's public chart endpoint (no key; unofficial, so every failure returns None and the
report simply has no market section). Shares outstanding come from the company's own SEC cover page.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5y&interval=1mo"
UA = "Mozilla/5.0 (compatible; compounding-minds-research)"
TTL_S = 600
_cache: dict[str, tuple[float, "Quote | None"]] = {}


@dataclass(frozen=True)
class Quote:
    symbol: str
    price: float
    currency: str
    as_of: str                       # ISO date of the price
    high_52w: float | None
    low_52w: float | None
    history: list[tuple[str, float]]  # month-end closes, oldest first, about 5 years


def _symbol(ticker: str) -> str:
    return urllib.parse.quote(ticker.replace(".", "-"))


def parse_chart(raw: dict, ticker: str) -> "Quote | None":
    try:
        res = raw["chart"]["result"][0]
        meta = res["meta"]
        stamps, closes = res["timestamp"], res["indicators"]["quote"][0]["close"]
        hist = [(time.strftime("%Y-%m-%d", time.gmtime(t)), float(c)) for t, c in zip(stamps, closes) if c is not None]
        price = float(meta["regularMarketPrice"])
        day = time.strftime("%Y-%m-%d", time.gmtime(meta.get("regularMarketTime") or stamps[-1]))
        return Quote(ticker, price, meta.get("currency", "USD"), day,
                     meta.get("fiftyTwoWeekHigh"), meta.get("fiftyTwoWeekLow"), hist)
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def quote(ticker: str, opener=urllib.request.urlopen) -> "Quote | None":
    hit = _cache.get(ticker)
    if hit and time.time() - hit[0] < TTL_S:
        return hit[1]
    q = None
    try:
        req = urllib.request.Request(URL.format(symbol=_symbol(ticker)), headers={"User-Agent": UA})
        with opener(req, timeout=10) as r:
            q = parse_chart(json.loads(r.read()), ticker)
    except (urllib.error.URLError, TimeoutError, ValueError, ConnectionError):
        q = None
    _cache[ticker] = (time.time(), q)
    return q


def shares_outstanding(rows: list[dict]) -> tuple[float, str, str] | None:
    """Total shares from the latest cover page: classes listed in the same filing are added together
    (Alphabet reports A, B and C separately). Returns (shares, period end, accession)."""
    if not rows:
        return None
    top = rows[0]
    same = [r for r in rows if r["accession"] == top["accession"] and r["end"] == top["end"]]
    return sum(r["value"] for r in same), top["end"], top["accession"]
