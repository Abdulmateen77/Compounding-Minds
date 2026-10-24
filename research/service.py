"""One call from a search box to a finished report: find the company, load its filings, write the report."""
from __future__ import annotations

import os
import threading
import time
from datetime import date, timedelta

from ingest.sec import SecClient

from . import live, market, narrative, resolve, text
from .report import build_report

REPORT_TTL_S = 1800
LISTINGS_TTL_S = 6 * 3600
SHARES_MAX_AGE_DAYS = 400       # a cover-page share count older than this is not trusted for market value
NOT_FOUND = ("No US-listed company matches “{q}”. This version covers companies listed on US exchanges "
             "(NYSE, Nasdaq). London and European listings are not covered yet.")


class ResearchService:
    def __init__(self, sec: SecClient | None = None, gateway=None, use_model: bool = True):
        self.sec = sec or SecClient()
        self.store = live.LiveStore(self.sec)
        self._gateway, self._use_model = gateway, use_model
        self._listings: tuple[float, list[resolve.Candidate]] | None = None
        self._reports: dict[int, tuple[float, dict]] = {}
        self._locks: dict[int, threading.Lock] = {}
        self._lock = threading.Lock()

    # ---- search ----------------------------------------------------------------------------------------------
    def listings(self) -> list[resolve.Candidate]:
        with self._lock:
            if self._listings is None or time.time() - self._listings[0] > LISTINGS_TTL_S:
                self._listings = (time.time(), resolve.load_listings(self.sec))
            return self._listings[1]

    def search(self, q: str) -> dict:
        found = resolve.search(q, self.listings())
        return {"query": q, "results": [c.as_dict() for c in found],
                "message": None if found else NOT_FOUND.format(q=q.strip())}

    # ---- report ----------------------------------------------------------------------------------------------
    def _gw(self):
        if self._gateway is not None or not self._use_model:
            return self._gateway
        if os.environ.get("MUBIT_API_KEY"):
            from agents.gateway import MubitGateway
            self._gateway = MubitGateway()
        return self._gateway

    def report(self, cik: int, force: bool = False) -> dict:
        with self._lock:
            lock = self._locks.setdefault(int(cik), threading.Lock())
        with lock:                                  # two people opening one company run the work once
            hit = self._reports.get(int(cik))
            if hit and not force and time.time() - hit[0] < REPORT_TTL_S:
                return hit[1]
            out = self._build(int(cik))
            self._reports[int(cik)] = (time.time(), out)
            return out

    def _build(self, cik: int) -> dict:
        listing = next((c for c in self.listings() if c.cik == cik), None)
        c = self.store.get(cik)
        profile = ({"name": listing.name, "ticker": listing.ticker, "exchange": listing.exchange, "market": "US"}
                   if listing else {"name": f"CIK {cik}", "ticker": None, "exchange": None, "market": "US"})
        profile["cik"] = cik
        profile["sic"] = c.sic
        today = date.today()
        plans = text.read_plans(self.sec, cik, c.filings, self._gw())
        quote = market.quote(profile["ticker"]) if profile["ticker"] else None
        shares = market.shares_outstanding(c.shares)
        if shares and date.fromisoformat(shares[1]) < today - timedelta(days=SHARES_MAX_AGE_DAYS):
            shares = None
        report = build_report(c.company_id, today, profile, quote=quote, shares=shares, plans=plans)
        gw = self._gw()
        if gw is not None and report.get("supported"):
            figs = [str(round(f["value"] * 100, 1)) for sec in report["sections"] for f in sec["figures"] if f["value"] is not None and f["unit"] == "pct"]
            narrative.attach(gw, report["analysis"], profile["name"], figs)
        report["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        report["sec_url"] = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik:010d}&type=10-K"
        return report
