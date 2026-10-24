# Investor UI: React front end on a FastAPI layer

Owner: Person B (output). Touches only new dirs `api/` and `web/`; reads existing code, never edits it. Code freeze Sun 25 Oct 10:00.

## 1. Goal

An investor picks a company. The page shows the pipeline running (ingest, metrics, committee, cross-examination), then a verdict page: **Investable on evidence / Watch / Not investable on evidence**, with the committee split, each investor's reasoning, the evidence behind it, risks, scenarios, and what Mubit has taught each agent.

Rules that still apply (CLAUDE.md): no LLM-generated numbers, point-in-time only, no live API calls in the demo, anonymized prompts (names mapped at render time only), "Research tool, not financial advice" visible on every screen, no "you should buy" wording. The verdict label is an evidence assessment, not a recommendation.

## 2. Architecture

```
web/ (React + Vite + TS)  --HTTP/SSE-->  api/ (FastAPI)  -->  existing modules
                                                               store/queries.py      point-in-time facts, metrics
                                                               agents/runner.py      agent calls (via Mubit gateway)
                                                               agents/cross_exam.py  revisions
                                                               agents/synthesizer.py verdict + confidence
                                                               dashboard/data.py     track records, corrections
                                                               data/runs, Postgres   cached runs
```

Demo mode (default): `/api` replays a stored run from `data/runs` and streams it as timed events, so the pipeline "runs" with no live calls. Live mode (flag `LIVE=1`, off for the demo): calls the real runner for a cached company. Both emit the same event stream, so the UI cannot tell them apart.

## 3. API contract (`api/`)

| Endpoint | Returns |
|---|---|
| `GET /companies` | universe: `id`, display name/ticker (render-time map), sector, held-out flag |
| `POST /assessments` `{company_id, as_of}` | `{assessment_id}`; starts a run (or replay) |
| `GET /assessments/{id}/events` (SSE) | ordered events: `stage` (ingest, metrics, committee, cross_exam, synthesis), `agent_call`, `revision`, `verdict`, `done` |
| `GET /assessments/{id}` | final `Assessment` JSON (below), for reload and sharing |
| `GET /agents/{agent}/track-record?as_of=` | rolling accuracy, Brier, model version, latest correction story |
| `GET /health` | source in use (postgres or jsonl), stub banner flag |

`Assessment`:
```
company, as_of, label, score, confidence, stub (bool)
committee[]: agent, investor, question, answer, confidence, reasoning[], evidence[{metric, value, accession}], revised_from?
agreement: votes_for / against / neutral, dissent[]
metrics[]: name, value, unit, trend[], accession      # Python-computed only
risks[]: from Risk agent
scenarios: bull/base/bear buckets from Scenarios agent
mubit[]: per agent {model_version, accuracy, n, last_correction{call, actual, lesson, update_ref}}
disclaimer
```
Pydantic models in `api/models.py` reuse `schemas.AgentCall` rather than redefining it. Generate TS types from the OpenAPI schema (`openapi-typescript`) so front and back cannot drift.

## 4. Front end (`web/`)

Stack: Vite, React, TypeScript, Tailwind, Framer Motion, Recharts (or visx), TanStack Query, native `EventSource`. Dark theme, one accent per verdict state, tabular numerals for figures.

Screens:
1. **Select**: searchable company grid or command palette, sector filter, as-of picker.
2. **Run**: vertical pipeline with live stage states, then investor "seats" that light up as each call lands. Cross-examination shows confidence revisions as small arrows. Skippable.
3. **Verdict**: hero with the label, a confidence ring, and the committee vote bar. Underneath: one card per investor (call, confidence, reasoning bullets, evidence chips linking to the filing accession), metric sparklines, risk list, bull/base/bear strip.
4. **Mubit panel**: per agent, track-record sparkline and model version; a "what it learned" card showing call, outcome, lesson, update ref, version before and after.
5. **Footer**: disclaimer, stub banner when data is not real results.

## 5. Build order (vertical slices)

| # | Slice | Done when |
|---|---|---|
| 1 | `api/` skeleton, `/companies`, `/health`, OpenAPI | `uvicorn` serves the stub universe; test passes |
| 2 | Replay engine: stored run to SSE event stream, `Assessment` assembler | One company streams end to end from `data/runs`; contract test on shape |
| 3 | `web/` scaffold, types from OpenAPI, Select and Run screens | Click company, watch stages tick |
| 4 | Verdict screen with real `Assessment` data | Hero, committee cards, evidence chips |
| 5 | Mubit panel + track-record endpoint | Correction story visible per agent |
| 6 | Polish: motion, responsive, empty and error states, stub banner | Walkthrough under 90 seconds |
| 7 | Demo hardening: static build served by FastAPI, one-command start, backup recording | `make demo` works offline |
| 8 | Live mode behind `LIVE=1` (stretch) | Real runner for one cached company |

Tests: API contract tests (shape, no numeric field without an accession or Python source), leakage guard on `as_of`, a smoke test that the SSE stream ends with `done`. Front end: type-check and one Playwright path (select, run, verdict).

## 6. Risks and open points

- **Data is still stubs**: the UI must carry the NOT RESULTS banner until real runs exist; build against the `Assessment` contract so real data drops in.
- **Streamlit stays** as the judge-facing replay/eval view; this UI is the investor-facing one. No shared state beyond the stored runs.
- **Ownership**: `api/` and `web/` are new and sit under B. Anything needing a change in A's files (for example a metrics endpoint) is requested, not edited.
- **Time**: slices 1-5 are the must-ship; 6-8 are cut in order if the freeze gets close. Add this plan to `TASKS.md` and the cut list once agreed.
- **Names**: real names appear only in the API's render-time map, for the demo companies, never in prompts.
