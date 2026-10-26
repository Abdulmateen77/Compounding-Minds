"""grade(call) -> Grade.  Stub outcome fn for the learning loop (README 12); real rules are grader/rules.py.

Real rules live in grader/rules.py and resolve against filings with filed_date > as_of.
`stub_outcome` returns a deterministic fake outcome (used for the stub question_ids).
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Callable

from schemas import AgentCall, Grade

from .config import DEFAULT_RESOLUTION_DAYS
from .scoring import brier_binary, brier_multiclass, p_yes

log = logging.getLogger("grader.unresolvable")
OutcomeFn = Callable[[AgentCall], tuple[str, dict | None]]  # -> (outcome, resolution info)


def stub_outcome(call: AgentCall) -> tuple[str, dict | None]:
    h = int(hashlib.sha256(f"{call.company_id}{call.as_of}{call.claim.question_id}".encode()).hexdigest(), 16)
    if call.claim.type == "bucket":
        return ("bear", "base", "bull")[h % 3], {"stub": True}
    return ("yes" if h % 2 else "no"), {"stub": True}


def nominal_resolution_date(call: AgentCall) -> date:
    return call.as_of + timedelta(days=DEFAULT_RESOLUTION_DAYS[call.horizon])


def _reason(info: dict | None) -> object:
    info = info or {}
    if info.get("reason"):
        return info["reason"]
    return {k: v.get("reason") for k, v in (info.get("components") or {}).items()
            if v.get("result") == "unresolvable"}


def grade(call: AgentCall, outcome_fn: OutcomeFn = stub_outcome) -> Grade:
    """resolution_date is always filled: the filing date that settled the call, the date we
    stopped looking (unresolvable), or the nominal horizon date when the rule gave none."""
    outcome, info = outcome_fn(call)
    now = datetime.now(timezone.utc)
    res = (info or {}).get("resolution_date")
    resolution_date = date.fromisoformat(res) if isinstance(res, str) else res
    resolution_date = resolution_date or nominal_resolution_date(call)
    if outcome == "unresolvable":
        log.warning("unresolvable call_id=%s agent=%s company=%s as_of=%s question=%s reason=%s",
                    call.call_id, call.agent, call.company_id, call.as_of, call.claim.question_id,
                    _reason(info))
        return Grade(call_id=call.call_id, graded_at=now, resolution_date=resolution_date,
                     outcome=outcome, correct=None, brier=None, evidence=[info or {}])
    if call.claim.type == "bucket":
        brier = brier_multiclass(call.claim.answer, call.claim.probability, outcome)
    else:
        brier = brier_binary(p_yes(call.claim.answer, call.claim.probability), outcome == "yes")
    return Grade(call_id=call.call_id, graded_at=now, resolution_date=resolution_date, outcome=outcome,
                 correct=call.claim.answer == outcome, brier=brier, evidence=[info or {}])


def grade_many(calls: list[AgentCall], outcome_fn: OutcomeFn = stub_outcome) -> tuple[list[Grade], int]:
    """Grade a batch. Returns (grades, n_unresolvable). Unresolvable grades are kept (so the
    run knows they were tried and why) but carry correct=None, brier=None: accuracy and Brier
    averages must skip them (see grader.scoring.accuracy)."""
    grades = [grade(c, outcome_fn) for c in calls]
    return grades, sum(g.outcome == "unresolvable" for g in grades)
