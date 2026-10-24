import json
import re
from datetime import date
from pathlib import Path

import pytest

from agents.gateway import FakeModelUpdater, ScriptedGateway
from agents.offline import scripted_llm
from agents.run_store import JsonlRunStore, MemoryRunStore, PostgresRunStore, open_store
from agents.runner import run_agent
from grader.grade import grade
from schemas import Correction
from store.stubs import get_metrics_stub

AS_OF = date(2019, 6, 30)
SCHEMA = (Path(__file__).resolve().parents[2] / "store" / "schema.sql").read_text()
EXTRAS = (Path(__file__).resolve().parents[2] / "schemas" / "run_extras.sql").read_text()


def a_call(tmp_path, run_id="r1"):
    m = get_metrics_stub("anon_001", "fundamentals", AS_OF)
    return run_agent("fundamentals", "anon_001", AS_OF, m, ScriptedGateway(scripted_llm), FakeModelUpdater(tmp_path), run_id=run_id)


def columns(table: str) -> set[str]:
    body = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\n\);", SCHEMA + EXTRAS, re.S).group(1)
    cols = {l.split()[0] for l in body.splitlines() if l.strip() and not l.strip().startswith(("--", "PRIMARY"))}
    cols |= set(re.findall(rf"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS (\w+)", EXTRAS))
    return cols


def test_rows_match_the_sql_schema(tmp_path):
    s = MemoryRunStore()
    call = a_call(tmp_path)
    s.start_run("r1", "train", {"x": 1})
    s.write_call(call)
    s.write_grade(grade(call))
    s.write_snapshot("r1", "fundamentals", "learned", AS_OF, 4, 2, 0.5, 0.2, "m")
    s.write_correction(Correction(correction_id="c1", call_id=call.call_id, agent="fundamentals", company_id="anon_001",
                                  as_of=AS_OF, predicted={"answer": "yes", "probability": 0.8},
                                  actual={"outcome": "no", "evidence": []}, error_type="overconfident", lesson="x"))
    s.write_eval_result("r1", {"provenance": {"real_results": False}})
    for table in ("runs", "calls", "grades", "corrections", "snapshots", "eval_results"):
        assert set(s.rows(table)[0]) <= columns(table), table
    assert s.rows("calls")[0]["payload"]["claim"]["question_id"] == "fcf_margin_improves_next_q"


def test_bad_run_kind_is_refused():
    with pytest.raises(ValueError):
        MemoryRunStore().start_run("r", "demo")


def test_writes_are_idempotent_and_jsonl_round_trips(tmp_path):
    s = JsonlRunStore(tmp_path / "db")
    call = a_call(tmp_path)
    s.write_call(call)
    s.write_call(call)
    s.close()
    again = JsonlRunStore(tmp_path / "db")
    assert len(again.rows("calls")) == 1 and again.rows("calls")[0]["call_id"] == call.call_id


class FakeCursor:
    def __init__(self, log): self.log = log
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, params): self.log.append((sql, params))


class FakeConn:
    def __init__(self): self.log, self.commits = [], 0
    def cursor(self): return FakeCursor(self.log)
    def commit(self): self.commits += 1
    def close(self): pass


def test_postgres_upserts_with_casts(tmp_path):
    conn = FakeConn()
    s = PostgresRunStore(conn=conn)
    call = a_call(tmp_path)
    s.write_call(call)
    s.write_grade(grade(call))
    s.close()
    sql, params = conn.log[0]
    assert sql.startswith("INSERT INTO calls") and "ON CONFLICT (call_id) DO UPDATE" in sql
    assert "%(payload)s::jsonb" in sql and "%(as_of)s::date" in sql
    assert json.loads(params["payload"])["call_id"] == call.call_id
    assert "%(resolution_date)s::date" in conn.log[1][0] and conn.commits == 1


def test_open_store():
    assert open_store(None) is None


def test_snapshot_rejects_unknown_variant():
    with pytest.raises(ValueError):
        MemoryRunStore().write_snapshot("r1", "fundamentals", "arm_x", AS_OF, 1, 1, 1.0, 0.1, None)


def test_snapshot_key_is_the_schema_primary_key():
    s = MemoryRunStore()
    for v in ("learned", "frozen"):
        s.write_snapshot("r1", "fundamentals", v, AS_OF, 4, 2, 0.5, 0.2, "m")
    s.write_snapshot("r1", "fundamentals", "learned", AS_OF, 5, 3, 0.6, 0.2, "m")
    assert len(s.rows("snapshots")) == 2
