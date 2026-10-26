"""Orchestrates B1: universe -> fetch+cache -> parse -> Dataset -> sinks (memory, JSONL, Postgres).

Raw responses hit disk (SecClient / macro clients) before anything parses them, so the whole load
re-runs with offline=True and no network. Gaps never abort the load; they are recorded per company.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import universe as _universe
from .concepts import Concept
from .events import detect_going_concern, extract_events, tag_going_concern
from .macro import DEFAULT_SERIES, FredClient, MacroSkipped, StooqClient
from .parse import parse_companyfacts
from .sec import WWW, CacheMiss, NotFound, SecClient, SecError, pad_cik

UNIVERSE_FILE = Path(__file__).resolve().parent / "universe.json"  # Person A, frozen (README 4.2)
PROCESSED = Path(__file__).resolve().parent.parent / "data" / "processed"


@dataclass
class Dataset:
    companies: list[dict] = field(default_factory=list)
    facts: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    macro: list[dict] = field(default_factory=list)
    prices: list[dict] = field(default_factory=list)
    gaps: dict[str, list[str]] = field(default_factory=dict)  # company_id or 'macro' -> problems

    def gap(self, key: str, msg: str) -> None:
        self.gaps.setdefault(key, []).append(msg)

    def backend(self):
        """In-memory backend for store/queries.py (`store.queries.set_backend(ds.backend())`)."""
        from schemas import Event, Fact, Point
        from store.queries import InMemoryBackend

        def keep(model, rows):  # schemas/ models forbid extra keys (source_tag, going_concern_hits ...)
            return [{k: v for k, v in r.items() if k in model.model_fields} for r in rows]
        return InMemoryBackend(keep(Fact, self.facts), keep(Event, self.events), keep(Point, self.macro))


# ---- universe -----------------------------------------------------------------------------------

COMPANY_KEYS = ("company_id", "cik", "ticker", "name", "sector", "covid_group", "held_out", "short_history", "sic")


def read_universe(universe_file: Path | None = UNIVERSE_FILE) -> list[dict]:
    """Person A's company list. The default file is validated (50 companies, 10 held out); a custom
    file is read leniently (tests, ad-hoc lists). None or a missing file gives []."""
    if not universe_file or not Path(universe_file).is_file():
        return []
    if Path(universe_file).resolve() == UNIVERSE_FILE.resolve():
        return _universe.load_universe(Path(universe_file))
    raw = json.loads(Path(universe_file).read_text())
    return list(raw.get("companies", raw) if isinstance(raw, dict) else raw)


def resolve_universe(sec: SecClient, tickers: list[str] | None = None,
                     universe_file: Path | None = UNIVERSE_FILE) -> list[dict]:
    """Company rows (exactly store/schema.sql `companies` columns) for `tickers` (tickers or CIKs),
    or for the whole universe when `tickers` is None. company_id, sector, covid_group and held_out
    come from the universe file; the CIK is resolved from SEC company_tickers.json when the file has
    none. A ticker outside the universe gets the next free anon id, held_out=False."""
    meta = {str(c["ticker"]).upper(): c for c in read_universe(universe_file)}
    by_ticker = {v["ticker"].upper(): v for v in sec.company_tickers().values()}
    used = {m["company_id"] for m in meta.values() if m.get("company_id")}
    nxt = iter(i for i in range(1, 10_000) if f"anon_{i:03d}" not in used)
    out = []
    for t in (tickers if tickers is not None else list(meta)):
        key = t.upper()
        if t.isdigit():
            hit = next((v for v in by_ticker.values() if int(v["cik_str"]) == int(t)), {})
            m = next((c for c in meta.values() if c.get("cik") and int(c["cik"]) == int(t)), {})
            if not m and hit:
                m = meta.get(hit["ticker"].upper(), {})
        else:
            hit, m = by_ticker.get(key, {}), meta.get(key, {})
        cik = m.get("cik") or hit.get("cik_str")
        cid = m.get("company_id") or f"anon_{next(nxt):03d}"
        out.append({"company_id": cid, "cik": pad_cik(cik) if cik is not None else None,
                    "ticker": (hit.get("ticker") or m.get("ticker") or key).upper(),
                    "name": m.get("name") or hit.get("title", key), "sector": m.get("sector"),
                    "covid_group": m.get("covid_group"), "held_out": bool(m.get("held_out", False)),
                    "short_history": bool(m.get("short_history", False)),
                    "sic": m.get("sic"), **({"_unresolved": True} if cik is None else {})})
    return out


# ---- load ---------------------------------------------------------------------------------------

def load(tickers: list[str] | None, sec: SecClient, *, concept_map: dict[str, Concept] | None = None,
         fred: FredClient | None = None, series: list[str] | None = None,
         stooq: StooqClient | None = None, filing_text: bool = False,
         universe_file: Path | None = UNIVERSE_FILE) -> Dataset:
    ds = Dataset()
    # A company that re-registered under a new CIK (Disney 2019, Exxon 2026) keeps its older filings under
    # the old CIK. `prior_ciks` in the universe file loads those under the same company_id.
    prior = {str(m["ticker"]).upper(): m.get("prior_ciks") or [] for m in read_universe(universe_file)}
    for c in resolve_universe(sec, tickers, universe_file):
        cid = c["company_id"]
        if c.pop("_unresolved", False):
            ds.gap(cid, f"ticker {c['ticker']} not found in company_tickers.json")
            ds.companies.append(c)  # not written to Postgres: cik is NOT NULL
            continue
        try:
            sub = sec.submissions(c["cik"])
            c["sic"] = c["sic"] or (str(sub["sic"]) if sub.get("sic") else None)
        except (NotFound, CacheMiss, SecError):
            pass  # reported below by the submissions step
        ds.companies.append(c)
        try:
            ds.facts += parse_companyfacts(cid, sec.companyfacts(c["cik"]), concept_map)
        except (NotFound, CacheMiss, SecError) as e:
            ds.gap(cid, f"companyfacts: {e}")
        try:
            events = extract_events(cid, sec.all_submission_filings(c["cik"]), cik=c["cik"])
            if filing_text:
                tag_going_concern(events, _text_reader(sec))
            ds.events += events
        except (NotFound, CacheMiss, SecError) as e:
            ds.gap(cid, f"submissions: {e}")
        for old in prior.get(c["ticker"], []):
            try:
                ds.facts += parse_companyfacts(cid, sec.companyfacts(old), concept_map)
                events = extract_events(cid, sec.all_submission_filings(old), cik=pad_cik(old))
                if filing_text:
                    tag_going_concern(events, _text_reader(sec))
                ds.events += events
            except (NotFound, CacheMiss, SecError) as e:
                ds.gap(cid, f"prior CIK {old}: {e}")
        if stooq:
            try:
                ds.prices += [{"company_id": cid, **p} for p in stooq.prices(c["ticker"])]
            except Exception as e:  # prices are context only; never fail the load
                ds.gap(cid, f"prices: {e}")
    if fred:
        for s in series or DEFAULT_SERIES:
            try:
                ds.macro += fred.series(s)
            except MacroSkipped as e:
                ds.gap("macro", f"{s}: {e}")
            except Exception as e:
                ds.gap("macro", f"{s}: {type(e).__name__}: {e}")
    return ds


def _text_reader(sec: SecClient):
    def read(e: dict) -> str | None:
        try:
            return sec.get(f"{WWW}/Archives/edgar/data/{e['text_ref']}").decode("utf-8", "replace")
        except SecError:
            return None
    return read


# ---- sinks --------------------------------------------------------------------------------------

TABLES = ("companies", "facts", "events", "macro", "prices")


def _enc(o):
    if isinstance(o, date):
        return o.isoformat()
    raise TypeError(o)


def write_jsonl(ds: Dataset, out_dir: Path | str = PROCESSED) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for t in TABLES:
        with open(out / f"{t}.jsonl", "w") as f:
            for r in getattr(ds, t):
                f.write(json.dumps(r, default=_enc) + "\n")
    (out / "gaps.json").write_text(json.dumps(ds.gaps, indent=1))
    return out


_DATE_FIELDS = {"period_start", "period_end", "filed_date", "obs_date", "vintage_date", "date"}


def read_jsonl(in_dir: Path | str = PROCESSED) -> Dataset:
    d, ds = Path(in_dir), Dataset()
    for t in TABLES:
        p = d / f"{t}.jsonl"
        if p.is_file():
            rows = [json.loads(line) for line in p.read_text().splitlines() if line]
            for r in rows:
                for k in _DATE_FIELDS & r.keys():
                    r[k] = date.fromisoformat(r[k]) if r[k] else None
            setattr(ds, t, rows)
    if (d / "gaps.json").is_file():
        ds.gaps = json.loads((d / "gaps.json").read_text())
    return ds


SCHEMA_FILE = Path(__file__).resolve().parent.parent / "store" / "schema.sql"

# Insert columns per table: exactly store/schema.sql minus DB-generated ones (id, period_start_key).
# tests/test_schema_contract.py checks these, the parsers' row keys and schema.sql stay in sync.
COLUMNS = {
    "companies": ("company_id", "cik", "ticker", "name", "sector", "covid_group", "held_out", "short_history", "sic"),
    "facts": ("company_id", "concept", "source_tag", "value", "unit", "period_start", "period_end",
              "fiscal_year", "fiscal_period", "form", "accession", "filed_date"),
    "events": ("company_id", "form", "items", "filed_date", "accession", "text_ref", "going_concern_hits"),
    "macro": ("series_id", "value", "obs_date", "vintage_date"),
    "prices": ("company_id", "date", "close"),
}
_CONFLICT = {
    "companies": "ON CONFLICT (company_id) DO UPDATE SET " + ",".join(
        f"{c}=EXCLUDED.{c}" for c in COLUMNS["companies"][1:]),
    # restatements are new rows (different accession); re-runs from the raw cache never duplicate
    "facts": "ON CONFLICT (company_id, concept, unit, period_start_key, period_end, accession) DO NOTHING",
    "events": "ON CONFLICT (company_id, accession) DO UPDATE SET items=EXCLUDED.items,"
              "text_ref=EXCLUDED.text_ref,going_concern_hits=EXCLUDED.going_concern_hits",
    "macro": "ON CONFLICT (series_id, obs_date, vintage_date) DO NOTHING",
    "prices": "ON CONFLICT (company_id, date) DO UPDATE SET close=EXCLUDED.close",
}


def write_postgres(ds: Dataset, url: str, *, apply_schema: bool = True, connect=None) -> dict[str, int]:
    """Idempotent upsert into store/schema.sql tables (re-running never duplicates or deletes rows).
    `connect` is injectable for tests; by default psycopg is imported lazily. Companies without a
    resolved CIK are skipped (cik is NOT NULL) along with their rows. Returns rows sent per table."""
    if connect is None:
        import psycopg  # lazy: optional dependency
        connect = psycopg.connect
    ok = {c["company_id"] for c in ds.companies if c.get("cik")}
    counts: dict[str, int] = {}
    with connect(url) as conn, conn.cursor() as cur:
        if apply_schema:
            cur.execute(SCHEMA_FILE.read_text())
        for t in ("companies", "facts", "events", "macro", "prices"):
            cols = COLUMNS[t]
            rows = [r for r in getattr(ds, t) if t == "macro" or r["company_id"] in ok]
            counts[t] = len(rows)
            if rows:
                cur.executemany(f"INSERT INTO {t} ({','.join(cols)}) VALUES ({','.join(['%s'] * len(cols))}) "
                                f"{_CONFLICT[t]}", [tuple(r.get(c) for c in cols) for r in rows])
    return counts


RUNS_DIR = Path(__file__).resolve().parent.parent / "data" / "runs"


def write_runs_companies(ds: Dataset, runs_dir: Path | str = RUNS_DIR) -> Path:
    """`companies.jsonl` for dashboard/data.py and api/service.py (company_id + sector). Anonymous
    columns only: ticker and name never leave the store, and data/runs may be shipped."""
    path = Path(runs_dir) / "companies.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    keep = ("company_id", "sector", "covid_group", "held_out")
    path.write_text("".join(json.dumps({k: c.get(k) for k in keep}) + "\n" for c in ds.companies))
    return path
