# Data Sources: Compounding Minds

Where every piece of data and agent context comes from. Data is fetched once from free public sources, cached raw on disk, loaded into Postgres, and read by agents only through one date-gated door.

Companions: [DATA_ARCHITECTURE.md](DATA_ARCHITECTURE.md) (diagrams), [ingest/README.md](ingest/README.md) (how to fetch and load).

---

## 1. External sources (fetched once, cached to `data/raw/`)

| # | Source | What it gives | Cached at | Code |
|---|---|---|---|---|
| 1 | SEC `company_tickers.json` | Ticker to CIK map for the 50-company universe | `data/raw/sec/www.sec.gov/files/` | [ingest/sec.py](ingest/sec.py) |
| 2 | SEC XBRL `companyfacts` | Every financial number (revenue, margins, FCF, debt, dividends) | `data/raw/sec/data.sec.gov/api/xbrl/` | [ingest/parse.py](ingest/parse.py), [store/concepts.py](store/concepts.py) |
| 3 | SEC `submissions` | Filing list, 8-K item codes, SIC, auditor changes | `data/raw/sec/data.sec.gov/submissions/` | [ingest/events.py](ingest/events.py) |
| 4 | SEC filing text (10-K, 10-Q) | Full text, scanned for going-concern notes | `data/raw/sec/www.sec.gov/Archives/` | `ingest/events.py` (`tag_going_concern`) |
| 5 | FRED / ALFRED | Macro with point-in-time vintages: `GDPC1`, `UNRATE` (vintaged), `T10Y2Y`, `BAA10Y` | `data/raw/fred/` | [ingest/macro.py](ingest/macro.py) |
| 6 | Stooq / Tiingo prices | Stretch, context only. `StooqClient` is built, nothing downloaded yet | none | `ingest/macro.py` |
| 7 | Firecrawl (press releases, FOMC) | Stretch, not built | none | none |

The universe is [ingest/universe.json](ingest/universe.json) (tickers only).

---

## 2. Store and the date gate

- **Parsed output:** `data/processed/` holds `companies.jsonl`, `facts.jsonl`, `events.jsonl`, `macro.jsonl`, `prices.jsonl` and `gaps.json`.
- **Postgres:** tables in [store/schema.sql](store/schema.sql). Every row carries `filed_date` (macro: `vintage_date`).
- **The gate:** [store/queries.py](store/queries.py) is the only reader of those tables (`get_facts`, `get_events`, `get_macro`, `get_metrics`). At as-of date `t` it returns only rows with `filed_date <= t`.
- **Stubs:** with `USE_STUBS=1`, data comes from `store/stubs/` instead.

---

## 3. Context each agent receives

1. **Investor principles:** [principles/](principles/) (`buffett.md`, `buffett_moat.md`, `graham.md`, `munger.md`, `dalio.md`). Own-words rules with citations, verification status in [principles/SOURCES.md](principles/SOURCES.md).
2. **Metric bundles:** [metrics/](metrics/) computes every number in Python from gated facts, events and macro, each traced to a filing accession.
3. **Read-only tools:** [tools/server.py](tools/server.py) exposes `get_metric_series`, `get_recent_events`, `get_macro_snapshot`, `peer_compare`.
4. **Lessons from past corrections:** carried in the per-agent Mubit model version ([agents/correction_loop.py](agents/correction_loop.py), [agents/reflection.py](agents/reflection.py)).
5. **Prompts:** built by [agents/adapters/](agents/adapters/) with anonymised company IDs (`anon_001`...) and relative quarters (Q-8 to Q0).

---

## 4. LLM and verifier services

| Service | Role | Config | Code |
|---|---|---|---|
| Mubit (`https://api.mubit.ai`) | Every LLM call routes through it. Responses cached in `data/llm_cache/`, docs in `data/mubit_docs/` | `MUBIT_BASE_URL`, `MUBIT_API_KEY` | [agents/gateway.py](agents/gateway.py) |
| Banyan Sapling verifier (Hugging Face endpoint) | Second check for going-concern grading | `SAPLING_URL` | [grader/sapling.py](grader/sapling.py) |

---

## 5. Where results go

- Postgres: calls, grades, corrections, snapshots.
- Replay output on disk: `data/runs/`, `data/runs_final/`, `data/mubit_batch*.json`, `data/loop.json`.
- The dashboard and web app read only these, never a live API.

---

*Research tool, not financial advice.*
