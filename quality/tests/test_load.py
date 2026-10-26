"""load_scored against a real Postgres. Skipped automatically when none is reachable (conftest pg_conn)."""
from __future__ import annotations

from datetime import date

import pytest

from quality.load import load_scored, resolution_date_of
from quality.tests.helpers import make_call, make_scored
from store import db

psycopg = pytest.importorskip("psycopg")
from psycopg.types.json import Jsonb  # noqa: E402


def insert(conn, run_id, variant, scored):
    cfg = {} if variant is None else {"variant": variant}
    conn.execute("INSERT INTO runs (run_id, kind, config) VALUES (%s, 'train', %s) ON CONFLICT DO NOTHING",
                 (run_id, Jsonb(cfg)))
    c, g = scored.call, scored.grade
    conn.execute("INSERT INTO calls (call_id, run_id, agent, company_id, as_of, payload) VALUES (%s,%s,%s,%s,%s,%s)",
                 (c.call_id, run_id, c.agent, c.company_id, c.as_of, Jsonb(c.model_dump(mode="json"))))
    conn.execute("INSERT INTO grades (call_id, graded_at, outcome, correct, brier, evidence) VALUES (%s,%s,%s,%s,%s,%s)",
                 (c.call_id, g.graded_at, g.outcome, g.correct, g.brier, Jsonb(g.evidence)))
    conn.commit()


@pytest.fixture
def loaded(pg_conn):
    db.upsert_companies(pg_conn, [dict(company_id=f"anon_00{i}", cik=str(i), ticker=f"T{i}", name=f"Name {i}")
                                  for i in (1, 2, 3)])
    pg_conn.commit()
    rows = {
        "learned_default": make_scored("yes", company="anon_001", as_of=date(2019, 6, 30), resolution=date(2019, 9, 30)),
        "frozen": make_scored("no", company="anon_002", as_of=date(2023, 3, 31), resolution=date(2023, 6, 30), answer="yes"),
        "unresolvable": make_scored("unresolvable", company="anon_003", as_of=date(2020, 3, 31), resolution=None),
    }
    insert(pg_conn, "run-a", None, rows["learned_default"])         # no variant in config -> learned
    insert(pg_conn, "run-b", "frozen", rows["frozen"])
    insert(pg_conn, "run-a", None, rows["unresolvable"])
    return rows


def test_load_returns_every_graded_call_with_the_variant_from_run_config(loaded, pg_conn):
    got = {s.call.call_id: s for s in load_scored(pg_conn)}
    assert set(got) == {r.call.call_id for r in loaded.values()}
    assert got[loaded["learned_default"].call.call_id].variant == "learned"     # the default
    assert got[loaded["frozen"].call.call_id].variant == "frozen"


def test_load_rebuilds_the_call_and_grade_faithfully(loaded, pg_conn):
    want = loaded["frozen"]
    got = next(s for s in load_scored(pg_conn) if s.call.call_id == want.call.call_id)
    assert got.call == want.call
    assert (got.grade.outcome, got.grade.correct) == (want.grade.outcome, want.grade.correct)
    assert got.grade.brier == pytest.approx(want.grade.brier)
    assert got.grade.resolution_date == date(2023, 6, 30)       # read back from grades.evidence


def test_unresolvable_grades_are_loaded_so_they_can_be_counted(loaded, pg_conn):
    got = {s.call.call_id: s for s in load_scored(pg_conn)}
    u = got[loaded["unresolvable"].call.call_id]
    assert u.grade.outcome == "unresolvable" and u.grade.correct is None and u.grade.brier is None
    assert u.grade.resolution_date is None                      # none was recorded


def test_load_can_be_limited_to_some_runs(loaded, pg_conn):
    only_b = load_scored(pg_conn, run_ids=["run-b"])
    assert [s.variant for s in only_b] == ["frozen"]
    assert len(load_scored(pg_conn, run_ids=["run-a"])) == 2
    assert load_scored(pg_conn, run_ids=["no-such-run"]) == []


def test_an_empty_database_loads_nothing(pg_conn):
    assert load_scored(pg_conn) == []


def test_the_loaded_records_feed_the_report(loaded, pg_conn):
    from quality.report import build_heldout

    h = build_heldout(load_scored(pg_conn), {"anon_002"})
    assert set(h["agents"]) == {"fundamentals"}
    assert h["agents"]["fundamentals"]["unresolvable"] == 1


def test_resolution_date_is_read_from_the_graders_evidence_shape():
    assert resolution_date_of([{"rule": "x", "resolution_date": "2020-06-30"}]) == date(2020, 6, 30)
    assert resolution_date_of([{"stub": True}]) is None
    assert resolution_date_of([]) is None and resolution_date_of(None) is None
    assert resolution_date_of(["not a dict"]) is None
    assert resolution_date_of([{"resolution_date": date(2021, 1, 2)}]) == date(2021, 1, 2)
