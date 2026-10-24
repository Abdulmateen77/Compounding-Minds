"""Where agent output is saved: runs, calls, grades, corrections, snapshots, eval results.

The dashboard reads Postgres only (CLAUDE.md rule 5), so everything the agents and the
eval produce lands in the tables of store/schema.sql plus schemas/run_extras.sql.

    PostgresRunStore(dsn)   the real one (needs psycopg and DATABASE_URL)
    JsonlRunStore(dir)      offline: one .jsonl file per table, same row shapes
    MemoryRunStore()        tests

Every write is idempotent on its primary key, so re-running a cached replay is safe.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from schemas import AgentCall, Correction, Grade

TABLES = ("runs", "calls", "grades", "corrections", "snapshots", "eval_results")
RUN_KINDS = ("train", "heldout")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_row(run_id: str, kind: str, config: dict | None = None) -> dict:
    if kind not in RUN_KINDS:
        raise ValueError(f"run kind must be one of {RUN_KINDS}")
    return {"run_id": run_id, "kind": kind, "config": config or {}, "started_at": _now()}


def call_row(call: AgentCall) -> dict:
    return {"call_id": call.call_id, "run_id": call.run_id, "agent": call.agent, "company_id": call.company_id,
            "as_of": call.as_of.isoformat(), "payload": call.model_dump(mode="json")}


def grade_row(g: Grade) -> dict:
    return {"call_id": g.call_id, "graded_at": g.graded_at.isoformat(), "outcome": g.outcome, "correct": g.correct,
            "brier": g.brier, "evidence": g.evidence,
            "resolution_date": g.resolution_date.isoformat() if g.resolution_date else None}


def correction_row(c: Correction, mubit_ref: str | None = None, applied: bool = False) -> dict:
    return {"correction_id": c.correction_id, "call_id": c.call_id, "agent": c.agent, "summary": c.lesson,
            "payload": c.model_dump(mode="json"), "mubit_ref": mubit_ref,
            "applied_at": _now() if applied else None}


def snapshot_row(run_id: str, agent: str, arm: str, as_of: date, n: int, accuracy: float | None,
                 brier: float | None, model: str | None) -> dict:
    return {"run_id": run_id, "agent": agent, "arm": arm, "as_of": as_of.isoformat(), "n": n,
            "accuracy": accuracy, "brier": brier, "model": model}


class RunStore:
    """Write API. Subclasses implement `_put(table, key, row)`."""

    KEYS = {"runs": ("run_id",), "calls": ("call_id",), "grades": ("call_id",),
            "corrections": ("correction_id",), "snapshots": ("run_id", "agent", "arm", "as_of"),
            "eval_results": ("run_id",)}

    def _put(self, table: str, row: dict) -> None:
        raise NotImplementedError

    def start_run(self, run_id: str, kind: str, config: dict | None = None) -> None:
        self._put("runs", run_row(run_id, kind, config))

    def write_call(self, call: AgentCall) -> None:
        self._put("calls", call_row(call))

    def write_grade(self, g: Grade) -> None:
        self._put("grades", grade_row(g))

    def write_correction(self, c: Correction, mubit_ref: str | None = None, applied: bool = False) -> None:
        self._put("corrections", correction_row(c, mubit_ref, applied))

    def write_snapshot(self, run_id: str, agent: str, arm: str, as_of: date, n: int,
                       accuracy: float | None, brier: float | None, model: str | None) -> None:
        self._put("snapshots", snapshot_row(run_id, agent, arm, as_of, n, accuracy, brier, model))

    def write_eval_result(self, run_id: str, report: dict) -> None:
        self._put("eval_results", {"run_id": run_id, "generated_at": _now(),
                                   "real_results": bool(report.get("provenance", {}).get("real_results")),
                                   "report": report})


class MemoryRunStore(RunStore):
    def __init__(self):
        self.tables: dict[str, dict[tuple, dict]] = {t: {} for t in TABLES}

    def _put(self, table, row):
        self.tables[table][tuple(row[k] for k in self.KEYS[table])] = row

    def rows(self, table: str) -> list[dict]:
        return list(self.tables[table].values())


class JsonlRunStore(MemoryRunStore):
    """Offline store: keeps the latest row per key and rewrites <dir>/<table>.jsonl on close."""

    def __init__(self, directory: Path | str):
        super().__init__()
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        for t in TABLES:
            p = self.dir / f"{t}.jsonl"
            if p.exists():
                for line in p.read_text().splitlines():
                    super()._put(t, json.loads(line))

    def flush(self) -> None:
        for t, rows in self.tables.items():
            if rows:
                (self.dir / f"{t}.jsonl").write_text("".join(json.dumps(r, default=str) + "\n" for r in rows.values()))

    close = flush


_JSON_COLS = {"config", "payload", "evidence", "report"}
# Rows carry ISO strings and JSON text; cast in SQL so no driver type guessing is involved.
_CASTS = {**{c: "jsonb" for c in _JSON_COLS}, "as_of": "date", "resolution_date": "date",
          "graded_at": "timestamptz", "applied_at": "timestamptz", "started_at": "timestamptz",
          "generated_at": "timestamptz"}


class PostgresRunStore(RunStore):
    """Upserts into Postgres. Run store/schema.sql then schemas/run_extras.sql first.

    `calls.company_id` references `companies`, so Person A's ingest must have loaded the
    universe before a real replay writes calls.
    """

    def __init__(self, dsn: str | None = None, conn: Any = None):
        if conn is None:
            import psycopg  # optional dependency: only the real store needs it
            conn = psycopg.connect(dsn or os.environ["DATABASE_URL"])
        self.conn = conn

    def _put(self, table, row):
        cols = list(row)
        keys = self.KEYS[table]
        placeholders = ", ".join(f"%({c})s::{_CASTS[c]}" if c in _CASTS else f"%({c})s" for c in cols)
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in keys)
        sql = (f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) "
               f"ON CONFLICT ({', '.join(keys)}) DO " + (f"UPDATE SET {updates}" if updates else "NOTHING"))
        params = {c: json.dumps(v, default=str) if c in _JSON_COLS else v for c, v in row.items()}
        with self.conn.cursor() as cur:
            cur.execute(sql, params)

    def flush(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()


def open_store(target: str | None) -> RunStore | None:
    """'postgres' (uses DATABASE_URL), a directory path for JSONL, or None for no saving."""
    if not target:
        return None
    if target == "postgres":
        return PostgresRunStore()
    return JsonlRunStore(target)
