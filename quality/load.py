"""Read scored calls out of Postgres (BRIEF_HERMES H2). Person B writes the rows.

    calls  JOIN grades ON call_id   JOIN runs ON run_id

The variant comes from `runs.config->>'variant'` and defaults to `learned` when it is missing.
`calls.payload` is an AgentCall as JSON.

`grades` has no resolution_date column. The grader stores it inside `grades.evidence`
(`grader/grade.py` writes `evidence=[info]` and `info["resolution_date"]`), so it is read back
from there. The base-rate baseline needs it, to keep out outcomes that only came from a filing
after the training window.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Sequence

from schemas import AgentCall, Grade

from .metrics import Scored

QUERY = """
SELECT c.payload, g.graded_at, g.outcome, g.correct, g.brier, g.evidence,
       COALESCE(r.config->>'variant', 'learned') AS variant
FROM calls c
JOIN grades g ON g.call_id = c.call_id
JOIN runs r ON r.run_id = c.run_id
{where}
ORDER BY c.as_of, c.agent, c.company_id, c.call_id
"""


def _json(value):
    """psycopg returns JSONB already decoded; a driver that does not hands back text."""
    return json.loads(value) if isinstance(value, (str, bytes)) else value


def resolution_date_of(evidence) -> date | None:
    """The date the settling filing arrived, from the grader's evidence, if it recorded one."""
    for item in evidence or []:
        raw = item.get("resolution_date") if isinstance(item, dict) else None
        if raw:
            return raw if isinstance(raw, date) else date.fromisoformat(str(raw)[:10])
    return None


def row_to_scored(payload, graded_at: datetime, outcome: str, correct, brier, evidence, variant: str) -> Scored:
    call = AgentCall.model_validate(_json(payload))
    evidence = _json(evidence) or []
    grade = Grade(call_id=call.call_id, graded_at=graded_at, resolution_date=resolution_date_of(evidence),
                  outcome=outcome, correct=correct, brier=brier,
                  evidence=[e for e in evidence if isinstance(e, dict)])
    return Scored(call=call, grade=grade, variant=variant or "learned")


def load_scored_dir(runs_dir, run_ids: Sequence[str] | None = None) -> list[Scored]:
    """The same rows from a run_store JSONL directory (`grader.replay --out data/runs_final`).
    A grade that was re-written (offline regrade) appears twice: the last line wins."""
    from pathlib import Path
    root = Path(runs_dir)

    def rows(name):
        path = root / f"{name}.jsonl"
        if not path.exists():
            return []
        with path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    variant = {r["run_id"]: (r.get("config") or {}).get("variant", "learned") for r in rows("runs")}
    calls = {c["call_id"]: c for c in rows("calls") if not run_ids or c["run_id"] in run_ids}
    grades = {g["call_id"]: g for g in rows("grades") if g["call_id"] in calls}
    out = [row_to_scored(calls[cid]["payload"], datetime.fromisoformat(g["graded_at"]), g["outcome"],
                         g["correct"], g["brier"], g["evidence"], variant.get(calls[cid]["run_id"], "learned"))
           for cid, g in grades.items()]
    return sorted(out, key=lambda s: (s.call.as_of, s.call.agent, s.call.company_id, s.call.call_id))


def load_scored(conn, run_ids: Sequence[str] | None = None) -> list[Scored]:
    """Every graded call, optionally limited to some runs. An unresolvable grade is returned too:
    the metrics leave it out of accuracy and Brier and count it separately."""
    where, params = "", ()
    if run_ids:
        where, params = "WHERE c.run_id = ANY(%s)", (list(run_ids),)
    with conn.cursor() as cur:
        cur.execute(QUERY.format(where=where), params)
        return [row_to_scored(*row) for row in cur.fetchall()]
