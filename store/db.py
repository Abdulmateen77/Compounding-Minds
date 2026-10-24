"""Database access: connection, schema, and idempotent bulk loaders (Person A).

Every loader is safe to re-run: a second load of the same raw data inserts nothing. The
unique keys live in schema.sql. Loaders take plain dict rows (what ingest/parse_*.py return),
so Person B's fetchers only have to get raw JSON into the cache.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

import psycopg

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
DEFAULT_URL = "postgresql://localhost:5432/compounding_minds"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_URL)


def connect(url: str | None = None) -> psycopg.Connection:
    return psycopg.connect(url or database_url())


def apply_schema(conn: psycopg.Connection) -> None:
    """Create all tables and indexes. Idempotent."""
    conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def _many(conn: psycopg.Connection, sql: str, rows: Iterable[dict]) -> int:
    rows = list(rows)
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
        n = cur.rowcount
    conn.commit()
    return max(n, 0)


def upsert_companies(conn: psycopg.Connection, rows: Iterable[dict]) -> int:
    """Rows need company_id, cik, ticker, name. Re-running updates cik, sector and the flags."""
    rows = [{"sector": None, "covid_group": None, "held_out": False, "short_history": False, "sic": None, **r} for r in rows]
    return _many(conn, """
        INSERT INTO companies (company_id, cik, ticker, name, sector, covid_group, held_out, short_history, sic)
        VALUES (%(company_id)s, %(cik)s, %(ticker)s, %(name)s, %(sector)s, %(covid_group)s, %(held_out)s, %(short_history)s, %(sic)s)
        ON CONFLICT (company_id) DO UPDATE SET cik = EXCLUDED.cik, sector = EXCLUDED.sector,
            covid_group = EXCLUDED.covid_group, held_out = EXCLUDED.held_out, short_history = EXCLUDED.short_history,
            sic = COALESCE(EXCLUDED.sic, companies.sic)""", rows)


def set_sic(conn: psycopg.Connection, company_id: str, sic: str | None) -> None:
    if sic:
        conn.execute("UPDATE companies SET sic = %s WHERE company_id = %s", (sic, company_id))
        conn.commit()


def insert_facts(conn: psycopg.Connection, rows: Iterable[dict]) -> int:
    """A restatement is a new accession, so it is a new row. The same row twice is ignored."""
    rows = [{"source_tag": None, "fiscal_year": None, "fiscal_period": None, "period_start": None, **r} for r in rows]
    return _many(conn, """
        INSERT INTO facts (company_id, concept, source_tag, value, unit, period_start, period_end,
                           fiscal_year, fiscal_period, form, accession, filed_date)
        VALUES (%(company_id)s, %(concept)s, %(source_tag)s, %(value)s, %(unit)s, %(period_start)s, %(period_end)s,
                %(fiscal_year)s, %(fiscal_period)s, %(form)s, %(accession)s, %(filed_date)s)
        ON CONFLICT (company_id, concept, unit, period_start_key, period_end, accession) DO NOTHING""", rows)


def insert_events(conn: psycopg.Connection, rows: Iterable[dict]) -> int:
    """Re-running keeps the row but lets a later text pass add going_concern_hits and text_ref."""
    rows = [{"items": [], "text_ref": None, "going_concern_hits": 0, **r} for r in rows]
    return _many(conn, """
        INSERT INTO events (company_id, form, items, filed_date, accession, text_ref, going_concern_hits)
        VALUES (%(company_id)s, %(form)s, %(items)s, %(filed_date)s, %(accession)s, %(text_ref)s, %(going_concern_hits)s)
        ON CONFLICT (company_id, accession) DO UPDATE SET
            going_concern_hits = GREATEST(events.going_concern_hits, EXCLUDED.going_concern_hits),
            text_ref = COALESCE(EXCLUDED.text_ref, events.text_ref)""", rows)


def insert_macro(conn: psycopg.Connection, rows: Iterable[dict]) -> int:
    return _many(conn, """
        INSERT INTO macro (series_id, value, obs_date, vintage_date)
        VALUES (%(series_id)s, %(value)s, %(obs_date)s, %(vintage_date)s)
        ON CONFLICT (series_id, obs_date, vintage_date) DO NOTHING""", rows)
