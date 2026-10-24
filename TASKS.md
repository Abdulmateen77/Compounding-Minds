# TASKS: Compounding Minds

Who builds what, in what order. Spec: [README.md](README.md). Pattern and flow: [ARCHITECTURE.md](ARCHITECTURE.md). Rules: [CLAUDE.md](CLAUDE.md).

**Person A: data and grading.** Owns `ingest/`, `store/`, `metrics/`, `tools/`, `grader/`, `dashboard/`, `screener/`.
**Person B: agents and Mubit.** Owns `agents/`, `principles/`, `eval/`, `memos/`.
**Shared:** `schemas/` (either may edit, tell the other), `.env.example`, repo root docs.

Code freeze: **Sun 25 Oct 10:00**. Rule: only edit your own directories unless asked. Small PRs, `main` always runs.

---

## 1. The contract between A and B

B must never be blocked on A. These land first.

| Deliverable | Owner | Due | Notes |
|---|---|---|---|
| `schemas/` Pydantic models: `AgentCall`, `Grade`, `Correction` | B writes, A reviews | Hour 2 | Shapes fixed in README section 6 |
| `store/stubs/`: 5 stub metric bundles per MVP agent | A | Hour 3 | Match `get_metrics` output exactly |
| `get_metrics_stub()` with env flag to flip to the real store | A | Hour 3 | `USE_STUB_STORE=1` |
| `grade(call) -> Grade` with a stub rule set | A | Hour 3 | Lets B test the loop on fake outcomes |
| `LLMGateway` and `ModelUpdater` interfaces, `FakeModelUpdater` | B | Hour 3 | Code against the interface, not Mubit's API |
| `.env.example` | A | Hour 1 | Keys listed, no values |

Interface (store gate): `get_facts`, `get_events`, `get_macro`, `get_metrics`, all with `as_of`. Do not change without telling the other person.

---

## 2. Person A: data and grading

### A1. Foundations (Hours 0-3)
- [ ] Repo hygiene: `.env.example`, Postgres via Docker or local, README run instructions
- [ ] `store/schema.sql` with all tables, `filed_date NOT NULL`, `vintage_date NOT NULL` for macro
- [ ] Freeze `ingest/universe.json` (about 50 companies, sector mix, some COVID losers and winners, about 10 held out). Assign `anon_001`...`anon_050`
- [ ] SEC fetcher with `User-Agent`, under about 10 requests per second, raw cache on disk
- [ ] Stub bundles and `grade()` stub (see section 1)

### A2. Data layer (Hours 3-10)
- [ ] Ingest `company_tickers.json`, XBRL `companyfacts`, `submissions` (8-K item codes), FRED + ALFRED vintages, prices
- [ ] Small fixed XBRL concept map with fallbacks. Drop companies that do not map cleanly
- [ ] `store/queries.py`: the only gate. Latest row per `(concept, period_end)` with `filed_date <= as_of`. Never order or filter by `period_end` for visibility
- [ ] `store/tests/test_leakage.py`: no row after `as_of`, known restatement invisible before its filing, macro returns the vintage valid at `t`
- [ ] Prices ingest (context only)

### A3. Metrics and tools (Hours 10-20)
- [ ] `metrics/` for MVP agents: Fundamentals, Risk, Scenarios. Each metric returns `{name, value, unit, as_of, inputs: [accession...]}`
- [ ] `get_metrics(company_id, agent, as_of)` on top of the three getters
- [ ] Traceability test: every `inputs` accession exists in `facts`
- [ ] `tools/` MCP servers: `get_metric_series`, `get_recent_events`, `get_macro_snapshot`, `peer_compare`
- [ ] Hour 10 checkpoint: real metrics for one company flow into one agent

### A4. Grader (Hours 10-20)
- [ ] `grader/config.py`: bucket thresholds (bear < 0%, base 0 to 10%, bull > 10%)
- [ ] `grader/rules.py`: one rule per `question_id` with a fixture each, including a restatement case
- [ ] `grader/grade.py`: Brier score (binary and multiclass), `unresolvable` handling
- [ ] `grader/corrections.py`: select corrections (cap N per agent per quarter, default 10, by confidence), assign `error_type`

### A5. Replay and dashboard (Hours 20-34)
- [ ] `grader/replay.py`: quarter loop 2018Q1 to 2024Q4, grade only calls whose resolution filing is visible, snapshot metrics. Deterministic, with a response cache keyed by prompt hash (coordinate with B)
- [ ] Full ingest QA, drop bad companies
- [ ] `dashboard/` v1: replay timeline, accuracy curves with COVID window shaded, committee table
- [ ] Correction spotlight: call, actual, lesson, Mubit ref, model version before and after
- [ ] Held-out panel (reads B's `eval/` output)
- [ ] Disclaimer footer always visible
- [ ] Hour 30 checkpoint: full replay running

### A6. Freeze (Hours 34-37)
- [ ] Record backup demo video of the full flow
- [ ] Freeze checks: tests pass, no secrets committed, demo runs from cache with no live API calls

### A stretch (in order)
`grader/calibration.py` track record, `screener/` watchlist flags, Moat and Valuation metric sets, legend scoreboard view.

---

## 3. Person B: agents and Mubit

### B1. Foundations (Hours 0-3)
- [x] `schemas/` Pydantic models (see section 1)
- [x] `LLMGateway`, `ModelUpdater` interfaces, `FakeModelUpdater` (appends lessons to principles or few-shot memory, labelled fallback)
- [ ] Mubit client setup (one base URL; gateway done, update-API answer still open). **Ask at office hours:** exact update endpoint and payload, update latency, per-agent isolation, rate limits, how version IDs are exposed. Do not guess endpoints
- [x] Draft `principles/` skeletons

### B2. First agent (Hours 3-10)
- [x] `agents/runner`: load principles, receive anon `company_id`, `as_of` and metrics, allow at most about 5 tool calls, return one `AgentCall`. One repair retry, then drop and log
- [x] Parse-time check that `evidence` values match metrics engine output
- [x] Prompts contain only anon ID and metrics. No names, tickers or dates beyond relative framing (Q-8 to Q0)
- [x] Fundamentals agent working on stubs
- [x] `agents/adapters/<agent>.py`: one per agent, each with its own Mubit identity
- [x] `principles/buffett.md` (5-10 rules in own words, `id | rule | how to check | source`, no long quotes)

### B3. MVP agents and synthesizer (Hours 10-20)
- [x] Risk (Munger) and Scenarios (Dalio) agents, plus `principles/munger.md` and `principles/dalio.md`
- [x] Synthesizer: weights from `grades` computed in Python, LLM only writes the rationale, calibrated confidence
- [x] Reflection prompt that produces the `lesson`. It must cite a principle or metric and never name a company
- [ ] Real `ModelUpdater` against Mubit, using whatever office hours confirmed
- [ ] Hour 20 checkpoint: full vertical slice (one company, one agent, one quarter, graded and corrected)

### B4. Correction loop and eval (Hours 20-30)
- [ ] Correction loop with real Mubit: lesson, `submit_corrections`, model version stamped into later `AgentCall.model`
- [x] Frozen twin of each agent (no learning)
- [x] `eval/` held-out harness: split by time (train 2018-2022, held-out 2023-2024) and by company (about 10 held out). Learning from train-window corrections only
- [x] Baselines: always-yes, base rate

### B5. Full run and report (Hours 30-37)
- [ ] Full replay run with real agents, results stored
- [ ] Held-out report: frozen vs learned vs baselines, generated once, no tuning against it
- [ ] Tune the demo script, README results section
- [ ] Rehearse the live correction-to-update moment

### B stretch (in order)
- [x] Valuation and Moat agents with `principles/graham.md` (Moat uses `principles/buffett_moat.md`)
- [x] Frontier-model comparison (`eval.run --frontier-model`)
- [x] Cross-examination round (`agents/cross_exam.py`)
- [x] `memos/` drafting with placeholder number check

### B extras built
- [x] Run store: calls, grades, corrections, snapshots and eval results to Postgres or JSONL (`agents/run_store.py`, `schemas/run_extras.sql`). Tell A: adds `grades.resolution_date`, `snapshots`, `eval_results`
- [x] Bounded tool use in the runner (`agents/tools.py`), ready for A's MCP tools

---

## 4. Integration checkpoints

| Hour | Checkpoint | Both must |
|---|---|---|
| 3 | Contract landed | Schemas, stubs, `grade()` stub, interfaces merged |
| 10 | Real metrics into one agent | A: metrics for one company via real store. B: Fundamentals consuming them |
| 20 | Vertical slice | One company, one agent, one quarter: call, grade, correction, update |
| 30 | Full replay | All MVP agents, all quarters, dashboard showing results |
| 34 | Demo-ready | Backup video recorded, held-out report in, freeze checks run |

---

## 5. Hand-offs and shared decisions

| Item | Who decides | By |
|---|---|---|
| Universe list | A (B reviews sector mix) | Hour 3 |
| Streamlit vs React | A (default Streamlit) | Hour 3 |
| Mubit update API shape | B (report back to A for the dashboard) | After office hours |
| Corrections per agent per quarter | Both, tune on train window | Hour 20 |
| LLM response cache format | A and B | Hour 20 |
| Whether Valuation joins MVP | Both, if Fundamentals, Risk and Scenarios finish early | Hour 20 |

---

## 6. Definition of done (MVP)

- [ ] Leakage test passes
- [ ] One grader fixture per MVP `question_id` passes
- [ ] Every stub and real call validates against `AgentCall`
- [ ] Metrics traceability test passes
- [ ] Smoke test passes: one company, one agent, two consecutive quarters, with a correction
- [ ] Dashboard runs from Postgres only, no live API calls
- [ ] Correction-to-Mubit update visible on screen (or labelled fallback)
- [ ] Held-out report generated once
- [ ] Backup demo video recorded
- [ ] No secrets in git

## 7. Cut list (if behind)

Drop in this order: frontier-model comparison, legend scoreboard, cross-examination, memos, screener, Moat, Valuation, calibration tracker.
**Never cut:** point-in-time store, reality grader, correction-to-Mubit loop, held-out eval, backup demo video.

---

*Research tool, not financial advice.*
