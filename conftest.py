"""Shared test fixtures.

`pg_conn` gives every database test its own throwaway schema in a real Postgres, so the tests
exercise the real SQL (unique keys, ON CONFLICT, the generated column). If no Postgres is
reachable the database tests are SKIPPED, not failed:  docker compose up -d  then run pytest, or
point TEST_DATABASE_URL at any Postgres you can create schemas in.
"""
import os
import uuid

import pytest

TEST_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
_unreachable: str | None = None  # remember a failed connect so the remaining DB tests skip instantly


@pytest.fixture
def pg_conn():
    global _unreachable
    psycopg = pytest.importorskip("psycopg")
    if _unreachable:
        pytest.skip(_unreachable)
    try:
        conn = psycopg.connect(TEST_URL, connect_timeout=2)
    except psycopg.OperationalError as e:
        _unreachable = f"no test Postgres reachable at TEST_DATABASE_URL ({e.__class__.__name__})"
        pytest.skip(_unreachable)
    schema = "t_" + uuid.uuid4().hex[:10]
    conn.execute(f"CREATE SCHEMA {schema}")
    conn.execute(f"SET search_path TO {schema}")
    conn.commit()
    from store import db
    db.apply_schema(conn)
    try:
        yield conn
    finally:
        conn.rollback()
        conn.execute(f"DROP SCHEMA {schema} CASCADE")
        conn.commit()
        conn.close()
