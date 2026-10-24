-- Postgres schema (README 4.3). Every visible-in-time table carries a NOT NULL filed/vintage date.
-- Owner: Person A (what the data IS). Person B's ingest loads it. Keep column names stable:
-- they are the contract. All statements are idempotent, so the file can be re-run safely.

CREATE TABLE IF NOT EXISTS companies (
  company_id TEXT PRIMARY KEY CHECK (company_id ~ '^anon_[0-9]{3}$'),  -- 'anon_001'
  cik        TEXT NOT NULL,
  ticker     TEXT NOT NULL,               -- never leaves the store
  name       TEXT NOT NULL,               -- never leaves the store
  sector     TEXT,
  covid_group TEXT CHECK (covid_group IN ('hit','resilient','mixed')),
  held_out   BOOLEAN NOT NULL DEFAULT false,  -- true = never used to learn (README 9)
  sic        TEXT                         -- from SEC submissions
);

-- One row per (concept, period, filing). A restatement is a NEW row, never an update, so the
-- gate in store/queries.py can show what was known at any date. `concept` is OUR key from
-- store/concepts.py; `source_tag` keeps the original us-gaap tag.
CREATE TABLE IF NOT EXISTS facts (
  id            BIGSERIAL PRIMARY KEY,
  company_id    TEXT NOT NULL REFERENCES companies,
  concept       TEXT NOT NULL,
  source_tag    TEXT,
  value         DOUBLE PRECISION NOT NULL,
  unit          TEXT NOT NULL,
  period_start  DATE,                     -- NULL for balance-sheet (instant) facts
  period_end    DATE NOT NULL,
  fiscal_year   INTEGER,
  fiscal_period TEXT,                     -- Q1 Q2 Q3 FY
  form          TEXT NOT NULL,
  accession     TEXT NOT NULL,
  filed_date    DATE NOT NULL
);
-- Idempotent loads: ingest inserts with
--   ON CONFLICT (company_id, concept, unit, period_start_key, period_end, accession) DO NOTHING
-- where period_start_key is the generated column below (a NULL start becomes 0001-01-01),
-- so re-running the load from the raw cache never creates duplicates.
ALTER TABLE facts ADD COLUMN IF NOT EXISTS period_start_key DATE
  GENERATED ALWAYS AS (COALESCE(period_start, DATE '0001-01-01')) STORED;
CREATE UNIQUE INDEX IF NOT EXISTS facts_uniq
  ON facts (company_id, concept, unit, period_start_key, period_end, accession);
CREATE INDEX IF NOT EXISTS facts_lookup ON facts (company_id, concept, filed_date);
CREATE INDEX IF NOT EXISTS facts_period ON facts (company_id, concept, period_end, filed_date);

CREATE TABLE IF NOT EXISTS events (
  id         BIGSERIAL PRIMARY KEY,
  company_id TEXT NOT NULL REFERENCES companies,
  form       TEXT NOT NULL,
  items      TEXT[] NOT NULL DEFAULT '{}',   -- 8-K item codes, e.g. {'4.01'}
  filed_date DATE NOT NULL,
  accession  TEXT NOT NULL,
  text_ref   TEXT,                           -- path or key of the cached filing text
  going_concern_hits INTEGER NOT NULL DEFAULT 0,  -- passages found by the event extractor
  UNIQUE (company_id, accession)
);
CREATE INDEX IF NOT EXISTS events_lookup ON events (company_id, filed_date);

-- Revised series keep one row per vintage. Market rates are never revised: vintage_date = obs_date.
CREATE TABLE IF NOT EXISTS macro (
  id           BIGSERIAL PRIMARY KEY,
  series_id    TEXT NOT NULL,
  value        DOUBLE PRECISION NOT NULL,
  obs_date     DATE NOT NULL,
  vintage_date DATE NOT NULL,
  UNIQUE (series_id, obs_date, vintage_date)
);
CREATE INDEX IF NOT EXISTS macro_lookup ON macro (series_id, vintage_date, obs_date);

CREATE TABLE IF NOT EXISTS prices (       -- context only, never a prediction target
  company_id TEXT NOT NULL REFERENCES companies,
  date       DATE NOT NULL,
  close      DOUBLE PRECISION NOT NULL,
  PRIMARY KEY (company_id, date)
);

CREATE TABLE IF NOT EXISTS runs (
  run_id     TEXT PRIMARY KEY,
  kind       TEXT NOT NULL CHECK (kind IN ('train','heldout')),
  config     JSONB NOT NULL DEFAULT '{}',
  started_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS calls (
  call_id    TEXT PRIMARY KEY,
  run_id     TEXT NOT NULL REFERENCES runs,
  agent      TEXT NOT NULL,
  company_id TEXT NOT NULL REFERENCES companies,
  as_of      DATE NOT NULL,
  payload    JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (run_id, agent, company_id, as_of)   -- a replay never writes the same call twice
);
CREATE INDEX IF NOT EXISTS calls_by_quarter ON calls (run_id, as_of, agent);

CREATE TABLE IF NOT EXISTS grades (
  call_id   TEXT PRIMARY KEY REFERENCES calls,
  graded_at TIMESTAMPTZ NOT NULL,
  outcome   TEXT NOT NULL,
  correct   BOOLEAN,                        -- NULL when outcome = 'unresolvable'
  brier     DOUBLE PRECISION,
  evidence  JSONB NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS corrections (
  correction_id TEXT PRIMARY KEY,
  call_id       TEXT NOT NULL REFERENCES calls,
  agent         TEXT NOT NULL,
  summary       TEXT,
  payload       JSONB NOT NULL,
  mubit_ref     TEXT,
  applied_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS corrections_by_agent ON corrections (agent, applied_at);

-- Written by the replay after each quarter (Person B). The dashboard's accuracy curves read it.
-- `variant` separates the learning agent from its frozen twin (README 8.4).
CREATE TABLE IF NOT EXISTS snapshots (
  run_id     TEXT NOT NULL REFERENCES runs,
  agent      TEXT NOT NULL,
  variant    TEXT NOT NULL CHECK (variant IN ('learned','frozen','baseline')),
  as_of      DATE NOT NULL,
  n_calls    INTEGER NOT NULL,
  n_correct  INTEGER NOT NULL,
  accuracy   DOUBLE PRECISION,
  brier      DOUBLE PRECISION,
  model      TEXT,                          -- model version in force that quarter
  PRIMARY KEY (run_id, agent, variant, as_of)
);
