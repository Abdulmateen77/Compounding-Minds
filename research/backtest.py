"""Do the investor checks mean anything? Run them at every past quarter and compare with what happened next.

For each of the 50 companies and each quarter-end from 2018Q1 to 2023Q4, build the same report the app builds
(as of that date, through the same date gate, so it sees only filings public then), take the Buffett and Munger
fits, and look up what happened over the next twelve months in later filings:

  Buffett fit  vs  revenue growth over the next year, and the free-cash-flow margin a year on
  Munger fit   vs  an auditor change or a dividend cut within the next year. A cut here must last two quarters (see
                   research/dividends.py): the grader's single-quarter rule mistakes payment timing for cuts

No model is involved, so it costs nothing and is exactly repeatable. Graham's price check and the valuation need a
share price, which the database does not hold for the past, so they are not tested here.

    python -m research.backtest                       # writes data/backtest/lens_backtest.jsonl and prints the summary
    python -m research.backtest --summary-only
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from grader.risk import check_auditor_change, window_end
from ingest.universe import load_universe
from metrics.context import Context
from store import queries

from . import dividends
from .report import Base, build_report

OUT = Path(__file__).resolve().parent.parent / "data" / "backtest" / "lens_backtest.jsonl"
FIRST, LAST = date(2018, 3, 31), date(2023, 12, 31)
LOOK_AHEAD_DAYS = 455          # a year plus the filing delay, so the 4th following quarter has been filed


def quarter_ends(first: date = FIRST, last: date = LAST) -> list[date]:
    out, y, q = [], first.year, (first.month - 1) // 3
    while True:
        m = 3 * q + 3
        d = date(y, m, 31 if m in (3, 12) else 30)
        if d > last:
            return out
        if d >= first:
            out.append(d)
        q += 1
        if q == 4:
            y, q = y + 1, 0


def outcomes(cid: str, as_of: date, q0: date) -> dict:
    """What happened over the following year, read from filings public by as_of + a year and a quarter."""
    later = Context(cid, as_of + timedelta(days=LOOK_AHEAD_DAYS))
    now = Context(cid, as_of)
    nxt = next((e for e in later.timeline if 350 <= (e - q0).days <= 380), None)
    out = {"growth_next": None, "fcf_margin_next": None}
    if nxt is not None:
        rev_now, rev_next = now.ttm("revenue", q0), later.ttm("revenue", nxt)
        if rev_now and rev_next and rev_now.value > 0:
            out["growth_next"] = rev_next.value / rev_now.value - 1
            b = Base(later, nxt)
            if b.fcf is not None and rev_next.value > 0:
                out["fcf_margin_next"] = b.fcf.value / rev_next.value
    end = window_end(as_of)
    events = [e for e in queries.get_events(cid, end) if as_of < e.filed_date <= end]
    aud, _ = check_auditor_change(events)
    div = dividends.cut_in_window(later, as_of, end)          # persistence rule, same definition as the report's check
    out["auditor_change"] = 1 if aud == "yes" else 0
    out["dividend_cut"] = div
    out["distress"] = 1 if (aud == "yes" or div == 1) else (None if div is None else 0)
    return out


def run(out_path: Path = OUT, companies: list[dict] | None = None, quarters: list[date] | None = None) -> int:
    queries.use_postgres()
    companies = companies or load_universe()
    quarters = quarters or quarter_ends()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out_path.open("w", encoding="utf-8") as f:
        for c in companies:
            cid = c["company_id"]
            for as_of in quarters:
                try:
                    r = build_report(cid, as_of, {"name": cid, "ticker": None, "exchange": None, "market": "US", "cik": 0})
                    if not r["supported"]:
                        continue
                    fits = {l["key"]: l["fit"] for l in r["analysis"]["lenses"]}
                    row = {"company_id": cid, "as_of": as_of.isoformat(), "held_out": bool(c.get("held_out")),
                           "fit": fits, **outcomes(cid, as_of, date.fromisoformat(r["data_through"]))}
                except Exception as e:                       # one bad company-quarter must not stop the run
                    print(f"skip {cid} {as_of}: {type(e).__name__}: {e}", file=sys.stderr)
                    continue
                f.write(json.dumps(row) + "\n")
                n += 1
            print(f"{cid} done ({n} rows)", file=sys.stderr, flush=True)
    return n


# ---- the summary -----------------------------------------------------------------------------------------------
def _rank(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks, i = [0.0] * len(xs), 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) < 10:
        return None
    rx, ry = _rank(x), _rank(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return None if den == 0 else num / den


def permutation_p(x: list[float], y: list[float], rho: float, n: int = 2000, seed: int = 7) -> float:
    """Two-sided: how often does shuffling the outcomes give a correlation as strong?"""
    import random
    rng = random.Random(seed)
    ys, hits = list(y), 0
    for _ in range(n):
        rng.shuffle(ys)
        r = spearman(x, ys)
        hits += r is not None and abs(r) >= abs(rho)
    return (hits + 1) / (n + 1)


BUCKETS = [("High (0.70 or more)", 0.70, 1.01), ("Middle (0.40 to 0.70)", 0.40, 0.70), ("Low (under 0.40)", -0.01, 0.40)]


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def summarise(path: Path = OUT, held_out: bool | None = None, year_end_only: bool = False) -> dict:
    """`year_end_only` keeps one quarter per company per year, so the twelve-month windows do not overlap."""
    rows = [json.loads(l) for l in path.open(encoding="utf-8")]
    if held_out is not None:
        rows = [r for r in rows if r["held_out"] == held_out]
    if year_end_only:
        rows = [r for r in rows if r["as_of"].endswith("-12-31")]
    tests = [("buffett", "growth_next", "Revenue growth over the next year"),
             ("buffett", "fcf_margin_next", "Free-cash-flow margin a year later"),
             ("munger", "distress", "Auditor change or dividend cut within a year")]
    out = {"rows": len(rows), "tests": []}
    for lens, key, label in tests:
        pairs = [(r["fit"][lens], r[key]) for r in rows if r["fit"].get(lens) is not None and r.get(key) is not None]
        t = {"lens": lens, "outcome": label, "n": len(pairs), "buckets": []}
        for name, lo, hi in BUCKETS:
            ys = [y for x, y in pairs if lo <= x < hi]
            t["buckets"].append({"bucket": name, "n": len(ys), "mean": sum(ys) / len(ys) if ys else None, "median": _median(ys)})
        xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
        rho = spearman(xs, ys)
        t["spearman"] = rho
        t["p"] = None if rho is None else permutation_p(xs, ys, rho)
        out["tests"].append(t)
    return out


def format_summary(s: dict) -> str:
    lines = [f"{s['rows']} company-quarters"]
    for t in s["tests"]:
        lines.append(f"\n{t['lens'].title()} fit vs {t['outcome'].lower()} (n={t['n']})")
        for b in t["buckets"]:
            m = "n/a" if b["mean"] is None else (f"{b['mean'] * 100:.1f}%")
            md = "n/a" if b["median"] is None else (f"{b['median'] * 100:.1f}%")
            lines.append(f"   {b['bucket']:<24} n={b['n']:<5} typical (median) {md:<8} average {m}")
        if t["spearman"] is not None:
            lines.append(f"   rank correlation {t['spearman']:+.3f}, shuffle-test p = {t['p']:.3f}")
    return "\n".join(lines)


EVIDENCE = Path(__file__).resolve().parent / "evidence.json"


def write_evidence(path: Path = OUT, dest: Path = EVIDENCE) -> dict:
    """The small summary the app shows (the 1,184-row file itself stays in data/, which is not committed)."""
    out = {"window": "2018 Q1 to 2023 Q4", "companies": 50, "horizon": "the next twelve months",
           "all_quarters": summarise(path), "year_end_only": summarise(path, year_end_only=True),
           "held_out_year_end": summarise(path, held_out=True, year_end_only=True)}
    dest.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--summary-only", action="store_true")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--write-evidence", action="store_true", help="also write research/evidence.json for the app")
    a = ap.parse_args(argv)
    if not a.summary_only:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
        print(f"wrote {run(Path(a.out))} rows to {a.out}")
    print(format_summary(summarise(Path(a.out))))
    if a.write_evidence:
        write_evidence(Path(a.out))
        print(f"wrote {EVIDENCE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
