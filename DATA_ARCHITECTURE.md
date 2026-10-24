# Data Architecture: Compounding Minds

The whole system in diagrams, from raw data to the dashboard. Diagrams use Mermaid, so they render on GitHub and in the VS Code Markdown preview.

Companions: [ARCHITECTURE.md](ARCHITECTURE.md) (pattern and reasoning), [README.md](README.md) (full spec and schemas), [PROJECT.md](PROJECT.md) (overview).

**How to read the colours**

| Colour | Meaning |
|---|---|
| Blue | Python code. Deterministic. Produces every number |
| Orange | LLM step, always routed through Mubit |
| Green | Postgres tables (shared state) |
| Grey | External source |
| Purple | What the user sees |

---

## 1. The whole picture

```mermaid
flowchart LR
    classDef src fill:#eceff1,stroke:#607d8b,color:#263238
    classDef py fill:#e3f2fd,stroke:#1e88e5,color:#0d47a1
    classDef llm fill:#fff3e0,stroke:#fb8c00,color:#e65100
    classDef db fill:#e8f5e9,stroke:#43a047,color:#1b5e20
    classDef ui fill:#f3e5f5,stroke:#8e24aa,color:#4a148c

    subgraph S1["1. Sources"]
        SEC["SEC EDGAR<br/>XBRL facts, filings, 8-K items"]:::src
        MAC["FRED / ALFRED<br/>macro vintages"]:::src
        PRC["Stooq / Tiingo<br/>prices, context only"]:::src
        WEB["Firecrawl, stretch<br/>press releases, FOMC"]:::src
    end

    subgraph S2["2. Ingest, run once"]
        ING["ingest/<br/>fetch, cache raw, parse"]:::py
    end

    subgraph S3["3. Store"]
        DB[("Postgres<br/>facts, events, macro,<br/>every row has filed_date")]:::db
        GATE["store/queries.py<br/>THE gate: filed_date <= as_of"]:::py
    end

    subgraph S4["4. Numbers"]
        MET["metrics/<br/>Python computes every number,<br/>each traced to filings"]:::py
    end

    subgraph S5["5. Run one quarter"]
        ORC["Replay orchestrator<br/>plain code, sets as_of"]:::py
        AG["Specialist agents<br/>judge metrics, fixed JSON out"]:::llm
        SYN["Synthesizer<br/>committee verdict"]:::llm
    end

    subgraph S6["6. Learn"]
        GR["Reality grader<br/>pure Python vs later filings"]:::py
        COR["Correction maker<br/>plus reflection lesson"]:::llm
        MUB["Mubit<br/>per-agent model update"]:::llm
    end

    subgraph S7["7. Show"]
        OUT[("calls, grades,<br/>corrections, snapshots")]:::db
        DASH["Dashboard<br/>replay, curves, spotlight"]:::ui
        REP["Final report<br/>verdict plus memo"]:::ui
    end

    SEC --> ING
    MAC --> ING
    PRC --> ING
    WEB --> ING
    ING --> DB
    DB --> GATE
    GATE --> MET
    MET --> ORC
    ORC --> AG
    AG --> SYN
    SYN --> OUT
    AG --> OUT
    OUT --> GR
    GR --> COR
    COR --> MUB
    MUB -.->|"new model version"| AG
    OUT --> DASH
    OUT --> REP
```

One sentence: data goes in once, passes a single date gate, becomes numbers, becomes calls, gets graded against reality, and the misses retrain the agents.

---

## 2. Data pipeline: sources to the store

Runs **once, before the demo**. Raw responses are cached on disk before parsing, so a re-run never hits the network.

```mermaid
flowchart TB
    classDef src fill:#eceff1,stroke:#607d8b,color:#263238
    classDef py fill:#e3f2fd,stroke:#1e88e5,color:#0d47a1
    classDef db fill:#e8f5e9,stroke:#43a047,color:#1b5e20

    subgraph SRC["External sources"]
        A1["company_tickers.json"]:::src
        A2["XBRL companyfacts"]:::src
        A3["submissions: 8-K items, SIC"]:::src
        A4["Filing text: 10-K, 10-Q"]:::src
        A5["EDGAR full-text search"]:::src
        A6["ALFRED vintages"]:::src
        A7["Stooq prices"]:::src
        A8["8-K Ex. 99.1, FOMC, Wayback<br/>via Firecrawl, stretch"]:::src
    end

    RAW[("Raw cache on disk<br/>never re-fetched")]:::db

    subgraph PARSE["ingest/ : parse and normalise"]
        P1["Universe builder<br/>~50 companies, anon_001..050"]:::py
        P2["Concept mapper<br/>fixed XBRL concept map"]:::py
        P3["Event extractor<br/>8-K item codes, going-concern hits"]:::py
        P4["Macro loader<br/>keeps vintage_date"]:::py
    end

    subgraph TBL["Postgres tables"]
        T1[("companies")]:::db
        T2[("facts<br/>filed_date NOT NULL")]:::db
        T3[("events<br/>filed_date NOT NULL")]:::db
        T4[("macro<br/>vintage_date NOT NULL")]:::db
        T5[("prices, context only")]:::db
    end

    A1 --> RAW
    A2 --> RAW
    A3 --> RAW
    A4 --> RAW
    A5 --> RAW
    A6 --> RAW
    A7 --> RAW
    A8 --> RAW
    RAW --> P1
    RAW --> P2
    RAW --> P3
    RAW --> P4
    P1 --> T1
    P2 --> T2
    P3 --> T3
    P4 --> T4
    RAW --> T5

    T2 --> GATE
    T3 --> GATE
    T4 --> GATE
    GATE["store/queries.py<br/>only door into the tables"]:::py
    GATE --> OUT["get_facts, get_events,<br/>get_macro, get_metrics"]:::py
```

**Rules on this pipeline**

| Rule | Why |
|---|---|
| Every row carries `filed_date` (macro: `vintage_date`) | Lets the gate hide the future |
| A restatement is a new row, never an overwrite | At date `t` we return what was known at `t` |
| Nobody queries tables except `store/queries.py` | One place to test for leakage |
| Names and tickers stay in `companies` | Agents only ever see `anon_007` |
| Firecrawl output is dated pages only, no numbers | Numbers come from XBRL, never from an LLM |

---

## 3. Orchestrator: one quarter, step by step

The orchestrator is plain code. It always runs the same steps in the same order, which keeps replays deterministic.

```mermaid
sequenceDiagram
    autonumber
    participant O as Orchestrator
    participant G as Store gate
    participant M as Metrics engine
    participant A as Agents (parallel)
    participant S as Synthesizer
    participant D as Postgres
    participant R as Grader
    participant C as Correction maker
    participant U as Mubit
    participant UI as Dashboard

    O->>O: set as_of = t (quarter end)
    loop each company
        O->>M: get_metrics(company, agent, t)
        M->>G: get_facts / get_events / get_macro (t)
        G-->>M: rows with filed_date <= t only
        M-->>O: metric bundle per agent, with accessions
        O->>A: dispatch bundle (fan-out)
        A-->>D: write AgentCall per agent
        O->>S: read calls and track record
        S-->>D: write committee verdict
    end
    O->>R: grade calls whose resolution filing is now visible
    R->>G: read filings after as_of
    R-->>D: write Grade (outcome, Brier)
    O->>C: pick wrong calls (cap per agent)
    C->>U: reflection call, writes lesson
    C-->>D: write Correction
    C->>U: submit_corrections (train window only)
    U-->>O: new model version per agent
    O->>D: snapshot accuracy and Brier
    D-->>UI: dashboard reads the snapshot
    O->>O: advance to t + 1 quarter
```

**Hard guarantee:** a call is graded and corrected only once its resolution filing is visible at the current `as_of`. The loop never learns from the future.

---

## 4. Passing data to the agents

```mermaid
flowchart TB
    classDef py fill:#e3f2fd,stroke:#1e88e5,color:#0d47a1
    classDef llm fill:#fff3e0,stroke:#fb8c00,color:#e65100
    classDef db fill:#e8f5e9,stroke:#43a047,color:#1b5e20

    ORC["Orchestrator<br/>company_id = anon_007, as_of = t"]:::py
    MET["Metrics engine"]:::py

    ORC --> MET
    MET -->|"Fundamentals bundle"| F["Fundamentals<br/>Buffett"]:::llm
    MET -->|"Risk bundle"| R["Risk<br/>Munger"]:::llm
    MET -->|"Scenarios bundle"| SC["Scenarios<br/>Dalio"]:::llm
    MET -.->|"stretch"| V["Valuation<br/>Graham"]:::llm
    MET -.->|"stretch"| MO["Moat<br/>Buffett"]:::llm

    F --> CALLS
    R --> CALLS
    SC --> CALLS
    V -.-> CALLS
    MO -.-> CALLS

    CALLS[("calls table<br/>one AgentCall each")]:::db
    CALLS --> SYN["Synthesizer<br/>weights from track record"]:::llm
    SYN --> VERD[("committee verdict<br/>plus confidence")]:::db
```

Agents are **independent**: none sees another agent's call before committing. That keeps errors attributable to one agent and one set of principles.

---

## 5. Inside one agent: resources, work, output

```mermaid
flowchart LR
    classDef py fill:#e3f2fd,stroke:#1e88e5,color:#0d47a1
    classDef llm fill:#fff3e0,stroke:#fb8c00,color:#e65100
    classDef db fill:#e8f5e9,stroke:#43a047,color:#1b5e20
    classDef res fill:#fffde7,stroke:#fbc02d,color:#5d4037

    subgraph IN["Resources the agent gets"]
        P["principles/investor.md<br/>5-10 rules, own words"]:::res
        B["Metric bundle<br/>numbers with accessions"]:::res
        T["MCP tools, read only, max ~5<br/>metric series, events,<br/>macro snapshot, peer compare"]:::res
        L["Lessons from past corrections<br/>via model version"]:::res
    end

    subgraph WORK["What it does"]
        PR["Prompt: anon ID, relative quarters<br/>Q-8 to Q0, no names or dates"]:::py
        GW["LLMGateway to Mubit<br/>agent-specific model"]:::llm
        J["Judge: apply rules to numbers,<br/>pick answer plus probability"]:::llm
    end

    subgraph OUT["How it produces output"]
        JS["AgentCall JSON<br/>fixed schema"]:::py
        V1{"Valid schema?"}:::py
        V2{"Evidence matches<br/>metrics engine?"}:::py
        RT["One repair retry"]:::py
        DR["Drop and log"]:::py
        W[("calls table")]:::db
    end

    P --> PR
    B --> PR
    L --> GW
    PR --> GW
    T <--> J
    GW --> J
    J --> JS
    JS --> V1
    V1 -- yes --> V2
    V1 -- no --> RT
    RT --> V1
    RT -. "still bad" .-> DR
    V2 -- yes --> W
    V2 -- no --> DR
```

**What each agent has and does**

| Agent | Investor | Metrics it receives | Question it answers | Graded against |
|---|---|---|---|---|
| Fundamentals | Buffett | FCF, margins, ROIC, debt/EBITDA, 8-quarter slope | Do FCF margin and operating margin both improve next quarter? | Next 10-Q or 10-K |
| Risk | Munger | Interest coverage, current ratio, cash runway, dividends, auditor history, going-concern hits | Auditor change, dividend cut or going-concern note within 12 months? | 8-K items, XBRL dividends, 10-K text |
| Scenarios | Dalio | 5-year revenue growth distribution, cyclicality, macro regime | Bull, base or bear revenue over the next 4 quarters? | Actual revenue growth |
| Valuation (stretch) | Graham | Reverse-DCF implied growth, owner earnings yield | Is implied growth above what was delivered? | Revenue growth next year |
| Moat (stretch) | Buffett | Gross margin level and spread, R&D and SG&A intensity | Does gross margin hold within ±2 points for 4 quarters? | Next 4 filings |
| Synthesizer | Committee | Other agents' calls and their track record | Attractive, neutral or unattractive business outlook | Composite of graded outcomes |

Every agent: **judges, never computes.** All numbers arrive pre-computed from Python.

---

## 6. Grading, learning and the Mubit update

```mermaid
flowchart LR
    classDef py fill:#e3f2fd,stroke:#1e88e5,color:#0d47a1
    classDef llm fill:#fff3e0,stroke:#fb8c00,color:#e65100
    classDef db fill:#e8f5e9,stroke:#43a047,color:#1b5e20
    classDef ui fill:#f3e5f5,stroke:#8e24aa,color:#4a148c

    CALL[("AgentCall<br/>answer plus probability")]:::db
    FIL[("Later filings<br/>filed_date after as_of")]:::db

    CALL --> GR
    FIL --> GR
    GR["Reality grader<br/>rules.py, pure Python<br/>no LLM"]:::py
    GR --> GRADE[("Grade<br/>outcome, correct, Brier")]:::db
    GRADE --> OK{"Correct?"}:::py

    OK -- yes --> TRK["Track record<br/>accuracy, calibration"]:::py
    OK -- no --> CAP["Cap per agent per quarter<br/>rank by confidence"]:::py
    CAP --> REF["Reflection call<br/>writes the lesson"]:::llm
    REF --> COR[("Correction<br/>error type, lesson, principle refs")]:::db
    COR --> UPD["ModelUpdater<br/>submit_corrections"]:::llm
    UPD --> MUB["Mubit<br/>update that agent only"]:::llm
    MUB --> VER["New model version"]:::llm
    VER -.->|"used in next quarter's calls"| CALL

    TRK --> SYNW["Synthesizer weights"]:::py
    GRADE --> SNAP[("Quarterly snapshot")]:::db
    COR --> SPOT["Correction spotlight"]:::ui
    SNAP --> CURVE["Accuracy curves"]:::ui
```

**Safeguards**
- The grader is not an LLM. It uses filed numbers.
- Corrections come from the **train window only** (2018 to 2022).
- Each learning agent has a **frozen twin** as a control.
- Lessons cite a principle or metric, never a company name.
- If Mubit is unavailable, `FakeModelUpdater` takes over and the UI labels it as a fallback.

---

## 7. Output: final report and dashboard

```mermaid
flowchart TB
    classDef db fill:#e8f5e9,stroke:#43a047,color:#1b5e20
    classDef py fill:#e3f2fd,stroke:#1e88e5,color:#0d47a1
    classDef llm fill:#fff3e0,stroke:#fb8c00,color:#e65100
    classDef ui fill:#f3e5f5,stroke:#8e24aa,color:#4a148c

    subgraph STORE["Everything lives in Postgres"]
        C[("calls")]:::db
        V[("committee verdicts")]:::db
        G[("grades")]:::db
        K[("corrections")]:::db
        SN[("snapshots")]:::db
        EV[("eval results<br/>frozen vs learned vs baselines")]:::db
    end

    subgraph REPORT["Final report, per company and quarter"]
        R1["Verdict plus confidence"]:::ui
        R2["Each agent's call and reasoning"]:::ui
        R3["Metric table, rendered by Python<br/>with source accessions"]:::ui
        R4["Memo prose, stretch<br/>numbers only via placeholders"]:::llm
    end

    subgraph DASH["Dashboard, reads Postgres only"]
        D1["Replay timeline<br/>2018Q1 to 2024Q4"]:::ui
        D2["Accuracy curves<br/>learned vs frozen, COVID shaded"]:::ui
        D3["Committee table"]:::ui
        D4["Correction spotlight<br/>call, actual, lesson, Mubit update"]:::ui
        D5["Held-out panel"]:::ui
        D6["Stretch: watchlist, memo, track record"]:::ui
    end

    V --> R1
    C --> R2
    C --> R3
    R3 --> R4

    SN --> D1
    SN --> D2
    C --> D3
    V --> D3
    G --> D4
    K --> D4
    EV --> D5
    R4 --> D6
    R1 --> D3
    FOOT["Footer on every view:<br/>Research tool, not financial advice"]:::ui
    DASH --- FOOT
```

**Rules on output**
- The dashboard never calls a live API. It reads what the replay already stored.
- Every number in a report comes from the metrics engine. In memos the LLM writes prose around `{{metric:name}}` placeholders that Python fills, and a post-check rejects any other number.
- Names and tickers are mapped back only at render time, and only for the demo company.

---

## 8. Who builds which box

| Diagram section | Owner |
|---|---|
| 2. Ingest (fetch, cache, parse) | B |
| 2. Schema, concept map, store gate | A |
| 3. Orchestrator and replay | B |
| 4-5. Agents, principles, adapters | A |
| 6. Grader and correction selection | B |
| 6. Reflection prompt wording, Mubit client | A |
| 6. ModelUpdater calls, correction loop | B |
| 7. Dashboard | B |
| Held-out eval and baselines | A |

See [TASKS.md](TASKS.md) for the hour-by-hour split.

---

*Research tool, not financial advice.*
