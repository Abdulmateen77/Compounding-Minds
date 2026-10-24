"""Load raw SEC and FRED files from the cache into Postgres. Works fully offline.

Person B's fetchers do the network part: download each file into the cache under the names
below (never re-download a file that is already there). Everything after that is here:

    data/raw/sec/companyfacts/CIK0000320193.json
    data/raw/sec/submissions/CIK0000320193.json                    newest ~1000 filings
    data/raw/sec/submissions/CIK0000320193-submissions-001.json    older pages, named in `files`
    data/raw/sec/filings/<cik>/<accession>/<document>              10-K/10-Q text (going concern)
    data/raw/fred/GDPC1.json                                       one file per series

Cache root: the RAW_CACHE_DIR environment variable, default `data/raw` (gitignored).
Every loader is idempotent.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg

from store import db
from store.concepts import MACRO_SERIES

from .parse_facts import parse_companyfacts
from .parse_fred import parse_fred
from .parse_submissions import parse_filings_block, parse_submissions
from .universe import load_universe


def cache_root() -> Path:
    return Path(os.environ.get("RAW_CACHE_DIR", "data/raw"))


def cik10(cik: str | int) -> str:
    return f"CIK{int(cik):010d}"


def companyfacts_path(cik, root: Path | None = None) -> Path:
    return (root or cache_root()) / "sec" / "companyfacts" / f"{cik10(cik)}.json"


def submissions_path(cik, root: Path | None = None) -> Path:
    return (root or cache_root()) / "sec" / "submissions" / f"{cik10(cik)}.json"


def fred_path(series_id: str, root: Path | None = None) -> Path:
    return (root or cache_root()) / "fred" / f"{series_id}.json"


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_companies(conn: psycopg.Connection, cik_by_ticker: dict[str, str]) -> dict:
    """Insert the universe. `cik_by_ticker` comes from the SEC company_tickers.json (Person B)."""
    rows, unresolved = [], []
    for c in load_universe():
        cik = cik_by_ticker.get(c["ticker"])
        if cik is None:
            unresolved.append(c["ticker"])
            continue
        rows.append({**{k: c[k] for k in ("company_id", "ticker", "name", "sector", "covid_group", "held_out", "short_history")},
                     "cik": str(int(cik))})
    db.upsert_companies(conn, rows)
    return {"loaded": len(rows), "unresolved_tickers": unresolved}


def load_company(conn: psycopg.Connection, company_id: str, cik: str | int, root: Path | None = None) -> dict:
    """Load one company's cached files. Missing files are reported, not raised."""
    report = {"company_id": company_id, "facts_rows": 0, "events_rows": 0, "missing": []}
    facts_file = companyfacts_path(cik, root)
    if facts_file.exists():
        rows = parse_companyfacts(_read(facts_file), company_id)
        db.insert_facts(conn, rows)
        report["facts_rows"] = len(rows)
    else:
        report["missing"].append(str(facts_file))

    sub_file = submissions_path(cik, root)
    if sub_file.exists():
        sub = parse_submissions(_read(sub_file), company_id)
        events = list(sub.events)
        for name in sub.extra_files:
            extra = sub_file.parent / name
            if extra.exists():
                events += parse_filings_block(_read(extra), company_id)
            else:
                report["missing"].append(str(extra))
        db.set_sic(conn, company_id, sub.sic)
        db.insert_events(conn, events)
        report["events_rows"] = len(events)
    else:
        report["missing"].append(str(sub_file))
    return report


def load_macro(conn: psycopg.Connection, root: Path | None = None) -> dict:
    report: dict = {"series_rows": {}, "missing": []}
    for series_id, _, _ in MACRO_SERIES.values():
        f = fred_path(series_id, root)
        if not f.exists():
            report["missing"].append(str(f))
            continue
        rows = parse_fred(_read(f), series_id)
        db.insert_macro(conn, rows)
        report["series_rows"][series_id] = len(rows)
    return report


def load_all(conn: psycopg.Connection, cik_by_ticker: dict[str, str], root: Path | None = None) -> dict:
    """Companies, then every company's cached files, then macro. Safe to re-run."""
    report = {"companies": load_companies(conn, cik_by_ticker), "per_company": [], "macro": {}}
    with conn.cursor() as cur:
        cur.execute("SELECT company_id, cik FROM companies ORDER BY company_id")
        companies = cur.fetchall()
    for company_id, cik in companies:
        report["per_company"].append(load_company(conn, company_id, cik, root))
    report["macro"] = load_macro(conn, root)
    return report
