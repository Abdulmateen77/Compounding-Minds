# Ingestion guide (for Person B)

> **Which loader to use.** Person B's `python -m ingest` (`ingest/sec.py`, `load.py`, `parse.py`, `events.py`,
> `macro.py`) is the loader of record: it has the rate-limited, caching SEC client and writes to Postgres.
> The files described below (`parse_facts.py`, `parse_submissions.py`, `parse_fred.py`, `pipeline.py`) are
> Person A's earlier, separately tested implementation of the same load from a raw-file cache. They are kept as
> a reference and as a cross-check, not as a second way to load data. Do not run both against one database:
> they store the CIK in different formats (B pads to 10 digits, A does not).

Person A built everything on the far side of the network call: what the data *is*, how raw SEC and
FRED files become rows, and how rows get into Postgres and back out through the date gate. Your job
is the part in the middle that touches the internet: **download the raw files into the cache.** Once
a file is in the cache, `ingest/pipeline.py` loads it. Nothing else needs writing to get real data
flowing.

```
 your fetchers  ->  data/raw/...  ->  ingest/pipeline.py  ->  Postgres  ->  store/queries.py (date gate)
 (network, B)       (cache, B)        (parse + load, done)    (done)       (done)
```

## 1. Set up (5 minutes)

```bash
cp .env.example .env                 # then fill in SEC_USER_AGENT and FRED_API_KEY
docker compose up -d                 # Postgres 16 on localhost:5432
pip install -r requirements.txt
python -m store.migrate              # creates every table. Safe to re-run
python -m pytest -q                  # database tests run against it too (they skip if it is down)
```

`SEC_USER_AGENT` must be a real name and email, for example `"Jane Doe jane@example.com"`. The SEC blocks
requests without one. A free FRED key is at fred.stlouisfed.org/docs/api/api_key.html.

## 2. What to download, and where it goes

Cache root is `RAW_CACHE_DIR` (default `data/raw`, gitignored). **Never download a file that is already
there**, and save the response exactly as received: the loaders re-run from these files with no network.

| What | URL | Save as |
|---|---|---|
| Ticker to CIK map | `https://www.sec.gov/files/company_tickers.json` | `sec/company_tickers.json` |
| Financial facts | `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` | `sec/companyfacts/CIK##########.json` |
| Filing list | `https://data.sec.gov/submissions/CIK##########.json` | `sec/submissions/CIK##########.json` |
| Older filing pages | `https://data.sec.gov/submissions/<name>` for each name in the `files` list of the file above | `sec/submissions/<name>` |
| 10-K and 10-Q text | `ingest.parse_submissions.filing_url(cik, accession, document)` | `sec/filings/<cik>/<accession>/<document>` |
| GDP, unemployment | `https://api.stlouisfed.org/fred/series/observations?series_id=GDPC1&file_type=json&realtime_start=1776-07-04&realtime_end=9999-12-31&api_key=...` (same with `UNRATE`) | `fred/GDPC1.json`, `fred/UNRATE.json` |
| Yield curve, credit spread | same URL without the two `realtime_` parameters, `series_id=T10Y2Y` and `BAA10Y` | `fred/T10Y2Y.json`, `fred/BAA10Y.json` |

`CIK##########` is the CIK left-padded to 10 digits. `ingest.pipeline.companyfacts_path(cik)`,
`submissions_path(cik)` and `fred_path(series_id)` give you the exact path for each file, so you never
build one by hand.

Rules:
- **SEC:** send the `User-Agent` header, stay under about 10 requests a second, ask for gzip.
- **FRED:** about 120 requests a minute. The revised series (GDP, unemployment) **must** use the
  `realtime_start=1776-07-04&realtime_end=9999-12-31` window, so every vintage comes back. Without it we
  would see today's revised numbers in 2019, which is exactly the leakage we are testing against.
- **Universe:** the 50 companies are in `ingest/universe.json` (tickers only). Resolve each ticker to a CIK
  from `company_tickers.json`, then make `cik_by_ticker = {"AAPL": "320193", ...}`.

## 3. Load

```python
from store import db
from ingest import pipeline

with db.connect() as conn:
    report = pipeline.load_all(conn, cik_by_ticker)   # companies, then every company's files, then macro
```

- Idempotent: run it as often as you like, it never duplicates a row.
- Missing files are listed in `report`, not raised. Download them and run it again.
- To load one company while testing: `pipeline.load_company(conn, "anon_001", cik)`.

## 4. Check it worked

```python
from store.quality import coverage, drop_candidates
rep = coverage(conn)
print(drop_candidates(rep))     # companies missing a required concept, or with under ~5 years of revenue,
                                # and not accepted in store.quality.KNOWN_GAPS (store.quality.known_gaps lists those)
```

A company in that list cannot get the Fundamentals, Risk or Scenarios metrics. Tell Person A: it is either
a wrong tag in `store/concepts.py` (A fixes) or a company to drop from `ingest/universe.json`.

Then read through the gate, the way an agent will:

```python
from datetime import date
from store import queries, pg
queries.set_backend(pg.PostgresBackend(conn))
queries.get_facts("anon_001", "revenue", date(2019, 6, 30))   # only rows filed on or before that day
```

## 5. What is still yours (README, TASKS.md section 4)

- [ ] The fetchers above, with the rate limits and the "skip if cached" rule
- [ ] Going-concern text pass: for each 10-K and 10-Q event with a `text_ref`, download the document, count
      the passages with the keywords in `grader/config.py`, and write the count back with
      `db.insert_events` (it keeps the larger `going_concern_hits`). The grader and the Risk agent read it
- [ ] Prices (stretch, nothing in the MVP uses them)
- [ ] The ingest QA report. `store.quality.coverage` is the data half of it

## 6. Things that will bite you

- **`fy` and `fp` in `companyfacts` describe the filing, not the period.** We store them for reference only.
  Never use them to decide which quarter a fact belongs to; `period_start` and `period_end` do that.
- **The same number appears in many filings** (the prior-year comparative). That is expected: each copy
  has its own accession and filing date, and the gate returns the latest visible one.
- **A Q2 10-Q has two durations ending on the same day** (3 months and 6 months). Both are stored, and
  both are returned. Cash-flow items are year-to-date only; `metrics/SPEC.md` explains how a quarter is
  derived from them.
- **`submissions` holds only the newest ~1000 filings.** Older ones are in the extra pages listed under
  `files`. Download those too or early-year 8-K items will be missing.
- **A new tag is not a bug in the parser.** If a company's revenue is missing, find which us-gaap tag it
  uses in its `companyfacts` file and tell Person A to add it to `store/concepts.py`.
