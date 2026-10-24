# Brief for Hermes: Person A workstreams

You are doing four independent pieces of Person A's work on **Compounding Minds** while Claude Code builds the metrics engine in parallel. Read this whole file first, then do the workstream you were told to do (H1 to H4). Each workstream is self-contained: its own branch, its own files, its own tests. When all are done we merge them together.

## 0. The project in one paragraph

A committee of AI analysts. Each agent follows one investor's rules (Buffett, Munger, Dalio), makes one checkable call about a company at a past date, and is marked against what later SEC filings reported. Wrong calls become corrections and Mubit updates that agent. A replay runs 2018 to 2024 quarter by quarter on 50 anonymised companies. **Code freeze is Sun 25 Oct 10:00.** Read `CLAUDE.md` (rules), `README.md` (spec), `TASKS.md` (who owns what) and `ARCHITECTURE.md` if you need more. This brief is enough to start.

## 1. Rules that apply to every workstream

**Non-negotiable project rules** (full list in `CLAUDE.md`):
1. **No number comes from an LLM.** Python computes every metric.
2. **Point-in-time only.** Anything an agent can see is filtered by `filed_date <= as_of` in `store/queries.py`. Never read tables directly from agent-facing code.
3. **No price predictions, no buy or sell language.** Footer wherever a user reads output: "Research tool, not financial advice."
4. **Agents never see names, tickers, calendar dates or accession numbers.** An accession like `0000320193-18-000070` contains the year, so it is a date leak. Use relative quarters: Q0 is the latest reported quarter, Q-1 the one before.
5. **No secrets in git.** Keys live in `.env` (gitignored).

**Git**
- Branch from the current tip of `person-a/data-and-agents`: `git fetch && git checkout -b hermes/<name> origin/person-a/data-and-agents`.
- Branch names: `hermes/tools` (H1), `hermes/eval` (H2), `hermes/content` (H3), `hermes/sources` (H4).
- Push your branch only: `git push -u origin hermes/<name>`. **Never push to `main` or `person-a/data-and-agents`.**
- Small commits with clear messages. Do not commit generated files, `data/`, `.env` or `__pycache__`.

**Files you may NOT edit** (we edit these after merging, so nothing collides): `TASKS.md`, `README.md`, `CLAUDE.md`, `requirements.txt`, `.env.example`, `store/queries.py`, `store/schema.sql`, `store/concepts.py`, `schemas/`, `agents/` (read it all you like), `grader/`, `ingest/`, `metrics/`, `principles/*.md` (except H4, see below), `conftest.py`. If you need a change in one of them, write it in your report under "Requests" and carry on without it.

**Tests**
- Every workstream ships tests, and `python -m pytest -q` must be fully green before you report. The suite has 128 tests today; do not break any.
- Python 3.11 or 3.13. Install with `pip install -r requirements.txt`. If you need another package, install it for yourself and list it under "Dependencies" in your report; do not edit `requirements.txt`.
- Tests that need Postgres use the `pg_conn` fixture in `conftest.py` and **skip themselves** if no database is reachable. To run them: `docker compose up -d`, then `TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres python -m pytest -q`. Prefer pure-Python tests with small fixtures wherever you can.
- No test may call the network, Mubit or an LLM.

**Style:** match the surrounding code: type hints, short docstrings that say *why*, no needless abstraction, plain functions over classes where a function will do. Comments explain decisions, not what the line does.

**When you finish, report in this format** (paste it as your final message, and also save it as `REPORT_<name>.md` in the repo root on your branch):
```
Workstream: H<n>   Branch: hermes/<name>   Commits: <n>
Done: <3 to 6 bullets>
Files: <list>
Tests: <n> new, <total> passing, <n> skipped
Deviations from this brief: <or "none">
Requests (changes needed in files I may not edit): <or "none">
Dependencies: <packages you installed, or "none">
Open questions: <or "none">
```

## 2. Facts you need about the code

**Shared shapes** (`schemas/models.py`): `AgentCall` (agent, company_id `anon_NNN`, as_of, claim{question_id, answer, probability}, confidence, reasoning, evidence, principles_used, tool_calls 0 to 5, model), `Grade` (call_id, outcome, correct, brier, evidence), `Correction`, plus store rows `Fact`, `Event`, `Point`.

**The date gate** (`store/queries.py`): `get_facts(company_id, concept, as_of)`, `get_events(company_id, as_of, forms=None)`, `get_macro(series_id, as_of)`. Set the backend once: in tests `queries.set_backend(InMemoryBackend(facts=[...], events=[...], macro=[...]))`, in production `queries.set_backend(PostgresBackend(conn))`.

**Metrics.** Agents are shown a *bundle*: `{"company_id", "agent", "as_of", "metrics": [{"name","value","unit","as_of","inputs":[accession,...]}]}`. Claude Code is writing the real `get_metrics(company_id, agent, as_of) -> bundle`. **Until it lands, use the stub** `store.stubs.get_metrics_stub(company_id, agent, as_of)`, which has exactly the same shape. Metric names by agent (this list is a locked contract):

| Agent | Metrics |
|---|---|
| fundamentals | `fcf_margin_ttm`, `fcf_margin_qoq_change`, `operating_margin`, `roic`, `debt_to_ebitda`, `fcf_slope_8q`, `capex_to_revenue` |
| risk | `interest_coverage`, `current_ratio`, `cash_runway_quarters`, `dividend_cut_history_5y`, `auditor_changes_5y`, `going_concern_hits`, `leverage_trend_8q` |
| scenarios | `revenue_growth_yoy`, `revenue_growth_mean_5y`, `revenue_growth_std_5y`, `revenue_macro_beta`, `gdp_growth_yoy`, `unemployment_rate`, `yield_curve_10y_2y`, `credit_spread_baa` |

**Agents** (`agents/runner.py`): `run_agent(agent, company_id, as_of, metrics, gateway, updater, run_id=None, lessons=None) -> AgentCall | None`. It returns `None` when the model's reply was invalid twice (the call is dropped and logged). `agents/specs.py::SPECS` has the three questions: `fcf_margin_improves_next_q` (yes/no), `distress_event_12m` (yes/no), `revenue_bucket_next_4q` (bear/base/bull).

**Scoring helpers** (`grader/scoring.py`): `brier_binary`, `brier_multiclass`, `p_yes`, `bucket_for_growth`. Read them before using them, and reuse them rather than rewriting the maths.

**Universe** (`ingest/universe.py`): `load_universe()`, `held_out_ids()`, `train_ids()`. 50 companies, 10 held out.

**Tables you may read** (`store/schema.sql`): `calls(call_id, run_id, agent, company_id, as_of, payload JSONB)`, `grades(call_id, outcome, correct, brier, ...)`, `runs(run_id, kind, config JSONB)`, `snapshots(run_id, agent, variant, as_of, n_calls, n_correct, accuracy, brier, model)`.

---

## H1. MCP tools (`hermes/tools`)

**Goal.** The four read-only tools an agent may call while reasoning (at most about 5 calls per run), as plain Python functions plus an MCP server around them.

**Files (yours):** `tools/__init__.py`, `tools/impl.py`, `tools/server.py`, `tools/tests/test_tools.py`, `tools/tests/__init__.py`. Delete `tools/.gitkeep`.

**Design (follow it, it is what keeps the tools leak-proof):**

1. Build one `Tools` object **per agent run**, with `as_of` fixed at construction:
   ```python
   Tools(company_id, as_of, metrics_fn, events_fn, sector_of, universe_ids, budget)
   ```
   - `metrics_fn(company_id, agent, as_of) -> bundle` (default `store.stubs.get_metrics_stub` until the real one lands; make it injectable)
   - `events_fn(company_id, as_of, forms)` defaulting to `store.queries.get_events`
   - `sector_of(company_id) -> str`, `universe_ids: list[str]` for peer lookups (injected, so no database is needed in tests)
   - `budget: ToolBudget(max_calls=5)`
   **No tool takes an `as_of` argument.** The model must never choose a date.
2. The tools (each returns JSON-serialisable data, never a pandas object):
   - `get_metric_series(metric, n_quarters=8) -> list[{"quarter": "Q-7".."Q0", "value": float}]`. Compute it by calling `metrics_fn` at each of the last `n_quarters` calendar quarter-ends on or before `as_of`, each **at its own date** (point-in-time correct). Label quarters relative to the latest: Q0, Q-1, and so on. Find which agent owns the metric from the table in section 2. Unknown metric: raise `ToolError` naming the valid metrics.
   - `get_recent_events(forms=None, n=5) -> list[{"form", "items", "quarters_ago"}]`. Read through `events_fn`. **Do not return `filed_date` or `accession`.** `quarters_ago` is a whole number relative to `as_of`.
   - `get_macro_snapshot() -> {"gdp_growth_yoy", "unemployment_rate", "yield_curve_10y_2y", "credit_spread_baa"}`, taken from the scenarios bundle at `as_of`.
   - `peer_compare(metric) -> {"value", "peer_median", "peer_count", "percentile"}` against other companies in the **same sector** at the same `as_of`, excluding the company itself. Peers with no value are skipped. Fewer than 3 peers: return `peer_count` and `null` for the other stats, never a guess.
3. `ToolBudget`: counts calls across all four tools. The 6th call raises `ToolBudgetExceeded`. Expose `budget.used` (the runner will write it into `AgentCall.tool_calls`).
4. `tools/server.py`: `build_server(tools) -> FastMCP` registering the four tools with the MCP Python SDK (`pip install mcp`, `from mcp.server.fastmcp import FastMCP`). Tool descriptions are plain, short, and say what comes back. The server must start with no network. Do not run a server in tests; test that building it registers exactly four tools, and `pytest.importorskip("mcp")` that one test.

**Tests (all must pass without a database):**
- point-in-time: a series built for an earlier `as_of` never contains a value that only existed later (use a fake `metrics_fn` that records the `as_of` it was called with and assert every call is `<= as_of`)
- events filed after `as_of` are not returned (use `InMemoryBackend`)
- no output of any tool contains a four-digit year (`\b(19|20)\d{2}\b`), an accession pattern (`\d{10}-\d{2}-\d{6}`), a ticker, or a company name
- `peer_compare` excludes self, stays inside the sector, and returns `null` stats under 3 peers
- the budget: the 5th call works, the 6th raises, and calls to different tools share one count
- an unknown metric raises `ToolError` with the valid names
- quarter labels are `Q0` for the latest and count down

**Done when:** the tests above pass, `python -c "from tools.server import build_server"` imports cleanly, and your report says exactly how the runner should wire it (`tools = Tools(...); server = build_server(tools)`).

---

## H2. Evaluation (`hermes/eval`)

**Goal.** Prove the learning works, honestly: frozen twins, baselines, a held-out split, and a quality report. This is what the judges see on the held-out panel.

**Files (yours):** `eval/__init__.py`, `eval/frozen.py`, `eval/baselines.py`, `eval/split.py`, `eval/metrics.py`, `eval/report.py`, `eval/load.py`, `eval/cli.py`, `eval/tests/`. Output goes to `eval/out/` (create it with a `.gitkeep`, and add generated files to nothing: do not commit them). Delete `eval/.gitkeep`.

**Core data type.** Everything works on plain records so it is testable without a database:
```python
@dataclass(frozen=True)
class Scored:
    call: AgentCall
    grade: Grade            # outcome in yes|no|bull|base|bear|unresolvable
    variant: str            # "learned" | "frozen"
```
`unresolvable` grades are **excluded from accuracy and Brier** and counted separately.

**What to build**
1. `eval/frozen.py`: `FrozenUpdater(ModelUpdater)` from `agents/gateway.py`. `get_model_version(agent)` returns `"<base>-frozen"`, `submit_corrections` does nothing and returns an `UpdateRef(agent, "frozen")`, `status` returns `UpdateStatus("applied")`, and a `lessons(agent)` method returns `[]`. A frozen twin is "the same agent, same prompts, never updated": it is the control. Add `run_frozen(agent, company_id, as_of, metrics, gateway, run_id)` that calls `agents.runner.run_agent(..., lessons=[])` with a `FrozenUpdater`.
2. `eval/baselines.py`: two baselines per agent, producing a probability for the **yes answer** (or a bucket distribution for scenarios) so they get a Brier score too:
   - `always_yes`: always answers `yes` (scenarios: always `base`) with probability 1.0
   - `base_rate`: answers the most common outcome **in the training window only** with probability equal to that outcome's training frequency. It must not look at held-out data. A test must prove that changing a held-out outcome does not change the baseline.
3. `eval/split.py`: three slices, by time (train 2018 to 2022, held-out 2023 to 2024) and company (`ingest.universe.held_out_ids()`):
   - `unseen_years`: training companies, 2023 to 2024
   - `unseen_companies`: held-out companies, all years
   - `unseen_both`: held-out companies, 2023 to 2024
   A call's year is `call.as_of.year`. Provide `slice_of(call, held_out_ids) -> list[str]`.
4. `eval/metrics.py`: pure functions over `list[Scored]`: `accuracy`, `mean_brier`, `calibration_bins(n_bins=5)` returning `[{"lo","hi","n","mean_confidence","accuracy"}]`, `overconfidence_gap` (mean confidence minus accuracy), `valid_json_rate(calls, attempted)` (calls produced divided by attempts; the runner drops invalid ones, so `attempted` is passed in), `evidence_match_rate` (share of calls whose evidence values equal the bundle values; take the bundles as an argument).
5. `eval/report.py`: builds the held-out report and the quality report from `list[Scored]` plus baselines. Writes two files into `eval/out/`:
   - **`heldout.json`** (the contract with Person B's dashboard; keep these keys exactly):
     ```json
     {
       "generated_at": "ISO datetime",
       "split": {"train_years": [2018, 2022], "heldout_years": [2023, 2024], "heldout_company_ids": ["anon_003"]},
       "agents": {
         "fundamentals": {
           "slices": {
             "unseen_years":     {"n": 0, "learned": {"accuracy": null, "brier": null}, "frozen": {"accuracy": null, "brier": null}, "always_yes": {"accuracy": null, "brier": null}, "base_rate": {"accuracy": null, "brier": null}},
             "unseen_companies": {},
             "unseen_both":      {}
           },
           "unresolvable": 0
         }
       },
       "notes": ["learned does not beat frozen on <agent>/<slice>"]
     }
     ```
     Use `null`, never `NaN`, when a slice has no calls. Add a note whenever learned does **not** beat frozen: the report must say so plainly. Never tune anything against held-out data.
   - **`quality.md`**: one section per agent with a table (valid-JSON rate, evidence match, accuracy, Brier, overconfidence gap, calibration bins) and a short plain-English critique paragraph written from the numbers: where the agent is weak, in one or two sentences. Generate the sentence from rules (for example: overconfidence gap above 0.10 means "overconfident"), not from an LLM.
6. `eval/load.py`: `load_scored(conn, run_ids=None) -> list[Scored]` reading `calls` joined to `grades` in Postgres. The variant comes from `runs.config->>'variant'`, defaulting to `learned` when missing. The payload column is an `AgentCall` as JSON. Person B writes those rows; a database test with a few hand-inserted rows is enough.
7. `eval/cli.py`: `python -m eval.cli --out eval/out` loads from `DATABASE_URL` and writes both files. `--demo` builds a synthetic set so the command can be tried with no database.

**Tests**
- accuracy and Brier on a hand-computed set of 6 records, to 6 decimal places
- `unresolvable` is excluded from both, and counted
- the base-rate baseline uses training data only (the held-out-leak test above)
- each call lands in exactly the right slices (check the boundaries: 2022-12-31 is training, 2023-01-01 is held-out; a held-out company in 2021 is only in `unseen_companies`)
- `heldout.json` has exactly the keys above, valid JSON, no `NaN`
- the "learned does not beat frozen" note appears when it should and not otherwise
- `FrozenUpdater` never changes version and ignores corrections
- one database test (skipped without Postgres) for `load_scored`

**Done when:** `python -m eval.cli --demo --out eval/out` writes both files and the tests pass.

---

## H3. Content (`hermes/content`)

**Goal.** The words: the demo script, the dashboard copy, the memo templates and the README results skeleton. Writing, not code. Audience: hackathon judges and investment analysts.

**Files (yours):** create `docs/content/` containing `demo_script.md`, `dashboard_copy.md`, `memo_templates.md`, `results_skeleton.md`. Nothing else.

**Read first:** `README.md` (sections 1, 10, 11, 11b, 15), `PROJECT.md`, `user-journey.html` (open it, it shows every screen and the journey), `principles/*.md`.

**Voice (apply to every file):** plain verbs, sentence case, active voice, no filler, no hype. Describe what something *is* or *does*, not how it is built: a user "opens a correction", not "queries the corrections table". A button says exactly what happens ("Run live loop", not "Submit"), and the same action keeps the same name everywhere. Error and empty states say what happened and what to do next; they do not apologise.

1. **`demo_script.md`**: a 3 to 4 minute script. A table with columns: time, what is on screen, what is said (written out in full), what the presenter clicks. Follow README section 15 (hook, setup, the call, reality, correction to Mubit, learning shown, COVID, held-out). The Mubit correction moment is the judging moment: give it the most time and say plainly what the audience should see (the lesson, the model version before and after). Include: a 20-second version for if time runs short, a "if the live loop fails" fallback line that points to the backup video, and a closing line. Then a **Q&A section of 10 likely judge questions with honest answers**, covering at least: is this leaking the future, why not predict prices, what stops the LLM inventing numbers, what if Mubit is down, does it actually improve, how do you know it is not overfitting, why anonymised companies, what are the limits. Where an answer depends on a real result, write `[RESULT: ...]` as a placeholder. **Never invent a result, accuracy figure or claim of improvement.**
2. **`dashboard_copy.md`**: every label on every screen in `user-journey.html`: controls, column headers, tooltips, the Right and Wrong marks, the correction spotlight's four stages, the held-out panel title and its "learned does not beat frozen" message, the Live today tab (stretch), empty states (no calls yet at this date, company not supported, Mubit running in fallback mode), error states, and the footer disclaimer "Research tool, not financial advice." One table per screen: element, text, note.
3. **`memo_templates.md`**: the six memo sections from README 11b.2 (Business outlook summary, Key metrics, Agent views and disagreements, Risks and distress flags, What would change the view, Source accessions). Each is a template with `{{metric:name}}` placeholders where a number goes. **The only way a figure may appear in a memo is as a `{{metric:<name>}}` placeholder using a real metric name from the table in section 2.** Never write a literal number. Never write buy, sell, target or recommend. Include two worked examples using placeholders only.
4. **`results_skeleton.md`**: the structure of the README's results section with **every number as a placeholder** `[RESULT: ...]`: what was measured, the three slices from H2, a table of learned vs frozen vs baselines, an honest paragraph for each outcome (it beat frozen; it matched; it lost), and a limits paragraph.

**Done when:** all four files exist, the Q&A has 10 answered questions, no file contains an invented number, and you searched your own files for the words `buy`, `sell`, `target price`, `recommend` and `outperform` and removed any that read as advice.

---

## H4. Citation check (`hermes/sources`)

**Goal.** The principle files cite books and letters from memory. Check each citation and fix what is wrong. This is the one workstream that needs the web.

**Files (yours):** `principles/SOURCES.md`, and **only the source column** (the last `|`-separated field) of lines in `principles/buffett.md`, `munger.md`, `dalio.md`, `graham.md`. Do not touch ids, rules or the "how to check" column: tests parse them.

**For each row in `principles/SOURCES.md`:**
1. Find the cited source online. Berkshire shareholder letters are public at `berkshirehathaway.com/letters/letters.html`. For books that are not free online (Poor Charlie's Almanack, The Intelligent Investor, Principles), look for the table of contents, publisher page or a reputable summary that confirms the chapter or section exists and covers the idea.
2. Decide: **Verified** (the source plainly covers the idea), **Wrong place** (the idea is real but the pointer is wrong: give the correct one), or **Cannot confirm** (no reliable evidence).
3. Update the table: tick the box for Verified, and add a short evidence note and the URL in a new column. For Wrong place, fix the pointer in `SOURCES.md` **and** in the matching line of the principles file. For Cannot confirm, rewrite the citation as `derived rule, our own synthesis of <ids>` (as `buffett.06` already does) and say why in the evidence note.

**Rules**
- **No long quotes.** A short phrase (under 15 words) in the evidence note is the maximum; paraphrase the rest. Do not paste passages from books or letters.
- Do not change what a rule *says*. If you think a rule is wrong, put it under "Open questions".
- The tests in `agents/tests/test_principles_contract.py` must still pass (they check the line format and metric names): run them after every edit.
- If a site blocks you, say so in the report rather than guessing.

**Done when:** every row of `principles/SOURCES.md` has a verdict and evidence, the tests pass, and the report lists the rows that changed.

---

## 3. After you finish

Push your branch, then tell Person A the branch name and paste your report. Claude Code reviews each branch, runs the full suite after merging it, and merges in this order: tools, eval, content, sources. If a merge conflicts, we resolve it; you do not need to. If something in this brief is wrong or contradicts the code, trust the code, say so in "Deviations", and keep going.
