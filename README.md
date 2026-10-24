# Compounding Minds: Full Spec

A team of AI analysts that grades itself against reality and compounds from every mistake.

Built for **Night Shift: Mubit Hackathon** (London, 23-25 Oct 2026). Code freeze **Sun 25 Oct 10:00**.
Companion files: [PROJECT.md](PROJECT.md) (overview), [ARCHITECTURE.md](ARCHITECTURE.md) (agent pattern and flow), [CLAUDE.md](CLAUDE.md) (rules for Claude Code), `TASKS.md` (who builds what).

---

## 1. Concept

Each agent follows one legendary investor's principles (Buffett, Graham, Munger, Dalio). At a past date `t`, it sees only what was public on `t`, then makes a **checkable call** about a company's business outcomes. We grade the call against what later SEC filings actually reported. Wrong calls become **corrections**. **Mubit** turns corrections into per-agent model updates, so the next round is better.

The demo's **Time Machine** replay runs 2018-2024 quarter by quarter. The audience watches accuracy climb, the COVID crash (2020) break the agents, then recovery as corrections accumulate.

**Why it's different:** most "AI analyst" demos make claims nobody checks. Ours is falsifiable, point-in-time honest, and visibly learns.

### Goals
1. Calls that are objectively gradable from filings, with no price predictions.
2. Zero look-ahead leakage, enforced in one place and tested.
3. A visible, reproducible loop: call, grade, correction, Mubit update, better call.
4. A live demo that runs entirely from a local cache in under the time limit.

### Positioning
This is a research-support and QA loop for analysts, not a replacement for an investment firm. It covers fundamental research, committee-style synthesis and systematic post-mortems. Stretch features (section 11b) add watchlist screening, memo drafting and a calibration track record to fit an analyst's workflow.

### Non-goals
- Portfolio sizing, trade execution, compliance workflows.
- Price targets, buy/sell advice, trading signals.
- Ingesting full investor books.
- Real-time data. Everything is historical and cached.
- Production-grade scale. ~50 companies is enough.

---

## 2. Hackathon constraints (hard)

| Rule | Consequence for design |
|---|---|
| All code written during the event | No pasted legacy code. Open-source libraries only. |
| Every LLM call routes through Mubit | One shared client, base URL set to Mubit, one adapter per agent. |
| Judged on: Mubit use, usefulness, execution, live demo | The correction to model update step must be **visible on screen**. |
| Code freeze Sun 25 Oct 10:00 | Backup demo video recorded before freeze. |

Mubit's exact update API is unknown to us. Do not guess endpoints. Ask at office hours and read the docs the team has. Until then, code against the `ModelUpdater` interface in section 10.

---

## 3. Architecture

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

### Stack
Python 3.11, FastAPI, PostgreSQL, `edgartools`, `fredapi`, `pandas`, MCP Python SDK, Streamlit (default) or React for the dashboard, LLM calls via Mubit.

---

## 4. Data layer (`ingest/`, `store/`) : owner A

### 4.1 Sources
| Source | Used for |
|---|---|
| SEC `company_tickers.json` | Universe, CIK mapping |
| XBRL `companyfacts` / `frames` | Financial facts with filing dates |
| SEC `submissions` | Filing list, 8-K item codes (e.g. 4.01 auditor change) |
| EDGAR full-text search | Going-concern and risk text |
| FRED + ALFRED | Macro series with **vintages** (what was known then, not revised values) |
| Tiingo or Stooq | Prices, used only for context metrics, never as a prediction target |

SEC rules: `User-Agent` header with a name and email, stay under ~10 requests/second, cache raw responses on disk before parsing.

### 4.2 Universe
~50 US companies, chosen for: filings continuous 2017-2025, mix of sectors, a few that visibly suffer in 2020 (airlines, retail) and a few that don't. Frozen in `ingest/universe.json` early (Hour 3). Each gets a stable alias `anon_001`...`anon_050`.

### 4.3 Tables (Postgres)

```
companies   (company_id PK 'anon_001', cik, ticker, name, sector)      -- ticker/name never leave store
facts       (id, company_id, concept, value, unit, period_start, period_end,
             fiscal_period, form, accession, filed_date NOT NULL)
events      (id, company_id, form, items[], filed_date NOT NULL, accession, text_ref)
macro       (id, series_id, value, obs_date, vintage_date NOT NULL)
prices      (company_id, date, close)                                   -- context only
calls       (call_id PK, run_id, agent, company_id, as_of, payload JSONB, created_at)
grades      (call_id FK, graded_at, outcome, correct bool, brier, evidence JSONB)
corrections (correction_id PK, call_id FK, agent, summary, payload JSONB, mubit_ref, applied_at)
runs        (run_id PK, kind 'train'|'heldout', config JSONB, started_at)
```

### 4.4 Point-in-time rule (the most important rule in the project)
- Every row has a `filed_date` (or `vintage_date` for macro).
- At as-of date `t`, only rows with `filed_date <= t` exist.
- Enforced **only** in `store/queries.py`. No agent, metric or tool queries tables directly.
- A fact restated later appears as a **new row** with its own `filed_date`; the older row stays. At `t` we return the latest row with `filed_date <= t` for that `(concept, period_end)`.
- Never filter or order by `period_end` to decide visibility.
- **Leakage test** (`store/tests/test_leakage.py`): for sampled `(company, concept, t)`, assert no returned row has `filed_date > t`; assert a known restatement is invisible before its filing date; assert macro returns the vintage valid at `t`.

### 4.5 Store interface (contract between A and B)

```python
get_facts(company_id: str, concept: str, as_of: date) -> list[Fact]
get_events(company_id: str, as_of: date, forms: list[str] | None = None) -> list[Event]
get_macro(series_id: str, as_of: date) -> list[Point]
get_metrics(company_id: str, agent: str, as_of: date) -> dict
```

`get_metrics` is implemented in `metrics/` on top of the three getters above. Person B can develop against stub JSON until this is live (section 12).

---

## 5. Metrics engine and tools (`metrics/`, `tools/`) : owner A

**No number comes from an LLM.** Python computes every metric. Agents read numbers and judge them.

| Agent | Metrics (all computed at `as_of`) |
|---|---|
| Fundamentals | FCF (TTM), FCF margin, operating margin, ROIC, debt/EBITDA, YoY and QoQ trends, 8-quarter slope |
| Valuation | Reverse DCF implied growth, owner earnings yield, historical growth CAGR, margin of safety proxy |
| Moat | Gross margin level, 4q std-dev, trend, R&D and SG&A intensity, pricing power proxy (margin vs revenue growth) |
| Risk | Interest coverage, current ratio, cash runway, dividend history, auditor-change history, going-concern keyword hits, leverage trend |
| Scenarios | Revenue growth distribution (5y), cyclicality (beta of revenue to macro), macro regime (FRED: GDP, unemployment, yield curve, credit spread) |

Each metric returns `{name, value, unit, as_of, inputs: [accession...]}` so any number in a prompt can be traced to filings.

### MCP tools
Thin MCP servers wrap `get_metrics` plus drill-downs:
- `get_metric_series(company_id, metric, n_quarters)`
- `get_recent_events(company_id, forms)`
- `get_macro_snapshot()`
- `peer_compare(company_id, metric)` : within sector, anonymized

Agents may call tools freely, **capped at ~5 calls per run**. Tools are read-only and go through `store/queries.py`.

---

## 6. Schemas (fixed)

Do not change these without telling the other person. Agents must emit exactly this shape every time, otherwise grading and Mubit updates break. Use Pydantic models in `schemas/` (shared package, either person may edit this directory, tell the other).

### 6.1 AgentCall

```json
{
  "call_id": "uuid",
  "run_id": "uuid",
  "agent": "fundamentals | valuation | moat | risk | scenarios | synthesizer",
  "company_id": "anon_007",
  "as_of": "2019-06-30",
  "horizon": "next_quarter | 4_quarters | 12_months",
  "claim": {
    "type": "binary | bucket | numeric_band",
    "question_id": "fcf_margin_improves_next_q",
    "answer": "yes | no | bull | base | bear | ...",
    "probability": 0.68
  },
  "confidence": 0.68,
  "reasoning": ["max 5 short bullets, each citing a metric name"],
  "evidence": [{"metric": "fcf_margin_ttm", "value": 0.142, "as_of": "2019-06-30"}],
  "principles_used": ["buffett.03", "buffett.07"],
  "tool_calls": 3,
  "model": "mubit/<agent-model-version>"
}
```
`probability` is the probability the stated `answer` is correct, in [0,1]. `evidence` values must match what the metrics engine returned (checked at parse time; mismatch rejects the call).

### 6.2 Grade

```json
{
  "call_id": "uuid",
  "graded_at": "datetime",
  "resolution_date": "2019-10-31",
  "outcome": "yes | no | bull | base | bear | unresolvable",
  "correct": true,
  "brier": 0.1024,
  "evidence": [{"accession": "0000320193-19-000119", "concept": "...", "value": 0.151}]
}
```
`unresolvable` (missing filing, delisting) is excluded from accuracy and logged.

### 6.3 Correction

```json
{
  "correction_id": "uuid",
  "call_id": "uuid",
  "agent": "fundamentals",
  "company_id": "anon_007",
  "as_of": "2019-06-30",
  "predicted": {"answer": "yes", "probability": 0.68},
  "actual": {"outcome": "no", "evidence": [...]},
  "error_type": "overconfident | missed_regime | wrong_signal | ignored_metric",
  "lesson": "Agent weighted FCF trend and ignored rising capex intensity. Rule: when capex/revenue rises 3 quarters running, discount FCF improvement calls.",
  "principle_refs": ["buffett.03"],
  "inputs_snapshot": {"metrics": {...}, "reasoning": [...]}
}
```
`lesson` is generated by a separate "reflection" LLM call (via Mubit), given the call, the actual outcome and the metrics. It must reference a principle or a metric, not company names.

---

## 7. Agents (`agents/`, `principles/`) : owner B

All agents share one runner:
1. Load `principles/<investor>.md`.
2. Receive `company_id`, `as_of`, and pre-computed metrics from `get_metrics`.
3. May call MCP tools (max ~5).
4. Return one `AgentCall` (6.1). Invalid JSON gets one repair retry, then the call is dropped and logged.

Prompts contain only `company_id` (anon) and metrics. **No names, no tickers, no dates beyond `as_of` relative framing.** Mask years where possible (use "Q-8 ... Q0").

### 7.1 Agent definitions

| Agent | Investor | Question (`question_id`) | Answer type | Resolved by |
|---|---|---|---|---|
| Fundamentals | Buffett | `fcf_margin_improves_next_q`: FCF margin and operating margin both higher in next reported quarter vs latest reported | binary | Next 10-Q (or 10-K for Q4) |
| Valuation | Graham | `implied_growth_above_delivered`: reverse-DCF implied growth is above growth actually delivered over next 12 months | binary | Revenue growth in filings over next year |
| Moat | Buffett | `gross_margin_holds_2pts`: gross margin stays within ±2pts of current across next 4 quarters | binary | Next 4 filings |
| Risk | Munger | `distress_event_12m`: any of auditor change (8-K 4.01), dividend cut (>=25% reduction), going-concern language in the next 12 months | binary | 8-K item codes, XBRL dividends, 10-K text search |
| Scenarios | Dalio | `revenue_bucket_next_4q`: bull / base / bear for next-4-quarter revenue vs trailing | bucket | Actual revenue growth, bucketed |
| Synthesizer | Committee | `committee_verdict`: attractive / neutral / unattractive business outlook with confidence | bucket | Composite of the graded outcomes (see 8.4) |

Bucket definitions for Scenarios are fixed and numeric, set once in `grader/config.py`: bear < 0% growth, base 0-10%, bull > 10% (tune on training window only, never on held-out).

### 7.2 Principles (`principles/<investor>.md`)
- 5-10 checkable rules per investor, **in our own words**, each with an ID (`buffett.03`) and a citation (Berkshire letter year, *The Intelligent Investor* ch. 20, etc.).
- No long quotes, no full-book ingestion.
- Format per rule: `id | rule | how to check with metrics | source`.
- Corrections can propose **new or revised rules**; Mubit updates apply them per agent (section 10).

### 7.3 Synthesizer
Takes the other agents' calls (not raw data), weighs them by each agent's trailing accuracy (from `grades`), and outputs the committee verdict with a calibrated confidence. MVP: weighted vote plus an LLM-written rationale. Stretch: **cross-examination round**, where agents challenge each other's evidence (max 1 round).

**Built (B):** cross-examination in `agents/cross_exam.py` (`python -m agents.synthesizer --cross-exam`): confidence only, shift capped at 0.15, originals untouched. Tool use in `agents/runner.py` + `agents/tools.py`: off unless a toolbox is passed, at most 5 calls, instructions in the user message only, tool values citable as evidence. Valuation and Moat agents are in `agents/specs.py`; Moat reads `principles/buffett_moat.md` so the Fundamentals prompt (also Buffett) never changes. Their stub metrics are in `store/stubs/` and their metric names are the contract for `metrics/`.

### 7.4 Mubit adapter (one per agent)
`agents/adapters/<agent>.py` wraps the single Mubit client with that agent's identity, so Mubit tracks each agent's model separately. Interface in section 10.

---

## 8. Replay and grading (`grader/`) : owner A, orchestrator shared

### 8.1 Replay orchestrator
```
for as_of in quarter_ends(2018Q1 .. 2024Q4):
    for company in universe:
        for agent in active_agents:
            call = agent.run(company, as_of)      # sees only filed_date <= as_of
            store(call)
    grade_resolved_calls(as_of)                   # grade calls whose resolution_date <= as_of
    corrections = make_corrections(newly_graded)
    mubit.apply(corrections)                      # per-agent model update
    snapshot_metrics(as_of)                       # accuracy, Brier, per agent, for dashboard
```
Key points:
- A call is graded only once its resolution filing is visible at the current `as_of`. This keeps the loop honest: the system never learns from the future.
- Replay is deterministic where possible (temperature 0, fixed seeds, cached LLM responses keyed by prompt hash) so the demo is reproducible.
- Full replay is run **offline before the demo** and stored. The live demo replays stored results step by step, with at least one live call-to-correction-to-update shown for real.

### 8.2 Reality grader
- Pure Python, no LLM. Resolves each `question_id` using rules in `grader/rules.py` against filings with `filed_date` after `as_of`.
- One exception: the Risk rule's going-concern check (`grader/risk.py`). Python finds passages with "going concern" / "substantial doubt"; Mubit's **Banyan Sapling** verifier judges them against a written policy (real doubt vs boilerplate). Sapling `supported` = yes, `violation` = no, `insufficient_information` / `inconsistent_context` = `unresolvable`; an `unsure` status uses the top label only when it holds a majority (>= 0.50, `grader/config.py`; retune on the training window). Verdicts are cached in `data/sapling_cache/`, so the demo replays them with no live calls. Auditor changes (8-K 4.01) stay pure Python; the dividend-cut check is still to add.
- Produces `Grade` (6.2). Computes Brier score `(p - outcome)^2` for binary, multiclass Brier for buckets.
- Logs `unresolvable` cases instead of guessing.

### 8.3 Correction maker
For every incorrect call, plus every correct call with confidence > 0.8 that was a "lucky" miss on the key metric (stretch), emit a `Correction` (6.3). The `lesson` comes from a reflection LLM call routed through Mubit. Rate-limit to avoid flooding: max N corrections per agent per quarter (default 10), prioritized by confidence of the wrong call.

### 8.4 Metrics tracked
- Per agent: rolling accuracy, Brier score, calibration curve, per-regime accuracy (pre-COVID, crash, recovery).
- Committee: verdict accuracy. The composite outcome for the synthesizer is "majority of the underlying graded outcomes favoured the verdict".
- Baselines: always-yes, base rate, and a no-learning copy of each agent (frozen at the start). The learning agent beating its frozen twin is the headline result.

---

## 9. Held-out evaluation (`eval/`) : owner B

Prevents the demo from just showing overfitting.
- **Split by time and by company.** Train window: 2018-2022. Held-out window: 2023-2024. Hold out ~10 companies across all years.
- Mubit updates are learned **only** from train-window corrections.
- Report accuracy and Brier on held-out for: (a) frozen agents, (b) learned agents, (c) baselines.
- Held-out results are generated once, before freeze, and shown as a single slide/panel. No tuning against them.
- Stretch: frontier-model comparison (same questions, a larger model with no learning), shown as a bar next to ours.

**Status (harness built, results pending).** `eval/` implements the split, the frozen twin (`agents/frozen.py`), both baselines, the frontier-model arm (`--frontier-model`), accuracy curves (`--curves`) and the report. Run `python -m eval.run` for an offline preview (stub metrics, scripted LLM, stamped NOT RESULTS, written to `data/eval_preview/`). `python -m eval.run --live` is a dry run that prints the call count; `--live --yes` spends real Mubit calls. `--save postgres` (or `--save <dir>` for JSONL) stores runs, calls, grades, corrections, snapshots and the report for the dashboard (`agents/run_store.py`, extra tables in `schemas/run_extras.sql`). The official report goes to `eval/reports/` only for runs on real inputs and is never overwritten without `--force`. It needs Person A's real `get_metrics` and the fundamentals and scenarios grader rules first (`eval/metrics_source.py` is the one switch). Results section: none yet, by design.

---

## 10. Mubit integration

Our code depends on an interface, not on Mubit's API directly:

```python
class LLMGateway:                       # all LLM calls go through here -> Mubit base URL
    def complete(self, agent: str, messages: list, **kw) -> str: ...

class ModelUpdater:
    def submit_corrections(self, agent: str, corrections: list[Correction]) -> UpdateRef: ...
    def get_model_version(self, agent: str) -> str: ...      # stamped into AgentCall.model
    def status(self, ref: UpdateRef) -> UpdateStatus: ...
```

- A `FakeModelUpdater` (appends lessons to the agent's principle file / few-shot memory) is the fallback so the demo works if Mubit's API is late or flaky. It must be labelled as fallback in the UI if used.
- The dashboard shows, for a chosen correction: the original call, the actual outcome, the lesson, the Mubit update reference, and the agent's model version before and after, then the same company asked again in a later quarter.
- **Open items for office hours:** exact update endpoint and payload, latency of updates, per-agent isolation, rate limits, how version IDs are exposed.

---

## 11. Dashboard (`dashboard/`) : owner A

Streamlit by default (fast to build). Reads only from Postgres, never calls live APIs.

| View | Content |
|---|---|
| Replay timeline | Slider/play button over quarters 2018Q1-2024Q4; shows current `as_of` |
| Accuracy curves | Rolling accuracy and Brier per agent, learned vs frozen twin, with COVID window shaded |
| Committee table | For a chosen company and quarter: each agent's call, confidence, reasoning bullets, synthesizer verdict |
| Correction spotlight | The call to actual to lesson to Mubit update path (the judging moment) |
| Held-out panel | Frozen vs learned vs baseline on 2023-2024 |
| Scoreboard (stretch) | "Legend scoreboard": which investor's rules are doing best now |

A disclaimer footer is always visible: "Research tool, not financial advice."

---

## 11b. Analyst workflow layer (stretch)

Turns the call-grade-correct engine into something that fits an investment team's research workflow. Three features, all built **on top of** existing stores and schemas. None changes the MVP or the never-cut list. All rules in CLAUDE.md still apply: no LLM-generated numbers, point-in-time only, no price predictions, no buy/sell language.

### 11b.1 Watchlist screener (`screener/`, owner A)
- Input: a watchlist (subset of the universe) and an `as_of` date.
- Pure Python, no LLM. Ranks companies by **flags computed from `get_metrics`**: e.g. FCF margin slope turning negative, interest coverage below threshold, gross margin std-dev rising, going-concern keyword hit.
- Optionally ranks by the committee's latest calls (distress probability, scenario bucket) stored in `calls`.
- Output: `ScreenResult {company_id, as_of, flags: [{metric, value, threshold, accessions}], rank_score}`. Every flag is traceable to filings, like any metric.
- Thresholds are fixed in `screener/config.py`, tuned on the train window only.
- Framed as "needs analyst attention", never "buy/sell".

### 11b.2 Analyst memo drafting (`memos/`, owner B)
- For a chosen company and `as_of`, assemble a structured memo from **existing outputs only**: the metrics bundle, each agent's `AgentCall` (reasoning bullets, evidence), the synthesizer verdict, and recent events.
- The LLM (via Mubit `LLMGateway`) writes prose around the numbers. **It may not introduce numbers**: every figure in the memo must come from a `{{metric:name}}` placeholder the renderer fills from the metrics engine. A post-check rejects memos containing any numeric literal not produced by a placeholder.
- Sections: Business outlook summary, Key metrics (table rendered by Python), Agent views and disagreements, Risks and distress flags, What would change the view (referencing principles), Source accessions.
- Anonymized by default. Name/ticker mapping happens only at render time in the dashboard, and only for the demo's chosen company, never in the prompt.
- Footer on every memo: "Research tool, not financial advice."

**Built (B):** `memos/` (`python -m memos --company anon_001 --as-of 2019-06-30`). The drafter writes four prose sections using placeholders only; `check_prose` rejects any digit, unknown placeholder or buy/sell language, with one repair retry, then the memo renders without LLM prose.

### 11b.3 Calibration and track-record tracker (`grader/calibration.py`, owner A)
- Maintains a persistent track record per agent (and per principle ID used): accuracy, Brier, calibration curve, overconfidence gap (mean confidence minus accuracy), per-regime breakdown.
- Computed only from `grades`, as-of aware: at replay date `t` it includes only grades resolved by `t`.
- Feeds the synthesizer's weights (7.3) and a "stale principle" flag when a principle's rolling Brier degrades.
- Exposes `get_track_record(agent, as_of) -> TrackRecord`, used by the dashboard, memos and screener.

### 11b.4 Dashboard additions
| View | Content |
|---|---|
| Watchlist screen | Ranked table of flagged companies at the current `as_of`, click-through to metrics |
| Memo view | Generated memo for a chosen company and quarter, with metric table and source accessions |
| Track record | Per-agent and per-principle calibration curves and overconfidence gap |

### 11b.5 Out of scope, even in stretch
Portfolio sizing, trade execution, price targets, compliance workflows, real-time feeds. This stays a research-support tool.

---

## 12. Interfaces and parallel development

Person B must never be blocked on Person A. Day 1 deliverables:
- `schemas/` with Pydantic models for 6.1-6.3 (merged first, by Hour 2).
- `store/stubs/` with 5 hand-written stub JSON metric bundles per agent matching `get_metrics` output. B develops against `get_metrics_stub()`, then flips an env flag to the real store.
- `grader/` exposes `grade(call) -> Grade` with a stub rule set, so B can test the learning loop on fake outcomes.

Integration checkpoints: Hour 10 (real metrics for one company flow into one agent), Hour 20 (full vertical slice: one company, one agent, one quarter, graded and corrected), Hour 30 (full replay running).

---

## 13. Repo layout

```
agents/       runner, adapters/, one module per agent, synthesizer          (B)
principles/   buffett.md, graham.md, munger.md, dalio.md                    (B)
eval/         held-out split, baselines, report generation                  (B)
ingest/       SEC/FRED/price fetchers, universe.json, raw cache             (A)
store/        schema.sql, queries.py (point-in-time gate), stubs/, tests/   (A)
metrics/      one module per agent's metric set                             (A)
tools/        MCP servers                                                   (A)
grader/       rules.py, grade.py, corrections.py, replay.py, calibration.py (A)
screener/     watchlist flags and ranking (stretch)                         (A)
memos/        memo assembly, placeholder renderer, number check (stretch)   (B)
dashboard/    Streamlit app                                                 (A)
schemas/      shared Pydantic models                                        (shared)
.env.example  keys listed, no values
```

---

## 14. Testing

Minimum tests (the project cannot demo without these):
1. **Leakage test** for `store/queries.py` (4.4).
2. **Grader rule tests**: one fixture per `question_id` with a known filing, asserting correct outcome, including a restatement case.
3. **Schema validation**: every stub and every real call parses against `AgentCall`.
4. **Metrics traceability**: each metric returns `inputs` accessions that exist in `facts`.
5. **Smoke test**: one company, one agent, two consecutive quarters, end to end including a correction.

---

## 15. Demo (3-4 min, adjust to the time limit)

1. **Hook (20s):** "A team of AI analysts that grades itself against reality."
2. **Setup (30s):** anonymized company, Buffett agent at 2019Q2, sees only what was public.
3. **The call (30s):** committee table, calls with confidence.
4. **Reality (30s):** next filing arrives, call graded wrong.
5. **Correction to Mubit (45s):** lesson text, Mubit update, new model version. **This is the judging moment.**
6. **Learning shown (30s):** same kind of case later, now right. Accuracy curve climbing.
7. **COVID (30s):** crash drops accuracy, recovery follows.
8. **Held-out (20s):** frozen vs learned vs baseline on unseen years.

Backup: a recorded video of the full flow, made before freeze. If live fails, play it.

---

## 16. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Look-ahead leakage | Single gate, leakage test, anonymization, masked dates |
| LLM memorizes company outcomes | Anonymize, strip names/tickers, mask years, report held-out by company |
| Mubit API late or unclear | `ModelUpdater` interface and `FakeModelUpdater` fallback, ask at office hours early |
| SEC rate limits / slow ingest | Start ingest by Hour 3, cache raw, ~50 companies only |
| XBRL concept inconsistency across filers | Small fixed concept map with fallbacks; drop companies that don't map cleanly |
| Replay too slow for live demo | Precompute everything, replay stored results, show one live loop |
| Accuracy doesn't improve | Report honestly; show per-regime and calibration gains; frozen-twin comparison is still a result |
| Scope creep | Follow the cut list below |

---

## 17. Scope

**MVP (must ship):** Fundamentals, Risk, Scenarios + synthesizer + grader + Mubit correction loop + replay dashboard, ~50 companies.

**Stretch (in order):** Valuation, Moat, track-record tracker (11b.3), held-out frontier-model comparison, watchlist screener (11b.1), analyst memos (11b.2), cross-examination round, legend scoreboard, Firecrawl press releases as an extra event source.

**Never cut:** point-in-time store, reality grader, correction-to-Mubit loop, held-out eval, backup demo video.

---

## 18. Timeline (~37 hours, indicative)

| Hours | A: data and grading | B: agents and Mubit |
|---|---|---|
| 0-3 | Repo, Postgres schema, universe, start ingest | `schemas/`, stubs, Mubit client setup, ask office-hours questions |
| 3-10 | Facts/events ingest, `queries.py`, leakage test | Agent runner, Fundamentals agent on stubs, principles drafts |
| 10-20 | Metrics for MVP agents, grader rules, first grades | Risk + Scenarios, Synthesizer, reflection prompt, ModelUpdater |
| 20-30 | Replay orchestrator, full ingest QA, dashboard v1 | Correction loop with real Mubit, held-out eval harness |
| 30-34 | Dashboard polish, correction spotlight | Full replay run, baselines, held-out report |
| 34-37 | Record backup video, freeze checks | Tune demo script, README results section |

---

## 19. Open questions

1. Mubit update API shape and latency (office hours).
2. Exact universe list (decide by Hour 3).
3. Streamlit vs React (default Streamlit unless someone wants the polish).
4. How many corrections per agent per quarter before updates become noisy (start at 10, tune on train window).
5. Whether to include Valuation in MVP if Fundamentals/Risk/Scenarios finish early.

---

*Research tool, not financial advice.*
