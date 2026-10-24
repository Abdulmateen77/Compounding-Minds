# CLAUDE.md: Compounding Minds

Project context for Claude Code. Read this first, then `README.md` (full spec), `ARCHITECTURE.md` (agent pattern: parallel fan-out/fan-in committee, shared Postgres state, external-verifier reflection loop) and `TASKS.md` (team split).

## What this is

A multi-agent investment research system built for **Night Shift: Mubit Hackathon** (London, 23-25 Oct 2026, code freeze **Sun 25 Oct 10:00**). Each agent follows a legendary investor's principles (Buffett, Graham, Munger, Dalio), makes a **checkable call** about a company, and is **graded by what actually happened** in later SEC filings. Wrong calls become corrections; **Mubit** turns corrections into per-agent model updates. The demo replays 2018-2024 quarter by quarter and shows accuracy climbing, a COVID crash, then recovery.

One sentence: a team of AI analysts that grades itself against reality and improves every time it's wrong.

## Hackathon rules that constrain the code

- **All project code must be written during the event.** Do not paste in pre-existing code. Open-source libraries are fine.
- **Every LLM call must route through Mubit** (one base URL change). One adapter per agent.
- Judging: use of Mubit (a correction visibly becoming a model update), usefulness, technical execution, live demo under the time limit.
- Check Mubit's exact update API at office hours. Do not guess its endpoints; ask or read the docs the team has.

## Team of two

- **Person A: content, data and agents.** Owns `principles/`, `agents/` (except the files below), `store/`, `metrics/`, `tools/`, `eval/`, `screener/`. Decides what the data is (sources, concept map, schema, metrics) and builds the agents.
- **Person B: ingestion, grading, orchestration and output.** Owns `ingest/`, `grader/`, `dashboard/`, `memos/`, plus `agents/synthesizer.py`, `agents/correction_loop.py`, `agents/cache.py`, `agents/mubit_batch.py`, `agents/offline.py`. Fetches the data in, grades the calls, runs the replay, shows the result.
- Shared: `schemas/`, `.env.example`, root docs. Full split and handoff times are in `TASKS.md`.
- Only edit your owner's files unless asked. Small PRs, `main` always runs.
- Until the real store is ready, everyone builds against **stub JSON** matching the schemas (`USE_STUBS=1`).

## Non-negotiable rules

1. **No number comes from an LLM.** Python computes every metric. Agents only judge.
2. **Point-in-time only.** Every stored value carries its `filed_date`. At as-of date `t`, only rows with `filed_date <= t` are visible. This is enforced in **one place** (`store/queries.py`) with a leakage test. Never filter by `period_end`.
3. **No price predictions.** Every call is about business outcomes reported in filings.
4. **Fixed output schemas.** Agents may use tools freely (cap ~5 calls) but must answer in the same JSON shape every time, or grading and Mubit updates break.
5. **No live API calls in the demo.** Everything comes from the Postgres cache.
6. **Anonymize companies** (`anon_001`...) to reduce memorization. Names and tickers stay out of agent prompts.
7. **Never commit secrets.** API keys live in `.env` (gitignored). Provide `.env.example`.
8. **Research tool, not financial advice.** Keep "you should buy X" out of any output.

## Agents and calls

| Agent | Investor | Call | Graded by |
|---|---|---|---|
| Fundamentals | Buffett | FCF and margins improve next quarter? | Next 10-Q |
| Valuation | Graham | Implied growth (reverse DCF) above or below delivered? | Actual growth next year |
| Moat | Buffett | Gross margin holds within ±2pts over 4 quarters? | Next 4 filings |
| Risk | Munger | Auditor change, dividend cut or going-concern note in 12 months? | 8-K, XBRL, 10-K text |
| Scenarios | Dalio | Bull/base/bear revenue bucket | Where reality landed |
| Synthesizer | Committee | Verdict with confidence | Brier score |

Supporting: **replay orchestrator** (advances one quarter, enforces as-of date) and **reality grader** (scores calls, emits corrections).

**MVP:** Fundamentals, Risk, Scenarios + synthesizer + grader + Mubit correction loop + replay dashboard, ~50 US companies.
**Stretch:** Valuation, Moat, cross-examination round, legend scoreboard, frontier-model comparison, Firecrawl press releases, and the analyst workflow layer (README 11b): watchlist screener (`screener/`, A), memo drafting (`memos/`, B), calibration track record (`grader/calibration.py`, A). Memos may not contain any number the metrics engine did not produce. Screener flags are "needs attention", never buy/sell.
**Never cut:** point-in-time store, reality grader, correction-to-Mubit loop, held-out eval, backup demo video.

## Data sources (free, cached to Postgres)

SEC `company_tickers.json`, XBRL `companyfacts` and `frames`, `submissions` (8-K item codes), EDGAR full-text search, FRED + ALFRED vintages, Tiingo or Stooq prices. Libraries: `edgartools`, `fredapi`, `pandas`.
SEC requests need a `User-Agent` with a name and email; stay under ~10 requests/second.

## Store interface (the contract between A and B)

```
get_facts(company_id, concept, as_of) -> list[Fact]      # filed_date <= as_of enforced inside
get_events(company_id, as_of, forms=None) -> list[Event]
get_macro(series_id, as_of) -> list[Point]
get_metrics(company_id, agent, as_of) -> dict
```

Schemas for the agent call and the correction are in `README.md` section 6. Do not change them without telling the other person.

## Investor principles

Do **not** ingest full books. `principles/<investor>.md` holds 5-10 checkable rules per investor, **in our own words**, each with a source citation (e.g. Berkshire letters, *The Intelligent Investor* ch. 20). No long quotes.

## Stack

Python, FastAPI, PostgreSQL, MCP servers over the metrics engine, Streamlit or React dashboard, LLM calls via Mubit.

## Working style

- Prefer simple, working code over clever code. We have ~37 hours.
- Ship vertical slices: one company, one agent, one quarter, end to end, then widen.
- Add a short test for anything touching point-in-time logic or grading.
- When unsure about scope, check the cut list in `TASKS.md` and ask.
