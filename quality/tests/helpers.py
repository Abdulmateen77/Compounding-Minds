"""Builders for the quality tests. Grades are made by the project's own `grader.grade.grade`, so
the Brier in a test is the real one, not a re-implementation of it."""
from __future__ import annotations

import itertools
from datetime import date, datetime, timedelta, timezone

from agents.specs import SPECS
from quality.metrics import Scored
from grader.grade import grade
from schemas import AgentCall

_ids = itertools.count(1)
GRADED = datetime(2025, 1, 1, tzinfo=timezone.utc)


def make_call(agent: str = "fundamentals", company: str = "anon_001", as_of: date = date(2019, 6, 30),
              answer: str | None = None, prob: float = 0.7, evidence=()) -> AgentCall:
    spec = SPECS[agent]
    answer = answer or spec.answers[0]
    return AgentCall.model_validate({
        "call_id": f"call-{next(_ids)}", "run_id": "run-1", "agent": agent, "company_id": company,
        "as_of": as_of.isoformat(), "horizon": spec.horizon,
        "claim": {"type": spec.claim_type, "question_id": spec.question_id, "answer": answer, "probability": prob},
        "confidence": prob, "reasoning": ["test"], "evidence": list(evidence), "principles_used": [],
        "tool_calls": 0, "model": "test"})


def make_scored(outcome: str, variant: str = "learned", resolution: date | None = "default",
                graded_at: datetime = GRADED, **kw) -> Scored:
    """One scored call. `resolution` defaults to 90 days after as_of; pass None for 'not recorded'."""
    call = make_call(**kw)
    if resolution == "default":
        resolution = call.as_of + timedelta(days=90)
    info = {"resolution_date": resolution.isoformat()} if resolution else {}
    g = grade(call, outcome_fn=lambda c: (outcome, dict(info))).model_copy(update={"graded_at": graded_at})
    return Scored(call=call, grade=g, variant=variant)


def six_binary() -> list[Scored]:
    """Six fundamentals calls with outcomes worked out by hand (see test_metrics):

        answer p     outcome  correct  p(yes)  brier
        yes   0.8    yes      yes      0.8     0.04
        yes   0.6    no       no       0.6     0.36
        no    0.7    no       yes      0.3     0.09
        no    0.9    yes      no       0.1     0.81
        yes   0.5    yes      yes      0.5     0.25
        yes   0.7    yes      yes      0.7     0.09
    """
    rows = [("yes", 0.8, "yes"), ("yes", 0.6, "no"), ("no", 0.7, "no"),
            ("no", 0.9, "yes"), ("yes", 0.5, "yes"), ("yes", 0.7, "yes")]
    return [make_scored(o, answer=a, prob=p, company=f"anon_{i:03d}") for i, (a, p, o) in enumerate(rows, 1)]
