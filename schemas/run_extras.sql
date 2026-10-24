-- Additions to store/schema.sql for what the agents and eval write (Person B).
-- Shared file: tell Person A before changing it. Run after store/schema.sql. Additive only.

-- The synthesizer weights and the no-look-ahead rule both need to know WHEN a grade
-- became visible, so the grade's resolution date is stored, not only its outcome.
ALTER TABLE grades ADD COLUMN IF NOT EXISTS resolution_date DATE;

-- Accuracy and Brier per agent, arm and quarter: the dashboard's accuracy curves.
-- arm: learned | frozen | frontier
CREATE TABLE IF NOT EXISTS snapshots (
  run_id   TEXT NOT NULL REFERENCES runs,
  agent    TEXT NOT NULL,
  arm      TEXT NOT NULL,
  as_of    DATE NOT NULL,
  n        INTEGER NOT NULL,
  accuracy DOUBLE PRECISION,
  brier    DOUBLE PRECISION,
  model    TEXT,
  PRIMARY KEY (run_id, agent, arm, as_of)
);

-- The held-out report (eval/report.py), stored once per held-out run for the dashboard panel.
CREATE TABLE IF NOT EXISTS eval_results (
  run_id       TEXT PRIMARY KEY REFERENCES runs,
  generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  real_results BOOLEAN NOT NULL,
  report       JSONB NOT NULL
);
