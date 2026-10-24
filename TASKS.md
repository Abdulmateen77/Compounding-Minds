# TASKS: Compounding Minds

Who builds what, in what order. Spec: [README.md](README.md). Pattern and flow: [ARCHITECTURE.md](ARCHITECTURE.md). Rules: [CLAUDE.md](CLAUDE.md). Pictures: [system-map.html](system-map.html), [user-journey.html](user-journey.html).

**Code freeze: Sun 25 Oct 10:00.** Rule: only edit your own files unless asked. Small PRs, `main` always runs, tests pass before merge.

---

## 0. The split in one table

| | **Person A: content, data and agents** | **Person B: ingestion, grading, orchestration and output** |
|---|---|---|
| **One line** | Decides what the agents know and say, structures the data they read, builds the agents | Pulls the data in, marks the agents against reality, runs the replay, shows the result |
| **Content** | Principles, prompts, lesson wording, dashboard and memo copy, demo script | n/a |
| **Data** | Source spec, concept map, universe, schema, point-in-time gate, metrics engine, MCP tools | Ingestion: fetchers, raw cache, parsing into tables |
| **Agents** | Runner, specs, adapters, Mubit client, all agents, frozen twins, baselines, held-out harness | n/a |
| **Grading** | n/a | Grader rules, corrections, calibration |
| **Orchestration** | n/a | Replay loop, response cache, correction loop, runs |
| **Synthesis** | n/a | Synthesizer and its weights |
| **Output** | n/a | Final report, memo, dashboard |
| **Directories** | `principles/`, `agents/` (except the files listed below), `store/`, `metrics/`, `tools/`, `eval/`, `screener/` | `ingest/`, `grader/`, `dashboard/`, `memos/`, plus the `agents/` files listed below |
| **Shared** | `schemas/`, `.env.example`, root docs, the backup video | |

**Files inside `agents/` that Person B owns** (they are orchestration, not agent logic): `synthesizer.py`, `correction_loop.py`, `cache.py`, `mubit_batch.py`, `offline.py`.

**The line between A and B on data.** A decides *what* the data is: which sources, which XBRL concepts, which table shapes, what the metrics mean. B does the *work of getting it in*: fetching, caching, and loading rows that match A's schema and concept map. A never writes a fetcher; B never defines a metric.

---

## 1. Where we are now (Sat 24 Oct, ~15:00)

Read from the repo. 74 tests pass. Nothing runs on real data yet: every agent runs on three hand-written stub files.

| Area | State | Owner |
|---|---|---|
| `agents/`: runner, specs for Fundamentals, Risk and Scenarios, masking, reflection, Mubit gateway | Built | A |
| `principles/`: all four investor files | Exist, need a content review | A |
| `schemas/`: call, grade, correction models | Built | Shared |
| `store/schema.sql`, `store/queries.py` (date gate, in-memory backend), leakage test, stub metrics | Built. Postgres backend is a TODO | A |
| `agents/synthesizer.py`, `correction_loop.py`, `cache.py`, `mubit_batch.py`, `offline.py` | Built | B |
| `grader/`: Brier scoring, `grade()`, Risk going-concern rule (via Sapling) | Built. Fundamentals and Scenarios rules are stubs | B |
| `video/`: Remotion showcase clip | Built | Shared |
| `ingest/` | Empty | B |
| `metrics/`, `tools/` | Empty | A |
| `eval/` | Empty | A |
| `dashboard/`, `memos/` | Empty | B |
| Replay orchestrator (`grader/replay.py`) | Not started | B |

---

## 2. The contract between A and B

Neither side should wait on the other. These handoffs have times. Anything late is raised in chat right away.

| # | From | To | Deliverable | Due |
|---|---|---|---|---|
| 1 | A | B | `ingest/universe.json` (about 50 companies, anon IDs, sector, about 10 held out) | Sat 17:00 |
| 2 | A | B | Final `store/schema.sql` and the XBRL concept map (concept, fallbacks, unit) | Sat 17:00 |
| 3 | B | A | Raw SEC data cached and parsed into Postgres for 5 companies | Sat 19:00 |
| 4 | A | B | Postgres backend in `store/queries.py`, leakage test passing on real rows | Sat 21:00 |
| 5 | A | B | `get_metrics(company, agent, as_of)` real for Fundamentals, Risk and Scenarios | Sat 22:00 |
| 6 | B | A | All 50 companies and macro loaded, ingest QA report | Sat 23:00 |
| 7 | A | B | `run_agent(company_id, as_of) -> AgentCall` (the runner entry point the replay calls) | Sat 20:00 |
| 8 | B | A | `grade(call) -> Grade` with real rules for all three MVP questions | Sat 23:00 |
| 9 | A | B | Held-out results as `eval/out/heldout.json` (frozen vs learned vs baselines) | Sun 05:00 |
| 10 | B | A | Quarterly snapshots in Postgres (for A's quality report) | Sun 03:00 |

Interfaces that do not change without telling the other person: `get_facts`, `get_events`, `get_macro`, `get_metrics`, and the three models in `schemas/`.

---

## 3. Person A: content, data and agents

### Phases (work through these in order)

| Phase | Goal | Due | Handoff | Status |
|---|---|---|---|---|
| **1. Contract** | Universe, concept map, final schema, metric spec, principles checked against the metrics | Sat 17:00 | 1, 2 | Done in code. Citations still to verify |
| **2. Real store** | Postgres backend for the date gate, loaders, parsers, leakage test on real rows, `run_agent` entry point | Sat 21:00 | 4, 7 | **Mostly done**: backend, loaders, parsers and a date-gate fix, tested on a real Postgres. Left: the leakage test on real filings (needs B's download, handoff 3) and `run_agent` |
| **3. Metrics and tools** | The 22 metrics computed from real facts, `get_metrics` real, MCP tools | Sat 22:00 | 5 | Spec written (`metrics/SPEC.md`), code not started |
| **4. Agents on real data** | Run the 3 MVP agents on real metrics, tune prompts, measure JSON validity and evidence match | Sun 01:00 | | Not started |
| **5. Evaluation** | Frozen twins, baselines, held-out run, quality report with critique | Sun 05:00 | 9 | Not started |
| **6. Content and freeze** | Copy, demo script, README results, backup video | Sun 08:00 | | Not started |

**Unblocked for Person B now.** Everything after the network call is built and tested: `docker compose up -d`, `python -m store.migrate`, then follow [ingest/README.md](ingest/README.md). B's only job to get real data flowing is to download the raw SEC and FRED files into the cache; `ingest/pipeline.py` parses and loads them, and `store.quality.coverage` reports which companies are missing what.

**Phase 2 delivered**
- `store/pg.py`: Postgres backend for the date gate. It only supplies candidate rows, so the visibility rule stays in `store/queries.py` and cannot differ from the tested in-memory one.
- `store/db.py`, `store/migrate.py`: connection, schema apply, idempotent bulk loaders (re-running inserts nothing).
- `ingest/parse_facts.py`, `parse_submissions.py`, `parse_fred.py`: raw SEC and FRED JSON to rows. Pure functions, tested on fixtures shaped like the real responses.
- `ingest/pipeline.py`: loads a cache directory into Postgres, offline. `store/quality.py`: per-company coverage and drop candidates.
- **Bug fixed in the date gate:** it kept one fact per `(concept, period_end)`, but a Q2 10-Q reports a 3-month and a 6-month figure ending the same day, so one was silently dropped. It now keys on `(concept, period_start, period_end)`, with a regression test.
- **Design fix in the concept map:** a restatement filed under a different tag (the 2018 revenue-recognition change) is now kept, so the gate can show the old value before the restatement and the new one after.
- `docker-compose.yml`, `.env.example`, and a `pg_conn` test fixture that skips cleanly when no database is reachable.

Phase 1 can be worked now with no dependency on B. Phase 2 starts as soon as handoff 3 (5 companies in Postgres) lands: until then, build the Postgres backend against the in-memory gate tests so it is ready to run.

**Phase 1 delivered**
- `ingest/universe.json`: 50 companies, anon IDs from a seeded shuffle, 10 held out, COVID groups. Built by `ingest/build_universe.py`, validated by `ingest/universe.py`, tested.
- `store/concepts.py`: the XBRL concept map (22 concepts, tag fallbacks, which are cumulative in a 10-Q), macro series, and the inputs each of the 22 metrics needs. `resolve_concept` merges tags per period and keeps restated rows.
- `store/schema.sql`: idempotent-load keys, `held_out` and `covid_group` on companies, going-concern count on events, macro vintage index, a `snapshots` table for the dashboard. Parsed with a real Postgres parser in a test.
- `metrics/SPEC.md`: the formula for every metric, how quarters are derived from filings, and what happens when data is missing.
- `principles/`: Graham expanded to 6 rules; `buffett.05` no longer cites a metric the Fundamentals agent is never shown; `principles/SOURCES.md` lists every citation still to verify; `agents/tests/test_principles_contract.py` keeps rules and metrics in sync.

### A1. Content production
- [~] Review the four `principles/*.md` files. Format, count and metric names are now tested. **Still to do: check each citation against the source (see `principles/SOURCES.md`)**
- [ ] Final question wording for each agent (the six `question_id`s in README 7.1)
- [ ] Prompt templates per agent: anonymous ID, relative quarters (Q-8 to Q0), no names or dates
- [ ] Reflection (lesson) prompt tuned on real misses: cites a principle or a metric, never a company name (starting point exists in `agents/reflection.py`)
- [ ] Copy: dashboard labels, empty and error states, the disclaimer, memo section templates
- [ ] Demo script (3 to 4 minutes) and talking points
- [ ] README results section, written after the held-out run

### A2. Data sources pipeline and structuring
- [x] Source spec: which XBRL concepts feed each metric, with fallbacks. Drop rule for companies that do not map cleanly is in `metrics/SPEC.md` (3 or more missing metrics)
- [x] `ingest/universe.json`: 50 US companies, COVID losers and winners, 10 held out, `anon_001` to `anon_050` **(handoff 1)**. Sector is hand-assigned; SIC comes from B's ingest
- [x] Concept map `store/concepts.py` **(handoff 2)**
- [x] Final `store/schema.sql`: keys, indexes, `filed_date NOT NULL`, `vintage_date NOT NULL` for macro, `snapshots` table **(handoff 2)**
- [x] `metrics/SPEC.md`: formulas for all 22 metrics and the quarter-derivation rules
- [x] Date gate in `store/queries.py` with an in-memory backend, and `store/tests/test_leakage.py`
- [ ] **Postgres backend** for the gate. Latest row per (concept, period_end) with `filed_date <= as_of`. Leakage test on real rows **(handoff 4)**
- [ ] `metrics/` engine for Fundamentals, Risk and Scenarios. Each metric returns name, value, unit, as_of and the filing accessions **(handoff 5)**
- [ ] Traceability test: every accession a metric cites exists in `facts`
- [ ] `get_metrics` real, then flip `USE_STUBS=0`
- [ ] `tools/` MCP servers: `get_metric_series`, `get_recent_events`, `get_macro_snapshot`, `peer_compare`
- [ ] Data quality report per company (coverage, gaps), agreed with B's ingest QA

### A3. Agents
- [x] Runner, specs for Fundamentals, Risk and Scenarios, date masking, Mubit gateway
- [ ] `run_agent(company_id, as_of) -> AgentCall` as the stable entry point **(handoff 7)**
- [ ] Run each agent on real metrics for one company, then widen. Check: JSON valid rate, evidence matches the metrics engine, tool calls capped at about 5 **(Sat 20:00)**
- [ ] Mubit: per-agent identity, and the office-hours answers on the update API (endpoint, latency, version IDs). The gateway already notes that no public corrections endpoint is known
- [ ] Confirm the model version is stamped into every `AgentCall`

### A4. Agent evaluation (`eval/`)
- [ ] Frozen twin of each agent (never updated)
- [ ] Baselines: always yes, base rate
- [ ] Held-out harness: split by time (train 2018 to 2022, held out 2023 to 2024) and by company (about 10). Learning from train-window corrections only
- [ ] Run once, before freeze, no tuning against it. Write `eval/out/heldout.json` **(handoff 9)**
- [ ] Quality report per agent: valid-JSON rate, evidence match, accuracy, Brier, calibration, overconfidence gap, and a short written critique of where each agent is weak

### A stretch (in order)
Moat and Valuation metric sets and agents, cross-examination round, `screener/`, frontier-model comparison.

---

## 4. Person B: ingestion, grading, orchestration and output

### B1. Ingestion (`ingest/`)
- [ ] SEC fetcher: User-Agent with name and email, under about 10 requests a second, every raw response cached to disk before parsing
- [ ] Pull `companyfacts`, `submissions` and filing text for the universe
- [ ] FRED and ALFRED macro with vintage dates. Prices from Stooq (context only)
- [ ] Parse into A's schema using A's concept map. `filed_date` on every row. A restatement is a new row, never an overwrite
- [ ] Event extractor: 8-K item codes, going-concern passages for the risk rule
- [ ] 5 companies loaded **(handoff 3, Sat 19:00)**, then all 50 **(handoff 6, Sat 23:00)**
- [ ] Ingest QA report. The whole load must re-run from the raw cache with no network
- [ ] Stretch: 8-K Exhibit 99.1 and FOMC pages through Firecrawl (dated pages only, no numbers); Live today fetch

### B2. Grading (`grader/`)
- [x] Brier scoring (binary and multiclass), `grade()`, Risk going-concern check through Sapling with a cache
- [ ] Risk: auditor change (8-K item 4.01) and dividend-cut (25% or more) checks
- [ ] Fundamentals rule: FCF margin and operating margin both up in the next reported quarter
- [ ] Scenarios rule: bucket from actual revenue growth. Thresholds in `grader/config.py`, tuned on the train window only
- [ ] One fixture per `question_id`, including a restatement case. `unresolvable` is excluded and logged **(handoff 8, Sat 23:00)**
- [ ] `grader/corrections.py`: pick the misses (cap N per agent per quarter, default 10, highest confidence first) and assign `error_type`
- [ ] Align the docs with the Sapling exception: [ARCHITECTURE.md](ARCHITECTURE.md), [PROJECT.md](PROJECT.md) and the diagrams still say "no LLM"
- [ ] Stretch: `grader/calibration.py` track record

### B3. Orchestration
- [x] Correction loop CLI and an offline demo that runs without Mubit
- [ ] `grader/replay.py`: quarter loop 2018Q1 to 2024Q4. Set `as_of`, call A's `run_agent` for every company and agent, store calls, grade only calls whose filing is now visible, make corrections, call `ModelUpdater`, snapshot
- [ ] `runs` table with train and held-out kinds. Learning from train-window corrections only
- [ ] Deterministic replay: temperature 0, response cache keyed by prompt hash **and model version** (a Mubit update changes the model, so old cache entries stop matching)
- [ ] Full replay run offline before the demo, results stored
- [ ] Rough cost and time estimate for the full run, done before starting it

### B4. Synthesis
- [x] Synthesizer exists
- [ ] Weights from each agent's trailing accuracy, computed in Python from `grades`. The LLM only writes the rationale
- [ ] Calibrated confidence for the committee verdict, graded as a composite of the underlying outcomes
- [ ] Tests for the weighting

### B5. Final output
- [ ] Final report per company and quarter: verdict, each agent's reasoning, a metric table rendered by Python with source accessions
- [ ] Name reveal at render time, only for the demo company
- [ ] Stretch: memo (`memos/`). The LLM writes prose around `{{metric:name}}` placeholders that Python fills. A number not from the metrics engine is rejected

### B6. Dashboard (`dashboard/`, Streamlit, reads Postgres only)
- [ ] Controls: company list (anonymous IDs with sector, plus a search box), quarter slider, Play, Step, speed, Learned vs Frozen toggle
- [ ] Committee table with evidence drawer
- [ ] Right or wrong results after Step
- [ ] Correction spotlight: call, reality, lesson, Mubit update, model version before and after. Labelled "fallback" if the fake updater was used
- [ ] Accuracy curves, learned vs frozen, COVID window shaded
- [ ] Run live loop button for one company and quarter
- [ ] Held-out panel reading A's `eval/out/heldout.json`
- [ ] Disclaimer footer on every view
- [ ] Stretch: Live today tab, watchlist, memo view, track record. See [user-journey.html](user-journey.html)

---

## 5. Timeline

| When | Person A | Person B |
|---|---|---|
| Sat 15:00 to 17:00 | Universe, concept map, final schema, principles review | Fetcher skeleton, raw cache, start pulling SEC data |
| Sat 17:00 to 21:00 | Postgres backend, leakage test on real rows, `run_agent` entry point | 5 companies parsed into Postgres, events, FRED and prices |
| Sat 21:00 to Sun 01:00 | Metrics for the three MVP agents, `get_metrics` real, agents on real data | Grader rules for all three questions, `corrections.py`, load all 50 companies |
| Sun 01:00 to 05:00 | Frozen twins, baselines, held-out harness, tool servers | Replay orchestrator, full replay run, synthesizer weights, dashboard v1 |
| Sun 05:00 to 08:00 | Held-out run, quality report and critique, copy and demo script | Dashboard polish, correction spotlight, final report |
| Sun 08:00 to 10:00 | Record the backup video together, freeze checks, README results | |

---

## 6. Checkpoints

| When | Checkpoint | Pass condition |
|---|---|---|
| Sat 17:00 | Contract landed | Universe, schema and concept map merged |
| Sat 21:00 | Real data, one company | Metrics for one company, from real rows, reach one agent |
| Sun 01:00 | Vertical slice | One company, one agent, one quarter: call, grade, correction, update |
| Sun 05:00 | Full replay | All three MVP agents, all quarters, the dashboard showing results |
| Sun 08:00 | Demo-ready | Held-out report in, backup video recorded |
| Sun 09:00 | Freeze checks | Tests pass, no secrets in git, the demo runs from cache with no live API calls |

---

## 7. Decisions still open

| Item | Who decides | By |
|---|---|---|
| Mubit update API shape, and what to do if there is no corrections endpoint | A, then tell B for the dashboard | After office hours |
| Whether Valuation joins the MVP | Both | Sun 01:00 |
| Corrections per agent per quarter | Both, tune on the train window | Sun 01:00 |
| Streamlit or React | B (default Streamlit) | Sat 17:00 |
| Sapling in the grader: keep, or replace with a rule | B, tell A | Sat 21:00 |
| Whether to build the Live today tab | Both | Sun 05:00 |

---

## 8. Definition of done (MVP)

- [ ] Leakage test passes on real rows
- [ ] One grader fixture per MVP `question_id` passes
- [ ] Every stub and real call validates against `AgentCall`
- [ ] Metrics traceability test passes
- [ ] Smoke test passes: one company, one agent, two consecutive quarters, with a correction
- [ ] Dashboard runs from Postgres only, no live API calls
- [ ] Correction to Mubit update visible on screen (or labelled fallback)
- [ ] Held-out report generated once
- [ ] Backup demo video recorded
- [ ] No secrets in git

## 9. Cut list (if behind)

Drop in this order: frontier-model comparison, legend scoreboard, cross-examination, memos, screener, Live today, Moat, Valuation, calibration tracker.
**Never cut:** point-in-time store, reality grader, correction-to-Mubit loop, held-out eval, backup demo video.

---

*Research tool, not financial advice.*
