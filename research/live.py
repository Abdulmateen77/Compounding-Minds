"""Load any listed company's SEC data on demand and read it through the same date gate as the replay.

A live company is never written to Postgres (its id must be `anon_NNN` there). Its facts and events sit in
memory under the id `live_<cik>`, and `LiveBackend` routes those ids to memory while every other id, and every
macro series, goes to the backend that was already installed. So `metrics.Context` works unchanged: it asks
`store.queries` for rows visible at `as_of`, and `as_of` is simply today.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from ingest.parse_facts import parse_companyfacts
from ingest.parse_submissions import parse_submissions
from ingest.sec import DATA, SecClient
from store import queries

LIVE_PREFIX = "live_"
MAX_AGE_HOURS = 24          # a cached SEC response older than this is refetched
MACRO_AGE_S = 3600


def live_id(cik: int) -> str:
    return f"{LIVE_PREFIX}{int(cik):010d}"


@dataclass
class LiveCompany:
    company_id: str
    cik: int
    sic: str | None
    facts: list[dict]
    events: list[dict]
    filings: list[dict]                       # submissions rows, newest first, for the text pass
    shares: list[dict] = field(default_factory=list)   # dei shares outstanding, latest first
    latest_filing: dict | None = None                  # the newest 10-K or 10-Q in the filing list
    facts_through: str | None = None                   # the newest filing date of any figure we hold
    loaded_at: float = field(default_factory=time.time)


class LiveBackend:
    """Routes `live_*` ids to memory, everything else to the backend that was installed before."""

    def __init__(self, base: queries.Backend):
        self.base = base
        self._facts: dict[str, dict[str, list[dict]]] = {}
        self._events: dict[str, list[dict]] = {}
        self._macro: dict[str, tuple[float, list[dict]]] = {}
        self._lock = threading.Lock()

    def put(self, c: LiveCompany) -> None:
        by: dict[str, list[dict]] = {}
        for r in c.facts:
            by.setdefault(r["concept"], []).append(r)
        with self._lock:
            self._facts[c.company_id], self._events[c.company_id] = by, c.events

    def facts(self, company_id: str, concept: str) -> list[dict]:
        if company_id.startswith(LIVE_PREFIX):
            return self._facts.get(company_id, {}).get(concept, [])
        return self.base.facts(company_id, concept)

    def events(self, company_id: str) -> list[dict]:
        if company_id.startswith(LIVE_PREFIX):
            return self._events.get(company_id, [])
        return self.base.events(company_id)

    def macro(self, series_id: str) -> list[dict]:
        """Macro series are small and shared: read once an hour, from Postgres when it is reachable."""
        got = self._macro.get(series_id)
        if got and time.time() - got[0] < MACRO_AGE_S:
            return got[1]
        try:
            rows = self.base.macro(series_id)
        except Exception:        # no database: the report just has no economy section
            rows = got[1] if got else []
        self._macro[series_id] = (time.time(), rows)
        return rows


class _PgMacro:
    """A macro-only backend that opens its own short connection, so no connection is shared across threads."""

    def facts(self, company_id, concept):
        return []

    def events(self, company_id):
        return []

    def macro(self, series_id):
        from store import db, pg
        with db.connect(timeout=3) as conn:
            return pg.PostgresBackend(conn).macro(series_id)


def install() -> LiveBackend:
    """Wrap the current store backend once. Safe to call again."""
    cur = queries._backend
    if isinstance(cur, LiveBackend):
        return cur
    base = cur if queries.has_backend() else (_PgMacro() if os.environ.get("DATABASE_URL") else cur)
    backend = LiveBackend(base)
    queries.set_backend(backend)
    return backend


def _fresh(sec: SecClient, url: str) -> bool:
    p = sec.path_for(url)
    return p.is_file() and (time.time() - p.stat().st_mtime) < MAX_AGE_HOURS * 3600


def _get(sec: SecClient, url: str):
    """Cached JSON, refetched once a day so a new filing shows up."""
    if sec.offline or _fresh(sec, url) or not sec.cached(url):
        return sec.get_json(url)
    sec.refresh = True
    try:
        return sec.get_json(url)
    finally:
        sec.refresh = False


def _shares(data: dict) -> list[dict]:
    """Shares outstanding from the cover page (dei). One row per (period, class); latest first. Companies with several
    share classes (Alphabet) tag the cover page by class, which the SEC summary omits: for those, the diluted
    weighted-average count from the income statement is the closest total, and it is marked as such."""
    rows = []
    for e in (data.get("facts", {}).get("dei", {}).get("EntityCommonStockSharesOutstanding", {}).get("units", {}).get("shares", [])):
        if e.get("val") is not None and e.get("end") and e.get("filed"):
            rows.append({"end": e["end"], "filed": e["filed"], "value": float(e["val"]), "accession": e.get("accn")})
    if not rows:
        w = (data.get("facts", {}).get("us-gaap", {}).get("WeightedAverageNumberOfDilutedSharesOutstanding", {}).get("units", {}).get("shares", []))
        for e in w:
            if e.get("val") is not None and e.get("end") and e.get("filed") and e.get("form") in ("10-Q", "10-K"):
                rows.append({"end": e["end"], "filed": e["filed"], "value": float(e["val"]), "accession": e.get("accn"), "weighted": True})
        rows.sort(key=lambda r: (r["filed"], r["end"]), reverse=True)
        return rows[:1]
    rows.sort(key=lambda r: (r["filed"], r["end"]), reverse=True)
    return rows


PERIODIC = ("10-K", "10-Q", "10-K/A", "10-Q/A")
_checked: set[tuple[int, str]] = set()        # (cik, day): the filing list is re-read once a day per company


def _refetch(sec: SecClient, url: str):
    if sec.offline:
        return sec.get_json(url)
    sec.refresh = True
    try:
        return sec.get_json(url)
    finally:
        sec.refresh = False


def latest_periodic(filings: list[dict]) -> dict | None:
    rows = [f for f in filings if f.get("form") in PERIODIC and f.get("filingDate")]
    if not rows:
        return None
    f = max(rows, key=lambda r: r["filingDate"])
    return {"form": f["form"], "filed": f["filingDate"], "period": f.get("reportDate") or None,
            "accession": f.get("accessionNumber")}


def facts_filed_through(data: dict) -> str | None:
    """The newest filing date of any fact in a companyfacts file: how current the file's contents really are."""
    dates = [e["filed"] for tax in data.get("facts", {}).values() for t in tax.values()
             for unit in t.get("units", {}).values() for e in unit if e.get("filed")]
    return max(dates) if dates else None


def load_company(sec: SecClient, cik: int) -> LiveCompany:
    """A file's save time says nothing about its contents (a cache can be copied in today and still stop in April), so
    freshness is judged by what is inside: the filing list is re-read once a day, and the figures are downloaded again
    whenever the list shows a 10-K or 10-Q newer than the newest figure in the cached file."""
    cid = live_id(cik)
    padded = f"{int(cik):010d}"
    subs_url, facts_url = f"{DATA}/submissions/CIK{padded}.json", f"{DATA}/api/xbrl/companyfacts/CIK{padded}.json"
    key = (int(cik), time.strftime("%Y-%m-%d"))
    subs_json = _get(sec, subs_url) if key in _checked else _refetch(sec, subs_url)
    _checked.add(key)
    filings = subs_json["filings"]["recent"]
    rows = [dict(zip(filings, vals)) for vals in zip(*filings.values())]
    newest = latest_periodic(rows)
    facts_json = _get(sec, facts_url)
    through = facts_filed_through(facts_json)
    if newest and (through is None or through < newest["filed"]):
        facts_json = _refetch(sec, facts_url)
        through = facts_filed_through(facts_json)
    subs = parse_submissions(subs_json, cid)
    events = list(subs.events)
    for name in subs.extra_files:                       # older filing pages: the risk checks look back 5 years
        try:
            events += parse_submissions({"filings": {"recent": _get(sec, f"{DATA}/submissions/{name}")}}, cid).events
        except Exception:
            continue
    c = LiveCompany(cid, int(cik), subs.sic, parse_companyfacts(facts_json, cid),
                    sorted({e["accession"]: e for e in events}.values(), key=lambda e: e["filed_date"]),
                    rows, _shares(facts_json))
    c.latest_filing, c.facts_through = newest, through
    return c


class LiveStore:
    """Loaded companies, cached in memory for an hour."""

    TTL_S = 3600

    def __init__(self, sec: SecClient | None = None):
        self.sec = sec or SecClient()
        self.backend = install()
        self._cache: dict[int, LiveCompany] = {}
        self._lock = threading.Lock()

    def get(self, cik: int) -> LiveCompany:
        with self._lock:
            c = self._cache.get(int(cik))
            if c and time.time() - c.loaded_at < self.TTL_S:
                return c
            c = load_company(self.sec, int(cik))
            self.backend.put(c)
            self._cache[int(cik)] = c
            return c


def today() -> date:
    return date.today()


def raw_dir() -> Path:
    return Path(os.environ.get("RAW_CACHE_DIR", "data/raw"))
