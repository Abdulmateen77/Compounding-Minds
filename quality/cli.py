"""Build the held-out report and the quality report.

    python -m quality.cli --out quality/out                  read scored calls from DATABASE_URL
    python -m quality.cli --runs data/runs_final --out quality/out   read a replay's JSONL output
    python -m quality.cli --demo --out quality/out           synthetic data, no database (labelled as such)

Writes quality/out/heldout.json (the dashboard's contract) and quality/out/quality.md.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .report import write_reports

CONNECT_TIMEOUT_S = 5


def _parse_attempted(items: list[str]) -> dict[str, int]:
    out = {}
    for item in items:
        agent, sep, n = item.partition("=")
        if not sep or not n.isdigit():
            raise SystemExit(f"--attempted wants agent=count, for example fundamentals=2400 (got {item!r})")
        out[agent] = int(n)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m quality.cli", description=__doc__.split("\n\n")[0])
    p.add_argument("--out", default="quality/out", help="directory for heldout.json and quality.md")
    p.add_argument("--demo", action="store_true", help="use labelled synthetic data and no database")
    p.add_argument("--runs", default=None, help="read a replay's JSONL directory (data/runs_final) instead of Postgres")
    p.add_argument("--run-id", action="append", default=None, help="only these runs (repeatable)")
    p.add_argument("--attempted", action="append", default=[], metavar="AGENT=N",
                   help="calls attempted per agent, for the valid-JSON rate (repeatable). The runner drops "
                        "invalid replies, so this cannot be recovered from the database")
    args = p.parse_args(argv)

    from ingest.universe import held_out_ids  # no database needed

    held_out = held_out_ids()
    attempted = _parse_attempted(args.attempted)
    extra_notes: list[str] = []
    if args.runs:
        from .load import load_scored_dir
        scored = load_scored_dir(args.runs, args.run_id)
        if not scored:
            print(f"no graded calls in {args.runs}", file=sys.stderr)
            return 2
    elif args.demo:
        from .demo import DEMO_NOTE, demo_attempted, demo_scored
        scored = demo_scored(held_out=set(held_out))
        attempted = attempted or demo_attempted(scored)
        extra_notes.append(DEMO_NOTE)
    else:
        import psycopg
        from store import db
        from .load import load_scored
        url = db.database_url()
        try:
            # db.connect() has no timeout, and on Windows a refused connection can hang for about two
            # minutes before failing. Fail in seconds so a down database is not mistaken for a freeze.
            with psycopg.connect(url, connect_timeout=CONNECT_TIMEOUT_S) as conn:
                scored = load_scored(conn, args.run_id)
        except Exception as err:  # connection refused, missing tables, bad credentials
            print(f"could not read scored calls from {url.rsplit('@', 1)[-1]}: {err.__class__.__name__}: {err}\n"
                  "Start Postgres and set DATABASE_URL, or try --demo.", file=sys.stderr)
            return 2

    heldout, heldout_path, quality_path = write_reports(args.out, scored, held_out, attempted=attempted or None,
                                                        extra_notes=extra_notes)
    print(f"wrote {heldout_path}")
    print(f"wrote {quality_path}")
    print(f"{len(scored)} scored calls, {len(heldout['agents'])} agents, {len(heldout['notes'])} notes")
    for note in heldout["notes"]:
        print(f"  note: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
