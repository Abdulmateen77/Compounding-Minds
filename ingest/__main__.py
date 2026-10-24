"""python -m ingest load [--tickers AAPL MSFT] [--offline] [--fred] [--stooq] [--filing-text]
                         [--out data/processed] [--postgres [URL]] [--refresh]
python -m ingest report [--in data/processed]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .load import PROCESSED, load, read_jsonl, write_jsonl, write_postgres, write_runs_companies
from .macro import FredClient, StooqClient
from .qa import format_report, qa_report
from .sec import SecClient, SecError


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ingest")
    sub = ap.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("load")
    l.add_argument("--tickers", nargs="+", help="override: load only these (default: all of ingest/universe.json)")
    l.add_argument("--offline", action="store_true", help="cache only, no network, no User-Agent needed")
    l.add_argument("--refresh", action="store_true", help="refetch even if cached")
    l.add_argument("--fred", action="store_true", help="load FRED/ALFRED macro (needs FRED_API_KEY or cache)")
    l.add_argument("--series", nargs="+")
    l.add_argument("--stooq", action="store_true")
    l.add_argument("--filing-text", action="store_true", help="scan cached 10-K/10-Q text for going concern")
    l.add_argument("--out", default=str(PROCESSED))
    l.add_argument("--postgres", nargs="?", const=os.environ.get("DATABASE_URL", ""), default=None)
    l.add_argument("--runs-dir", help="also write companies.jsonl here for the dashboard/API (e.g. data/runs)")
    l.add_argument("--json", action="store_true", help="print the QA report as JSON")
    r = sub.add_parser("report")
    r.add_argument("--in", dest="inp", default=str(PROCESSED))
    a = ap.parse_args(argv)

    if a.cmd == "report":
        print(format_report(qa_report(read_jsonl(a.inp))))
        return 0
    try:
        sec = SecClient(offline=a.offline, refresh=a.refresh)
    except SecError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    try:
        ds = load(a.tickers, sec, fred=FredClient(offline=a.offline) if a.fred else None, series=a.series,
                  stooq=StooqClient(offline=a.offline) if a.stooq else None, filing_text=a.filing_text)
    except SecError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    write_jsonl(ds, a.out)
    if a.runs_dir:
        write_runs_companies(ds, a.runs_dir)
    if a.postgres:
        write_postgres(ds, a.postgres)
    rep = qa_report(ds)
    print(json.dumps(rep, indent=1, default=str) if a.json else format_report(rep))
    print(f"\nnetwork fetches: {sec.fetches}, cache hits: {sec.hits}; wrote {a.out}")
    return 0 if rep["totals"]["ok"] == rep["totals"]["companies"] else 1


if __name__ == "__main__":
    sys.exit(main())
