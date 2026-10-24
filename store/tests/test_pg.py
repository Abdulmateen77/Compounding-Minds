"""Database tests: real Postgres, real SQL. Skipped automatically when no Postgres is reachable."""
import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from ingest import pipeline
from store import db, queries
from store.pg import PostgresBackend
from store.quality import coverage, drop_candidates

FIX = Path(__file__).resolve().parents[2] / "ingest" / "tests" / "fixtures"
CIK = "1234567"


@pytest.fixture
def cache(tmp_path):
    (tmp_path / "sec" / "companyfacts").mkdir(parents=True)
    (tmp_path / "sec" / "submissions").mkdir(parents=True)
    (tmp_path / "fred").mkdir()
    shutil.copy(FIX / "companyfacts_sample.json", pipeline.companyfacts_path(CIK, tmp_path))
    shutil.copy(FIX / "submissions_sample.json", pipeline.submissions_path(CIK, tmp_path))
    shutil.copy(FIX / "fred_gdp_sample.json", pipeline.fred_path("GDPC1", tmp_path))
    shutil.copy(FIX / "fred_t10y2y_sample.json", pipeline.fred_path("T10Y2Y", tmp_path))
    return tmp_path


@pytest.fixture
def loaded(pg_conn, cache):
    db.upsert_companies(pg_conn, [dict(company_id="anon_007", cik=CIK, ticker="SMPL", name="Sample Corp")])
    report = pipeline.load_company(pg_conn, "anon_007", CIK, cache)
    pipeline.load_macro(pg_conn, cache)
    queries.set_backend(PostgresBackend(pg_conn))
    yield report
    queries.set_backend(queries.InMemoryBackend())


def test_schema_applies_twice(pg_conn):
    db.apply_schema(pg_conn)  # already applied by the fixture: must be a no-op


def test_loading_is_idempotent(pg_conn, cache, loaded):
    n = lambda t: pg_conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]  # noqa: E731
    before = (n("facts"), n("events"), n("macro"))
    again = pipeline.load_company(pg_conn, "anon_007", CIK, cache)
    pipeline.load_macro(pg_conn, cache)
    assert (n("facts"), n("events"), n("macro")) == before
    assert again["facts_rows"] == loaded["facts_rows"] > 0


def test_missing_raw_files_are_reported_not_raised(pg_conn, tmp_path):
    db.upsert_companies(pg_conn, [dict(company_id="anon_009", cik="999", ticker="X", name="X")])
    r = pipeline.load_company(pg_conn, "anon_009", "999", tmp_path)
    assert len(r["missing"]) == 2 and r["facts_rows"] == 0


def test_load_report_counts(loaded):
    assert loaded["facts_rows"] == 8 and loaded["events_rows"] == 4


def test_a_missing_older_submissions_page_is_reported(pg_conn, cache):
    db.upsert_companies(pg_conn, [dict(company_id="anon_007", cik=CIK, ticker="SMPL", name="Sample Corp")])
    r = pipeline.load_company(pg_conn, "anon_007", CIK, cache)
    assert any("submissions-001" in m for m in r["missing"])


def test_sic_and_going_concern_default_are_stored(pg_conn, loaded):
    assert pg_conn.execute("SELECT sic FROM companies WHERE company_id='anon_007'").fetchone()[0] == "3571"
    assert pg_conn.execute("SELECT max(going_concern_hits) FROM events").fetchone()[0] == 0


def test_gate_through_postgres_hides_a_restatement_until_it_is_filed(loaded):
    def revenue_2017(t):
        rows = queries.get_facts("anon_007", "revenue", t)
        return [f.value for f in rows if f.period_end == date(2017, 12, 31)]
    assert revenue_2017(date(2019, 2, 13)) == [1000.0]   # original
    assert revenue_2017(date(2019, 2, 14)) == [1010.0]   # restated, filed 2019-02-14
    assert revenue_2017(date(2018, 2, 14)) == []          # nothing filed yet


def test_gate_through_postgres_returns_3m_and_6m_durations(loaded):
    got = {(f.period_start, f.value) for f in queries.get_facts("anon_007", "operating_income", date(2018, 8, 1))}
    assert got == {(date(2018, 4, 1), 40.0), (date(2018, 1, 1), 75.0)}


def test_gate_through_postgres_events_and_macro(loaded):
    assert [e.items for e in queries.get_events("anon_007", date(2019, 3, 1), forms=["8-K"])] == [["4.01", "9.01"]]
    assert queries.get_events("anon_007", date(2019, 2, 28), forms=["8-K"]) == []
    # GDP: the 2019-05-30 revision is invisible a day earlier
    assert queries.get_macro("GDPC1", date(2019, 5, 29))[0].value == 18927.3
    assert queries.get_macro("GDPC1", date(2019, 5, 30))[0].value == 18950.3


def test_no_row_visible_before_it_was_filed(loaded):
    for t in (date(2018, 3, 1), date(2018, 8, 1), date(2019, 3, 1)):
        for concept in ("revenue", "operating_income", "op_cash_flow", "current_assets"):
            assert all(f.filed_date <= t for f in queries.get_facts("anon_007", concept, t))


def test_company_loader_resolves_ciks_and_reports_unresolved(pg_conn):
    r = pipeline.load_companies(pg_conn, {"AAPL": "0000320193"})
    assert r["loaded"] == 1 and len(r["unresolved_tickers"]) == 49
    cik, held = pg_conn.execute("SELECT cik, held_out FROM companies").fetchone()
    assert cik == "320193" and held is False


def test_coverage_flags_a_company_missing_required_concepts(pg_conn, loaded):
    rep = {r["company_id"]: r for r in coverage(pg_conn)}["anon_007"]
    assert "capex" in rep["missing_required"] and not rep["ok"]
    assert "anon_007" in drop_candidates(coverage(pg_conn))
