"""grade(call) -> Grade.  STUB rule set so Person B can test the learning loop (README 12).

Real rules live in grader/rules.py (owner A) and resolve against filings with
filed_date > as_of. Until then `stub_outcome` returns a deterministic fake outcome.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from typing import Callable

from schemas import AgentCall, Grade

from .scoring import brier_binary, brier_multiclass, p_yes

OutcomeFn = Callable[[AgentCall], tuple[str, dict | None]]  # -> (outcome, resolution info)


def stub_outcome(call: AgentCall) -> tuple[str, dict | None]:
    h = int(hashlib.sha256(f"{call.company_id}{call.as_of}{call.claim.question_id}".encode()).hexdigest(), 16)
    if call.claim.type == "bucket":
        return ("bear", "base", "bull")[h % 3], {"stub": True}
    return ("yes" if h % 2 else "no"), {"stub": True}


def grade(call: AgentCall, outcome_fn: OutcomeFn = stub_outcome) -> Grade:
    outcome, info = outcome_fn(call)
    now = datetime.now(timezone.utc)
    res = (info or {}).get("resolution_date")
    resolution_date = date.fromisoformat(res) if isinstance(res, str) else res
    if outcome == "unresolvable":
        return Grade(call_id=call.call_id, graded_at=now, resolution_date=resolution_date,
                     outcome=outcome, correct=None, brier=None, evidence=[info or {}])
    if call.claim.type == "bucket":
        brier = brier_multiclass(call.claim.answer, call.claim.probability, outcome)
    else:
        brier = brier_binary(p_yes(call.claim.answer, call.claim.probability), outcome == "yes")
    return Grade(call_id=call.call_id, graded_at=now, resolution_date=resolution_date, outcome=outcome,
                 correct=call.claim.answer == outcome, brier=brier, evidence=[info or {}])
