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


def load_scored(conn, run_ids: Sequence[str] | None = None) -> list[Scored]:
    """Every graded call, optionally limited to some runs. An unresolvable grade is returned too:
    the metrics leave it out of accuracy and Brier and count it separately."""
    where, params = "", ()
    if run_ids:
        where, params = "WHERE c.run_id = ANY(%s)", (list(run_ids),)
    with conn.cursor() as cur:
        cur.execute(QUERY.format(where=where), params)
        return [row_to_scored(*row) for row in cur.fetchall()]
