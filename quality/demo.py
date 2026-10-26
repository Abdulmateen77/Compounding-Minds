"""Synthetic scored calls so `python -m quality.cli --demo` runs with no database.

THIS IS NOT DATA ABOUT THE AGENTS. Every number it produces is made up from a seeded random
generator, and every report built from it says so in its notes. It exists to exercise the report
code, including the awkward paths: an agent where learned beats frozen, one where it ties, one
where it loses, calls that resolve after the training window, and unresolvable grades. The
three skill levels below are chosen to trigger those paths. They are not predictions.
"""
from __future__ import annotations

import random
import uuid
from datetime import date, datetime, timedelta, timezone

from schemas import AgentCall, Grade
from grader.scoring import brier_binary, brier_multiclass, p_yes

from .metrics import Scored

DEMO_NOTE = ("SYNTHETIC DEMO DATA: generated from a seeded random generator to test the report. "
             "None of these numbers describe the real agents.")

# agent -> (claim type, question id, answers, horizon in days, skill of learned, skill of frozen)
# skill = chance the agent's answer matches the outcome; the shape is chosen to exercise the report.
_AGENTS = {
    "fundamentals": ("binary", "fcf_margin_improves_next_q", ("yes", "no"), 100, 0.68, 0.58),   # learned better
    "risk":         ("binary", "distress_event_12m", ("yes", "no"), 365, 0.60, 0.60),           # a tie
    "scenarios":    ("bucket", "revenue_bucket_next_4q", ("bear", "base", "bull"), 365, 0.45, 0.55),  # learned worse
}
_HORIZON = {"binary": "next_quarter", "bucket": "4_quarters"}
_GRADED_AT = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _quarter_ends(first: int, last: int) -> list[date]:
    ends = []
    for year in range(first, last + 1):
        for month, day in ((3, 31), (6, 30), (9, 30), (12, 31)):
            ends.append(date(year, month, day))
    return ends


def demo_scored(seed: int = 7, n_companies: int = 50, held_out: set[str] | None = None) -> list[Scored]:
    """Learned and frozen calls for three agents, 2018Q1 to 2024Q4. Same seed, same output."""
    rng = random.Random(seed)
    ids = [f"anon_{i:03d}" for i in range(1, n_companies + 1)]
    held_out = held_out if held_out is not None else set(ids[-10:])
    out: list[Scored] = []
    for agent, (ctype, qid, answers, horizon_days, skill_l, skill_f) in _AGENTS.items():
        for company in ids:
            for as_of in _quarter_ends(2018, 2024):
                # skip some quarters so the demo is not a perfect grid
                if rng.random() < 0.55:
                    continue
                outcome = rng.choice(answers) if ctype == "bucket" or rng.random() < 0.5 else answers[0]
                resolution = as_of + timedelta(days=horizon_days)
                unresolvable = rng.random() < 0.04
                for variant, skill in (("learned", skill_l), ("frozen", skill_f)):
                    right = rng.random() < skill
                    answer = outcome if right else rng.choice([a for a in answers if a != outcome])
                    confidence = round(min(0.95, max(0.5, skill + rng.uniform(-0.08, 0.2))), 2)
                    call = AgentCall(
                        call_id=str(uuid.UUID(int=rng.getrandbits(128))), run_id=f"demo-{variant}", agent=agent,
                        company_id=company, as_of=as_of, horizon=_HORIZON[ctype],
                        claim={"type": ctype, "question_id": qid, "answer": answer, "probability": confidence},
                        confidence=confidence, reasoning=["synthetic demo call"], evidence=[],
                        principles_used=[], tool_calls=0, model=f"demo-{variant}")
                    info = {"resolution_date": resolution.isoformat(), "synthetic": True}
                    if unresolvable:
                        grade = Grade(call_id=call.call_id, graded_at=_GRADED_AT, resolution_date=resolution,
                                      outcome="unresolvable", correct=None, brier=None, evidence=[info])
                    else:
                        brier = (brier_multiclass(answer, confidence, outcome) if ctype == "bucket"
                                 else brier_binary(p_yes(answer, confidence), outcome == "yes"))
                        grade = Grade(call_id=call.call_id, graded_at=_GRADED_AT, resolution_date=resolution,
                                      outcome=outcome, correct=answer == outcome, brier=brier, evidence=[info])
                    out.append(Scored(call=call, grade=grade, variant=variant))
    return out


def demo_attempted(scored: list[Scored]) -> dict[str, int]:
    """A made-up attempt count (about 3% of replies invalid) so the valid-JSON row has a value."""
    counts: dict[str, int] = {}
    for s in scored:
        if s.variant == "learned":
            counts[s.call.agent] = counts.get(s.call.agent, 0) + 1
    return {agent: int(round(n / 0.97)) for agent, n in counts.items()}
