"""Postgres backend for the date gate (README 4.4). It only supplies CANDIDATE rows: the rule
that decides what is visible at `as_of` stays in store/queries.py, so the in-memory backend used
by the tests and this one cannot disagree. Use:

    from store import queries, pg
    queries.set_backend(pg.PostgresBackend(conn))
"""
from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

_FACT_COLS = ("company_id, concept, source_tag, value, unit, period_start, period_end, "
              "fiscal_year, fiscal_period, form, accession, filed_date")
_EVENT_COLS = "company_id, form, items, filed_date, accession, text_ref, going_concern_hits"
_MACRO_COLS = "series_id, value, obs_date, vintage_date"


class PostgresBackend:
    def __init__(self, conn: psycopg.Connection):
        self._conn = conn

    def _rows(self, sql: str, params: tuple) -> list[dict]:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def facts(self, company_id: str, concept: str) -> list[dict]:
        return self._rows(f"SELECT {_FACT_COLS} FROM facts WHERE company_id = %s AND concept = %s",
                          (company_id, concept))

    def events(self, company_id: str) -> list[dict]:
        return self._rows(f"SELECT {_EVENT_COLS} FROM events WHERE company_id = %s", (company_id,))

    def macro(self, series_id: str) -> list[dict]:
        return self._rows(f"SELECT {_MACRO_COLS} FROM macro WHERE series_id = %s", (series_id,))
