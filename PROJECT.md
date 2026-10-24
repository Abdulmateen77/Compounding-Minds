# Compounding Minds: Project Definition

Overview document: what it is, who it is for, and how it is built. Agent pattern and data flow: [ARCHITECTURE.md](ARCHITECTURE.md). Detailed contracts and schemas live in [README.md](README.md). Rules for Claude Code live in [CLAUDE.md](CLAUDE.md).

---

## 1. What it is

A team of AI analysts that grades itself against reality and improves every time it is wrong.

Each agent follows one legendary investor's principles (Buffett, Graham, Munger, Dalio). At a past date `t` it sees only what was public on `t`, then makes a **checkable call** about a company's business outcomes. We grade the call against what later SEC filings reported. Wrong calls become **corrections**, and **Mubit** turns corrections into per-agent model updates.

It is a research-support and QA loop for analysts. It is not an autonomous fund, a trading system or a source of financial advice.

### Principles that define it
1. **Falsifiable.** Every call has a question that filings can answer. No price predictions.
2. **Point-in-time honest.** Data is filtered by `filed_date <= as_of` in one place, with a leakage test.
3. **No LLM-generated numbers.** Python computes every metric. Agents only judge.
4. **Self-correcting.** Graded misses become lessons, and lessons become model updates.
5. **Traceable.** Every number links back to a filing accession.

---

## 2. What it does

1. **Ingests** SEC, macro and price data into a local Postgres cache, with filing dates on every row.
2. **Computes** metrics (FCF, margins, leverage, coverage, growth distributions) in Python, each traceable to filings.
3. **Asks agents** to make fixed-format calls from the metrics and their investor's principles.
4. **Synthesizes** the calls into a committee verdict with calibrated confidence.
5. **Grades** each call against later filings (pure Python, no LLM).
6. **Generates corrections** for wrong calls, with a lesson written by a reflection LLM call.
7. **Updates** each agent through Mubit.
8. **Replays** 2018 to 2024 quarter by quarter, showing accuracy climbing, the 2020 crash, and recovery.
9. **Evaluates** on held-out years and companies, against frozen and baseline agents.

### Stretch: analyst workflow layer
- **Watchlist screener:** ranks companies by deterioration flags, framed as "needs analyst attention".
- **Analyst memos:** first-pass memos where every figure is filled in by Python from metric placeholders.
- **Calibration tracker:** per-agent and per-principle track record, feeding synthesizer weights.

### Roadmap (post-hackathon)
- Holdings-aware mode: input a portfolio, get flags and memos per position.
- Role-based outputs: analyst (full evidence), PM or CIO (summary and flags), adviser (plain language).
- Analyst-submitted theses graded by the same grader.
- Analyst overrides stored as corrections, so the system learns the firm's judgment.
- Event-triggered refresh and alerts when a 10-Q, 10-K or 8-K lands.
- Sector metric packs for financials, insurers, REITs.

---

## 3. Who can find it useful

| Firm type | Fit | What they would use |
|---|---|---|
| **Asset managers** (long-only, mutual funds) | Strong | Screener, memos, calibration by analyst and framework, audit trail |
| **Wealth managers / private bank CIO offices** | Strong | Holdings monitor, deterioration flags, plain-language memos |
| **Pensions, endowments, insurers** | Good | Equity and credit monitoring, explainability, audit export |
| **Investment banks: credit and risk** | Good | Counterparty early warning with filing evidence |
| **Investment banks: equity research** | Moderate | Draft first-pass notes, published track record (compliance permitting) |
| **Family offices** | Good | Small-team coverage, auditable process |
| **Fundamental / distressed funds** | Moderate | Deterioration monitor (value is process, not alpha or speed) |
| **Quant funds, robo-advisers** | Weak | Not designed for signals or quantitative models |

**Lead segment:** asset managers and wealth-management CIO offices. They have volume and governance pressure, public filings are enough to start, and the no-advice stance suits compliance.

### Honest limits
- Quarterly filings are public to everyone, so this helps coverage and discipline, not speed.
- Accuracy describes business-outcome calls, not investment returns.
- US-listed companies only to start. Funds, bonds and non-US names need new sources.
- It sits beside licensed research and risk systems. It does not replace them.

---

## 4. Use cases

| # | Use case | Who | Flow |
|---|---|---|---|
| 1 | **Coverage triage** | Asset manager analyst | Screener ranks the watchlist, analyst opens flagged names first |
| 2 | **First-pass memo** | Analyst, PM | Generate a memo with metric table and sources, then edit |
| 3 | **Holdings monitor** | Wealth CIO office | Portfolio in, deterioration flags out, adviser gets plain-language note |
| 4 | **Early-warning on distress** | Credit, risk, pensions | Risk agent flags auditor change, dividend cut or going-concern text |
| 5 | **Process QA** | PM, allocator, compliance | Calibration curves per agent and per principle, audit trail of calls |
| 6 | **Committee support** | Investment committee | Synthesizer verdict plus each agent's reasoning and disagreement |
| 7 | **Lessons learned** | Research head | Corrections show systematic errors (overconfidence, missed regimes) |
| 8 | **Hackathon demo** | Judges | Call, reality, correction, Mubit update, better call |

---

## 5. Technical overview

### 5.1 Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.11 |
| API / services | FastAPI |
| Database | PostgreSQL |
| Data libraries | `edgartools`, `fredapi`, `pandas` |
| Agent tools | MCP Python SDK (MCP servers over the metrics engine) |
| Schemas | Pydantic (shared `schemas/` package) |
| LLM access | Single `LLMGateway`, base URL set to **Mubit** |
| Model updates | `ModelUpdater` interface, Mubit implementation plus `FakeModelUpdater` fallback |
| Dashboard | Streamlit (default) or React |
| Testing | pytest |

### 5.2 Architecture

```
            SEC EDGAR / FRED / prices
                      |
                 [ingest/]  --one-off, cached-->  [store/ Postgres]
                                                      |
                                       store/queries.py  (only gate: filed_date <= as_of)
                                                      |
                 +------------------------------------+-----------------+
                 |                                                      |
          [metrics/] Python computes ALL numbers                  [tools/] MCP servers
                 |                                                      |
                 +---------------------> [agents/] <--------------------+
                                  (judge only, fixed JSON out)
                                          |  every LLM call via Mubit
                                          v
                              [Synthesizer: committee verdict]
                                          |
   [replay orchestrator] --advances quarter, sets as_of--> calls stored in DB
                                          |
                                   [grader/] reads later filings
                                          |
                                    Correction records
                                          |
                                 Mubit update (per agent)
                                          |
                                 [dashboard/] replay UI
```

Stretch modules plug into the same stores: `screener/` reads metrics and calls, `memos/` reads metrics, calls and events, `grader/calibration.py` reads grades.

### 5.3 Data sources

| Source | Used for |
|---|---|
| SEC `company_tickers.json` | Universe, CIK mapping |
| XBRL `companyfacts` / `frames` | Financial facts with filing dates |
| SEC `submissions` | Filing list, 8-K item codes (e.g. 4.01 auditor change) |
| EDGAR full-text search | Going-concern and risk text |
| FRED + ALFRED | Macro series with vintages (what was known then) |
| Tiingo or Stooq | Prices, context only, never a prediction target |
| 8-K Exhibit 99.1 (stretch) | Dated earnings and deal press releases |
| FOMC statements, Wayback IR snapshots (stretch) | Macro tone, historical company pages |
| Firecrawl (stretch, plus dev-time use) | Crawl non-SEC pages into `events`; scrape investor letters and Mubit docs while building |

R&D comes from XBRL `ResearchAndDevelopmentExpense` and the 10-K R&D section. Patents, clinical trials and FDA data are post-MVP. The full source list, per-agent data mapping and Firecrawl rules (no numeric extraction, scrub company names, trusted dates only) are in README sections 4.1b to 4.1d.

Rules: SEC `User-Agent` with name and email, under about 10 requests per second, raw responses cached to disk before parsing. No live API calls in the demo.

### 5.4 Data model (Postgres)

`companies`, `facts`, `events`, `macro`, `prices`, `calls`, `grades`, `corrections`, `runs`. Every fact and event has `filed_date NOT NULL`. Macro has `vintage_date NOT NULL`. A restatement is a new row, never an overwrite. Full table definitions are in README section 4.3.

### 5.5 Modules and owners

| Directory | Contents | Owner |
|---|---|---|
| `ingest/` | SEC, FRED, price fetchers, `universe.json`, raw cache | A |
| `store/` | `schema.sql`, `queries.py` (point-in-time gate), stubs, tests | A |
| `metrics/` | One module per agent's metric set | A |
| `tools/` | MCP servers | A |
| `grader/` | `rules.py`, `grade.py`, `corrections.py`, `replay.py`, `calibration.py` | A |
| `dashboard/` | Streamlit app | A |
| `agents/` | Runner, adapters, one module per agent, synthesizer | B |
| `principles/` | `buffett.md`, `graham.md`, `munger.md`, `dalio.md` | B |
| `eval/` | Held-out split, baselines, report generation | B |
| `memos/` (stretch) | Memo assembly, placeholder renderer, number check | B |
| `screener/` (stretch) | Watchlist flags and ranking | A |
| `schemas/` | Shared Pydantic models | Shared |

---

## 6. Functionality

### 6.1 Agents and calls

| Agent | Investor | Question ID | Type | Graded by |
|---|---|---|---|---|
| Fundamentals | Buffett | `fcf_margin_improves_next_q` | binary | Next 10-Q or 10-K |
| Risk | Munger | `distress_event_12m` | binary | 8-K items, XBRL dividends, 10-K text |
| Scenarios | Dalio | `revenue_bucket_next_4q` | bucket (bear < 0%, base 0 to 10%, bull > 10%) | Actual revenue growth |
| Synthesizer | Committee | `committee_verdict` | bucket | Composite of graded outcomes |
| Valuation (stretch) | Graham | `implied_growth_above_delivered` | binary | Revenue growth over next year |
| Moat (stretch) | Buffett | `gross_margin_holds_2pts` | binary | Next 4 filings |

### 6.2 Agent runner
1. Load `principles/<investor>.md`.
2. Receive anonymized `company_id`, `as_of` and pre-computed metrics.
3. May call MCP tools (capped at about 5 calls).
4. Return one `AgentCall` in the fixed schema. Invalid JSON gets one repair retry, then the call is dropped and logged.

Prompts contain no names, tickers or calendar dates beyond relative framing (Q-8 to Q0).

### 6.3 Metrics engine
Python computes all numbers. Each metric returns `{name, value, unit, as_of, inputs: [accession...]}`.

| Agent | Example metrics |
|---|---|
| Fundamentals | FCF (TTM), FCF margin, operating margin, ROIC, debt/EBITDA, 8-quarter slope |
| Risk | Interest coverage, current ratio, cash runway, dividend history, auditor-change history, going-concern hits |
| Scenarios | 5-year revenue growth distribution, cyclicality, macro regime (GDP, unemployment, yield curve, credit spread) |
| Valuation | Reverse-DCF implied growth, owner earnings yield, growth CAGR |
| Moat | Gross margin level and std-dev, R&D and SG&A intensity |

### 6.4 Reality grader
Pure Python, no LLM. Resolves each `question_id` using rules in `grader/rules.py` against filings with `filed_date` after `as_of`. Computes Brier score (binary and multiclass). Logs `unresolvable` cases and excludes them from accuracy.

### 6.5 Correction loop
For each wrong call, emit a `Correction` with error type (`overconfident`, `missed_regime`, `wrong_signal`, `ignored_metric`) and a lesson from a reflection LLM call through Mubit. Cap at N corrections per agent per quarter (default 10), prioritised by confidence of the wrong call. `ModelUpdater.submit_corrections` sends them to Mubit, and the new model version is stamped into later calls.

### 6.6 Replay orchestrator
For each quarter end from 2018Q1 to 2024Q4: run every agent for every company, store calls, grade calls that have resolved by that date, make corrections, apply Mubit updates, snapshot metrics. A call is graded only once its resolution filing is visible at the current `as_of`. Replay is deterministic (temperature 0, cached responses keyed by prompt hash) and precomputed before the demo.

### 6.7 Held-out evaluation
Split by time and by company. Train 2018 to 2022, held-out 2023 to 2024, about 10 companies held out for all years. Mubit updates learn only from train-window corrections. Report frozen vs learned vs baselines (always-yes, base rate). Generated once, with no tuning against it.

### 6.8 Dashboard
Replay timeline, accuracy curves (learned vs frozen twin, COVID window shaded), committee table, correction spotlight (call, actual, lesson, Mubit update, model version before and after), held-out panel. Stretch views: watchlist screen, memo view, track record, legend scoreboard. Always shows "Research tool, not financial advice."

---

## 7. Specs

### 7.1 Interfaces

```python
# store/queries.py: the only data gate
get_facts(company_id, concept, as_of) -> list[Fact]
get_events(company_id, as_of, forms=None) -> list[Event]
get_macro(series_id, as_of) -> list[Point]
get_metrics(company_id, agent, as_of) -> dict

# Mubit boundary
class LLMGateway:
    def complete(self, agent, messages, **kw) -> str: ...

class ModelUpdater:
    def submit_corrections(self, agent, corrections) -> UpdateRef: ...
    def get_model_version(self, agent) -> str: ...
    def status(self, ref) -> UpdateStatus: ...
```

Mubit's real update API is not yet known. Code against these interfaces, ask at office hours and do not guess endpoints. `FakeModelUpdater` (appends lessons to the agent's principle file or few-shot memory) is the labelled fallback.

### 7.2 Schemas
`AgentCall`, `Grade` and `Correction` are fixed Pydantic models in `schemas/`. Full JSON shapes are in README section 6. `evidence` values must match what the metrics engine returned, checked at parse time.

### 7.3 Non-functional requirements

| Area | Requirement |
|---|---|
| Leakage | No returned row has `filed_date > as_of`. Enforced in `store/queries.py` and tested. |
| Reproducibility | Temperature 0, fixed seeds, cached LLM responses |
| Demo | Runs from the Postgres cache, no live API calls, within the time limit |
| Scale | About 50 companies, 2018 to 2024, quarterly |
| Traceability | Every metric lists the accessions it was computed from |
| Security | No secrets committed. `.env` gitignored, `.env.example` provided |
| Compliance posture | Research tool, no buy/sell language, no price targets |
| Anonymity | `anon_001` to `anon_050`. Names and tickers never leave the store. |

### 7.4 Minimum tests
1. Leakage test for `store/queries.py` (including a restatement and macro vintages).
2. Grader rule tests, one fixture per `question_id`.
3. Schema validation for every stub and real call.
4. Metrics traceability (each `inputs` accession exists in `facts`).
5. Smoke test: one company, one agent, two consecutive quarters, with a correction.

### 7.5 Success criteria
- Correction to Mubit update is visible on screen in the demo.
- Learned agents beat their frozen twins on held-out data, or the result is reported honestly with calibration gains.
- No leakage test failures.
- Backup demo video recorded before code freeze (Sun 25 Oct 10:00).

### 7.6 Scope

**MVP:** Fundamentals, Risk, Scenarios, synthesizer, grader, Mubit correction loop, replay dashboard, about 50 companies.
**Stretch, in order:** Valuation, Moat, calibration tracker, frontier-model comparison, screener, memos, cross-examination round, legend scoreboard, Firecrawl press releases.
**Never cut:** point-in-time store, reality grader, correction-to-Mubit loop, held-out eval, backup demo video.

---

*Research tool, not financial advice.*
