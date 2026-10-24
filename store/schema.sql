-- Postgres schema (README 4.3). Every visible-in-time table carries a NOT NULL filed/vintage date.
CREATE TABLE IF NOT EXISTS companies (
  company_id TEXT PRIMARY KEY,            -- 'anon_001'
  cik        TEXT NOT NULL,
  ticker     TEXT NOT NULL,               -- never leaves the store
  name       TEXT NOT NULL,               -- never leaves the store
  sector     TEXT
);

CREATE TABLE IF NOT EXISTS facts (
  id            BIGSERIAL PRIMARY KEY,
  company_id    TEXT NOT NULL REFERENCES companies,
  concept       TEXT NOT NULL,
  value         DOUBLE PRECISION NOT NULL,
  unit          TEXT NOT NULL,
  period_start  DATE,
  period_end    DATE NOT NULL,
  fiscal_period TEXT,
  form          TEXT NOT NULL,
  accession     TEXT NOT NULL,
  filed_date    DATE NOT NULL
);
CREATE INDEX IF NOT EXISTS facts_lookup ON facts (company_id, concept, filed_date);

CREATE TABLE IF NOT EXISTS events (
  id         BIGSERIAL PRIMARY KEY,
  company_id TEXT NOT NULL REFERENCES companies,
  form       TEXT NOT NULL,
  items      TEXT[] NOT NULL DEFAULT '{}',
  filed_date DATE NOT NULL,
  accession  TEXT NOT NULL,
  text_ref   TEXT
);
CREATE INDEX IF NOT EXISTS events_lookup ON events (company_id, filed_date);

CREATE TABLE IF NOT EXISTS macro (
  id           BIGSERIAL PRIMARY KEY,
  series_id    TEXT NOT NULL,
  value        DOUBLE PRECISION NOT NULL,
  obs_date     DATE NOT NULL,
  vintage_date DATE NOT NULL
);

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
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS grades (
  call_id   TEXT PRIMARY KEY REFERENCES calls,
  graded_at TIMESTAMPTZ NOT NULL,
  outcome   TEXT NOT NULL,
  correct   BOOLEAN,
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
