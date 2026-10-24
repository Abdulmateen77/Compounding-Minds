"""The same metrics, read from a real Postgres: types, dates and the date gate must not change a number.
Skipped automatically when no database is reachable."""
from datetime import date

import pytest

from metrics import AGENT_METRICS, get_metrics
from store import db, queries
from store.pg import PostgresBackend

from . import factory as F

AFTER = date(2019, 3, 1)


@pytest.fixture
def both(pg_conn):
    facts = F.build_facts()
    events = [dict(company_id="anon_001", form="8-K", items=["4.01"], filed_date=date(2016, 6, 1), accession="EV-1"),
              dict(company_id="anon_001", form="10-Q", items=[], filed_date=date(2018, 8, 5), accession="EV-2",
                   going_concern_hits=2)]
    macro = F.build_macro()
    db.upsert_companies(pg_conn, [dict(company_id="anon_001", cik="1", ticker="X", name="X")])
    db.insert_facts(pg_conn, facts)
    db.insert_events(pg_conn, events)
    db.insert_macro(pg_conn, macro)
    F.install(facts, events, macro)
    memory = {a: get_metrics("anon_001", a, AFTER) for a in AGENT_METRICS}
    queries.set_backend(PostgresBackend(pg_conn))
    yield memory
    F.reset()


def test_postgres_gives_the_same_numbers_as_the_in_memory_gate(both):
    for agent, expected in both.items():
        got = get_metrics("anon_001", agent, AFTER)
        assert got == expected, agent


def test_the_postgres_path_still_hides_the_future(both):
    before = get_metrics("anon_001", "fundamentals", date(2019, 2, 19))       # before the FY2018 10-K
    after = get_metrics("anon_001", "fundamentals", AFTER)
    assert before != after
    filed = {f["accession"]: f["filed_date"] for f in F.build_facts()}
    for m in before["metrics"]:
        assert all(filed[a] <= date(2019, 2, 19) for a in m["inputs"])
