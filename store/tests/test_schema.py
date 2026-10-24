"""Schema checks. Syntax is parsed with a real Postgres parser when `pglast` is installed
(pip install pglast), so a typo is caught without a running database."""
import re
from pathlib import Path

import pytest

SQL = (Path(__file__).resolve().parent.parent / "schema.sql").read_text(encoding="utf-8")


def _tables() -> dict[str, str]:
    body = re.sub(r"--[^\n]*", "", SQL)
    return {m.group(1): m.group(2) for m in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", body, re.S)}


def test_every_visible_in_time_table_has_a_not_null_date():
    t = _tables()
    for name in ("facts", "events"):
        assert re.search(r"filed_date\s+DATE NOT NULL", t[name]), name
    assert re.search(r"vintage_date\s+DATE NOT NULL", t["macro"])


def test_expected_tables_exist():
    assert set(_tables()) == {"companies", "facts", "events", "macro", "prices", "runs", "calls",
                              "grades", "corrections", "snapshots"}


def test_facts_has_an_idempotency_key():
    assert "facts_uniq" in SQL and "period_start_key" in SQL


def test_parses_as_postgres():
    pglast = pytest.importorskip("pglast")
    stmts = pglast.parse_sql(SQL)
    assert len(stmts) == 18  # 10 tables, 1 generated column, 7 indexes
