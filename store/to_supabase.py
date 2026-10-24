"""Copy the local Postgres (schema and every row) to a hosted Postgres such as Supabase, then lock the tables.

    python -m store.to_supabase                    # reads DATABASE_URL (source) and SUPABASE_DB_URL (target) from .env
    python -m store.to_supabase --check-only       # compare row counts, change nothing

The target URL may hold a password with special characters (for example an "@"): it is split at the last "@" and the
password is percent-encoded here, so it can be pasted into .env as it is shown in the dashboard.

Row-level security is switched on for every table in the public schema. Supabase publishes the public schema as a web
API for anyone holding the project's public key; with RLS on and no policies, that API sees nothing. Our code connects
as the database owner, which is not subject to RLS, so it is unaffected.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

import psycopg

from . import db


def encode_url(raw: str) -> str:
    """Percent-encode the password of a postgres URL whose password may contain '@', '!', '#' and the like."""
    m = re.match(r"^(postgres(?:ql)?)://([^:/@]+):(.*)@([^@/]+)/(.+)$", raw.strip())
    if not m:
        return raw.strip()
    scheme, user, pw, hostport, name = m.groups()
    if re.search(r"%[0-9A-Fa-f]{2}", pw):          # already encoded
        return raw.strip()
    return f"{scheme}://{user}:{quote(pw, safe='')}@{hostport}/{name}"


def target_url() -> str:
    from dotenv import dotenv_values
    env = {**dotenv_values(Path(__file__).resolve().parent.parent / ".env"), **os.environ}
    for key in ("SUPABASE_DB_URL", "SUPABASE_DB_PASSWORD"):      # the second name is where the URL was first pasted
        if "://" in (env.get(key) or ""):
            return encode_url(env[key])
    raise SystemExit("no SUPABASE_DB_URL in .env")


def tables(conn: psycopg.Connection) -> list[str]:
    """Public tables, parents before children (foreign keys), so rows can be copied in order."""
    cur = conn.cursor()
    cur.execute("select table_name from information_schema.tables where table_schema='public' and table_type='BASE TABLE'")
    names = [r[0] for r in cur.fetchall()]
    cur.execute("""select cl.relname, pr.relname from pg_constraint c
                   join pg_class cl on cl.oid = c.conrelid join pg_class pr on pr.oid = c.confrelid
                   join pg_namespace n on n.oid = cl.relnamespace where c.contype='f' and n.nspname='public'""")
    deps = {n: set() for n in names}
    for child, parent in cur.fetchall():
        if child in deps and parent in deps and child != parent:
            deps[child].add(parent)
    out: list[str] = []
    while deps:
        ready = sorted(n for n, d in deps.items() if d <= set(out))
        if not ready:                                   # a cycle: copy the rest as they are
            ready = sorted(deps)
        for n in ready:
            out.append(n)
            deps.pop(n)
    return out


def counts(conn: psycopg.Connection, names: list[str]) -> dict[str, int]:
    cur = conn.cursor()
    out = {}
    for n in names:
        cur.execute(f'select count(*) from "{n}"')
        out[n] = cur.fetchone()[0]
    return out


def copy_table(src: psycopg.Connection, dst: psycopg.Connection, name: str) -> int:
    n = 0
    with src.cursor().copy(f'COPY "{name}" TO STDOUT') as out, dst.cursor().copy(f'COPY "{name}" FROM STDIN') as into:
        for chunk in out:
            into.write(chunk)
            n += len(chunk)
    return n


def fix_sequences(dst: psycopg.Connection, names: list[str]) -> None:
    """After copying explicit ids, move each serial sequence past the largest id so new inserts do not collide."""
    cur = dst.cursor()
    cur.execute("select table_name from information_schema.columns where table_schema='public' and column_name='id' "
                "and column_default like 'nextval%'")
    for (n,) in cur.fetchall():
        if n in names:
            cur.execute("select pg_get_serial_sequence(%s, 'id')", (f'public."{n}"',))
            seq = cur.fetchone()[0]
            if seq:
                cur.execute(f'select setval(%s, coalesce((select max(id) from "{n}"), 1))', (seq,))


def lock(dst: psycopg.Connection, names: list[str]) -> None:
    for n in names:
        dst.execute(f'alter table "{n}" enable row level security')


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check-only", action="store_true")
    a = ap.parse_args(argv)
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    dst_url = target_url()
    with db.connect() as src, psycopg.connect(dst_url, connect_timeout=20) as dst:
        names = tables(src)
        if not a.check_only:
            db.apply_schema(dst)
            have = counts(dst, [t for t in names if t in tables(dst)])
            if any(have.values()):
                print("target already has rows:", {k: v for k, v in have.items() if v}, "- refusing to copy over them", file=sys.stderr)
                return 2
            for n in names:
                print(f"copying {n} ...", flush=True)
                copy_table(src, dst, n)
            fix_sequences(dst, names)
            lock(dst, names)
            dst.commit()
        a_, b_ = counts(src, names), counts(dst, names)
        ok = a_ == b_
        for n in names:
            print(f"  {n:<22} local {a_[n]:>8}   supabase {b_[n]:>8}  {'ok' if a_[n] == b_[n] else 'MISMATCH'}")
        cur = dst.cursor()
        cur.execute("select relname, relrowsecurity from pg_class c join pg_namespace n on n.oid=c.relnamespace "
                    "where n.nspname='public' and c.relkind='r' order by 1")
        print("row-level security:", {r[0]: r[1] for r in cur.fetchall()})
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
