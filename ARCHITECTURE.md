# Architecture: Compounding Minds

Multi-agent design, data flow and the reasoning behind both. Companions: [PROJECT.md](PROJECT.md) (overview), [README.md](README.md) (full spec and schemas), [CLAUDE.md](CLAUDE.md) (rules).

---

## 1. Pattern summary

> **Fan-out/fan-in committee over a shared-state blackboard, with an external-verifier reflection loop.**

| Pattern | Role in this system | Status |
|---|---|---|
| **Parallel / Fan-Out–Fan-In** | Specialist agents run independently on the same input. The synthesizer aggregates their calls. | **Core** |
| **Shared Blackboard / Shared State** | Postgres is the only coordination channel. Agents never message each other. | Core |
| **Critic–Refiner / Reflection** | Python grader (external verifier) scores calls, a reflection LLM writes a lesson, Mubit updates the agent that erred. | Core (the learning mechanism) |
| **Sequential / Pipeline** | The replay loop runs call, grade, correct, update, snapshot, once per quarter. This is deterministic code, not agents. | Core (control flow) |
| **Debate / Consensus** | One optional cross-examination round before synthesis. | Stretch |

### Deliberately not used
| Pattern | Why not |
|---|---|
| Supervisor / LLM orchestrator | The orchestrator is plain code that always runs the same agents in the same order. This keeps replays deterministic and leakage-safe. |
| Hierarchical, Router, Planner–Executor–Evaluator | No manager agents, routing or LLM-generated plans. Fixed `question_id`s are what make calls gradable. |
| Peer-to-peer | Agents see no peer output before they commit. Independence preserves diversity and makes attribution per agent possible. |
| LLM-as-judge | The grader must stay objective and non-LLM. Ground truth from filings is the project's strongest asset. |

---

## 2. System diagram

```
            SEC EDGAR / FRED / prices
                      |
                 [ingest/]  --one-off, cached-->  [store/ Postgres]   <-- shared state (blackboard)
                                                      |
                                       store/queries.py  (only gate: filed_date <= as_of)
                                                      |
                 +------------------------------------+-----------------+
                 |                                                      |
          [metrics/] Python computes ALL numbers                  [tools/] MCP servers (read-only)
                 |                                                      |
                 +--------------------> FAN-OUT <------------------------+
                                           |
        +------------+------------+--------+-----+------------+
        |            |            |              |            |
   Fundamentals     Risk      Scenarios      Valuation       Moat        (parallel, independent,
   (Buffett)      (Munger)     (Dalio)       (Graham)     (Buffett)       no peer visibility)
        |            |            |              |            |
        +------------+------------+--------+-----+------------+
                                           |
                          (optional) cross-examination, max 1 round
                                           |
                                        FAN-IN
                              [Synthesizer: weighted verdict]
                       weights = trailing Brier from grades (Python)
                                           |
   [replay orchestrator] --sets as_of--> calls written to Postgres
                                           |
                          [grader/]  external verifier, pure Python
                                           |
                                    Grade + Correction
                                           |
                       reflection LLM call (lesson text)
                                           |
                       ModelUpdater -> Mubit (per-agent update)
                                           |
                                    [dashboard/]
```

---

## 3. Components and responsibilities

| Component | Type | Responsibility | Never does |
|---|---|---|---|
| Replay orchestrator | Deterministic code | Advance quarter, set `as_of`, dispatch agents, trigger grading and updates | Decide anything with an LLM |
| Specialist agents | LLM + bounded tools | Judge pre-computed metrics against investor principles, emit one fixed-schema `AgentCall` | Compute numbers, see peers' calls, query tables directly |
| Metrics engine | Python | Compute every number with accession traceability | Call an LLM |
| MCP tools | Read-only servers | Drill-down (metric series, events, macro snapshot, peer compare), capped at about 5 calls per run | Bypass `store/queries.py` |
| Synthesizer | Python weights + LLM rationale | Combine calls into a verdict, with weights from `grades` | Let an LLM set weights or confidence |
| Reality grader | Pure Python | Resolve each `question_id` from later filings, compute Brier | Use an LLM, guess on missing data |
| Correction maker | Python + reflection LLM | Select corrections (rate-limited), write lesson text | Name companies in lessons |
| ModelUpdater | Mubit client / fallback | Submit corrections per agent, expose model version | Leak lessons across agents |
| Store gate | `store/queries.py` | Enforce `filed_date <= as_of` | Filter by `period_end` |

---

## 4. Data and control flow (one quarter)

1. Orchestrator sets `as_of = t`.
2. For each company, `get_metrics(company, agent, t)` builds each agent's metric bundle.
3. **Fan-out:** agents run in parallel, each with its principles file, its metrics and at most 5 tool calls. Each writes an `AgentCall` row.
4. **Fan-in:** the synthesizer reads the calls, weights them using `get_track_record(agent, t)` and writes a verdict.
5. Grader scans calls whose resolution filing is now visible (`resolution_date <= t`) and writes `Grade` rows.
6. Correction maker selects wrong calls (capped per agent per quarter) and writes `Correction` rows, with lessons from the reflection call.
7. `ModelUpdater.submit_corrections(agent, corrections)` updates each erring agent. Training-window corrections only.
8. Orchestrator snapshots accuracy and Brier per agent for the dashboard, then advances to `t + 1 quarter`.

The loop never learns from the future: a call is graded and corrected only once its resolution filing is visible at the current `as_of`.

---

## 5. Shared state (blackboard)

Postgres tables are the only channel between components.

| Table | Written by | Read by |
|---|---|---|
| `facts`, `events`, `macro`, `prices` | ingest | store gate, metrics |
| `calls` | agents, synthesizer | grader, dashboard, synthesizer weights |
| `grades` | grader | correction maker, calibration, dashboard |
| `corrections` | correction maker | ModelUpdater, dashboard |
| `runs` | orchestrator | eval, dashboard |

Agents read state only through `store/queries.py` and the metrics engine. They write only their own `AgentCall`.

---

## 6. The learning loop (reflection with external reward)

```
act (AgentCall) -> verify (Python grader vs filings) -> reflect (lesson) -> update (Mubit, per agent) -> act again
```

What makes it different from typical LLM self-critique:
- **The verifier is not an LLM.** It uses filed numbers.
- **The reward is delayed and objective.** It arrives with the next filing.
- **Learning persists.** Lessons change the agent's model (Mubit) or principles and few-shot memory (`FakeModelUpdater`).
- **Updates are per agent.** An error attributes to one agent and one set of principles (`principle_refs`).

Safeguards:
- Cap N corrections per agent per quarter, prioritised by confidence of the wrong call.
- Learn only from the train window (2018 to 2022).
- Keep a frozen twin of each agent as a control.
- Lessons must reference a principle or metric, never a company name.

---

## 7. Independence and diversity rules

- No agent sees another agent's output before committing its call.
- Each agent has its own principles file, metric set and Mubit identity.
- The cross-examination round (stretch) runs after independent calls are stored, once, and may revise confidence but not the stored original call.
- Synthesizer weights come from trailing grades, recomputed each quarter.

---

## 8. Integrity constraints on the architecture

| Constraint | Enforced by |
|---|---|
| No look-ahead | Single gate `store/queries.py`, leakage test, anonymised IDs, relative quarter labels |
| No LLM numbers | Metrics engine in Python, `evidence` checked against engine output at parse time |
| Gradable calls | Fixed `question_id`s and Pydantic `AgentCall` schema, one repair retry then drop |
| Reproducible replay | Temperature 0, fixed seeds, response cache keyed by prompt hash |
| Mubit routing | One `LLMGateway`, one adapter per agent |
| Demo safety | Replay precomputed offline, dashboard reads Postgres only, `FakeModelUpdater` fallback labelled in the UI |

---

## 9. Extension points

| Extension | Where it plugs in |
|---|---|
| New agent (Valuation, Moat) | Add a question ID, metric set, principles file and adapter. Joins the fan-out with no other change. |
| Cross-examination | Optional step between fan-out and fan-in |
| Screener (`screener/`) | Reads metrics and `calls`, writes ranked flags |
| Memos (`memos/`) | Reads metrics, calls, events, writes memo text with placeholder-filled numbers |
| Calibration (`grader/calibration.py`) | Reads `grades`, feeds synthesizer weights and the dashboard |
| Analyst-submitted calls | Same `AgentCall` shape with `agent = "analyst:<id>"`, graded by the same grader |
| Analyst overrides | Stored as `Correction` records with a human source |

---

## 10. Failure modes

| Failure | Handling |
|---|---|
| Agent returns invalid JSON | One repair retry, then drop and log the call |
| Evidence does not match metrics engine | Reject the call at parse time |
| Resolution filing missing | Grade as `unresolvable`, excluded from accuracy, logged |
| Mubit API late or down | Switch to `FakeModelUpdater`, labelled as fallback in the UI |
| Corrections flood a quarter | Per-agent cap, prioritised by confidence |
| Accuracy does not improve | Report honestly, with calibration and frozen-twin comparison |

---

*Research tool, not financial advice.*
