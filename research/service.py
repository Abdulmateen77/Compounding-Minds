"""One call from a search box to a finished report: find the company, load its filings, write the report."""
from __future__ import annotations

import os
import threading
import time
from datetime import date, timedelta

from ingest.sec import SecClient

from concurrent.futures import ThreadPoolExecutor

from . import chat, live, market, narrative, resolve, text, web
from .report import build_report

REPORT_TTL_S = 1800
LISTINGS_TTL_S = 6 * 3600
SHARES_MAX_AGE_DAYS = 400       # a cover-page share count older than this is not trusted for market value
NOT_FOUND = ("No US-listed company matches “{q}”. This version covers companies listed on US exchanges "
             "(NYSE, Nasdaq). London and European listings are not covered yet.")


class ResearchService:
    def __init__(self, sec: SecClient | None = None, gateway=None, use_model: bool = True, use_news: bool = True):
        self.sec = sec or SecClient()
        self.store = live.LiveStore(self.sec)
        self._gateway, self._use_model, self._use_news = gateway, use_model, use_news
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

    # ---- one-on-one chat with an investor lens ------------------------------------------------------------------
    def chat(self, cik: int, lens_key: str, question: str, history: list[dict] | None = None) -> dict | None:
        """Answer a reader's question about one lens of this company's report; None if the report or lens does not exist."""
        report = self.report(int(cik))
        lens = next((l for l in (report.get("analysis") or {}).get("lenses", []) if l["key"] == lens_key), None)
        if not report.get("supported") or lens is None:
            return None
        return chat.answer(self._gw(), report, lens, question, history)

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
        gw = self._gw()
        with ThreadPoolExecutor(max_workers=3) as pool:          # the filing text, the news and the price side by side
            f_plans = pool.submit(text.read_plans, self.sec, cik, c.filings, gw)
            f_news = pool.submit(web.build, gw, profile["name"], profile["ticker"]) if self._use_news else None
            f_quote = pool.submit(market.quote, profile["ticker"]) if profile["ticker"] else None
            plans = f_plans.result()
            news = f_news.result() if f_news else None
            quote = f_quote.result() if f_quote else None
        shares = market.shares_outstanding(c.shares)
        if shares and date.fromisoformat(shares[1]) < today - timedelta(days=SHARES_MAX_AGE_DAYS):
            shares = None
        report = build_report(c.company_id, today, profile, quote=quote, shares=shares, plans=plans, share_history=c.share_history)
        report["news"] = news
        report["latest_filing"] = c.latest_filing
        report["facts_through"] = c.facts_through
        report["checked_at"] = time.strftime("%Y-%m-%d")
        if gw is not None and report.get("supported"):
            figs = [str(round(f["value"] * 100, 1)) for sec in report["sections"] for f in sec["figures"] if f["value"] is not None and f["unit"] == "pct"]
            narrative.attach(gw, report["analysis"], profile["name"], figs, [l["text"] for l in (news or {}).get("lines", [])])
        report["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        report["sec_url"] = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik:010d}&type=10-K"
        return report
