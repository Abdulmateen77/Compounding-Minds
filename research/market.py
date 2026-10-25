"""Price and market value: context for the multiples, never a prediction target.

Price comes from Yahoo Finance's public chart endpoint (no key; unofficial, so every failure returns None and the
report simply has no market section). Shares outstanding come from the company's own SEC cover page.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5y&interval=1mo"
UA = "Mozilla/5.0 (compatible; compounding-minds-research)"
TTL_S = 600
FAIL_TTL_S = 60
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
    """Tries both Yahoo hosts. A failure (a 429 is common) keeps the last good quote and is retried after a minute,
    instead of blanking the price section for the full cache time."""
    hit = _cache.get(ticker)
    if hit and time.time() - hit[0] < (TTL_S if hit[1] else FAIL_TTL_S):
        return hit[1]
    q = None
    for url in (URL, URL.replace("query1", "query2")):
        try:
            req = urllib.request.Request(url.format(symbol=_symbol(ticker)), headers={"User-Agent": UA})
            with opener(req, timeout=10) as r:
                q = parse_chart(json.loads(r.read()), ticker)
        except (urllib.error.URLError, TimeoutError, ValueError, ConnectionError):
            q = None
        if q:
            break
    if q is None and hit and hit[1]:
        q = hit[1]
        _cache[ticker] = (time.time() - TTL_S + FAIL_TTL_S, q)
        return q
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


COVER_SHARES = re.compile(r'<ix:nonFraction\b([^>]*name="dei:EntityCommonStockSharesOutstanding"[^>]*)>(.*?)</ix:nonFraction>', re.S | re.I)


def cover_page_shares(sec, cik: int, filings: list[dict]) -> tuple[float, str, str] | None:
    """Share count read from the cover page of the newest 10-K or 10-Q, for companies whose classes the SEC summary
    leaves out (Visa, UPS). Every class listed there is added together, so a class that converts at a ratio above one
    makes the total a little low; it is a close total, not an exact one."""
    rows = [f for f in filings if f.get("form") in ("10-K", "10-Q") and f.get("primaryDocument") and f.get("reportDate")]
    if not rows:
        return None
    f = max(rows, key=lambda r: r["filingDate"])
    try:
        html = sec.filing_document(cik, f["accessionNumber"], f["primaryDocument"]).decode("utf-8", errors="ignore")[:1_500_000]
    except Exception:
        return None
    total, seen = 0.0, set()
    # Berkshire quotes its B share: each A share is worth 1,500 of them, and is the smaller of the two cover-page counts.
    a_ratio = 1500 if cik == 1067983 else 1
    found = []
    for attrs, body in COVER_SHARES.findall(html):
        m = re.search(r'contextRef="([^"]*)"', attrs)
        key = m.group(1) if m else body
        digits = re.sub(r"[^\d.]", "", re.sub(r"<[^>]+>", "", body))
        if key in seen or not digits:
            continue
        seen.add(key)
        scale = re.search(r'scale="(-?\d+)"', attrs)
        found.append(float(digits) * 10 ** (int(scale.group(1)) if scale else 0))
    if a_ratio > 1 and len(found) == 2:
        total = min(found) * a_ratio + max(found)
    else:
        total = sum(found)
    return (total, f["reportDate"], f["accessionNumber"]) if total > 0 else None
