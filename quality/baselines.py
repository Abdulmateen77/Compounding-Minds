"""The two baselines every agent has to beat (README 8.4, BRIEF_HERMES H2).

A baseline is just a stand-in call: an answer and the probability that answer is right, the
same convention as `AgentCall.probability`. Scoring reuses `grader.scoring` so a baseline and
an agent are marked by identical maths.

  always_yes   always "yes" (scenarios: always "base") with probability 1.0
  base_rate    the most common outcome in the TRAINING cell, with probability equal to how often
               it happened there

The training cell is a training company in a training year whose outcome was settled inside
the training window. It never contains a held-out company, a held-out year, or an outcome that
only a later filing revealed.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Collection, Sequence

from grader.scoring import brier_binary, brier_multiclass, p_yes

from .metrics import Scored, is_resolved
from .split import in_training_cell, resolves_after_training

ALWAYS_YES = "always_yes"
BASE_RATE = "base_rate"


@dataclass(frozen=True)
class Pick:
    answer: str
    probability: float   # probability the answer is correct


def always_yes_pick(claim_type: str) -> Pick:
    return Pick("base" if claim_type == "bucket" else "yes", 1.0)


def score_pick(pick: Pick, claim_type: str, outcome: str) -> tuple[bool, float]:
    """(correct, Brier) for one resolved outcome. The Brier for a bucket spreads the leftover
    probability evenly over the other buckets, as `grader.scoring.brier_multiclass` does."""
    if claim_type == "bucket":
        return pick.answer == outcome, brier_multiclass(pick.answer, pick.probability, outcome)
    return pick.answer == outcome, brier_binary(p_yes(pick.answer, pick.probability), outcome == "yes")


def score_outcomes(pick: Pick | None, claim_type: str, outcomes: Sequence[str]) -> tuple[float | None, float | None]:
    """(accuracy, mean Brier) of a pick over resolved outcomes. None when there is nothing to score."""
    if pick is None or not outcomes:
        return None, None
    scored = [score_pick(pick, claim_type, o) for o in outcomes]
    return sum(c for c, _ in scored) / len(scored), sum(b for _, b in scored) / len(scored)


@dataclass
class BaseRateFit:
    picks: dict[str, Pick] = field(default_factory=dict)         # agent -> pick
    n_train: dict[str, int] = field(default_factory=dict)        # agent -> training cases used
    unknown_resolution: dict[str, int] = field(default_factory=dict)  # used, but resolution date missing
    excluded_late: dict[str, int] = field(default_factory=dict)  # left out: settled after training

    @property
    def notes(self) -> list[str]:
        out = []
        for agent in sorted(self.unknown_resolution):
            n = self.unknown_resolution[agent]
            if n:
                out.append(f"base_rate for {agent} used {n} training cases with no resolution date, "
                           "so it cannot prove they were settled inside the training window")
        for agent in sorted(self.excluded_late):
            n = self.excluded_late[agent]
            if n:
                out.append(f"base_rate for {agent} left out {n} training-window calls whose outcome "
                           "came from a filing after the training window")
        return out


def fit_base_rate(scored: Sequence[Scored], held_out_ids: Collection[str]) -> BaseRateFit:
    """Fit the base rate on the training cell only.

    Every variant's records are pooled and de-duplicated by (agent, company, as_of): the outcome
    belongs to the case, so the same case seen by the learned and the frozen twin counts once.
    Ties go to the alphabetically first outcome, so the fit is deterministic."""
    seen: set[tuple[str, str, object]] = set()
    outcomes: dict[str, Counter] = defaultdict(Counter)
    claim_type: dict[str, str] = {}
    fit = BaseRateFit()
    for s in scored:
        c = s.call
        if not in_training_cell(c, held_out_ids) or not is_resolved(s):
            continue
        key = (c.agent, c.company_id, c.as_of)
        if key in seen:
            continue
        seen.add(key)
        if resolves_after_training(s.grade):
            fit.excluded_late[c.agent] = fit.excluded_late.get(c.agent, 0) + 1
            continue
        if s.grade.resolution_date is None:
            fit.unknown_resolution[c.agent] = fit.unknown_resolution.get(c.agent, 0) + 1
        outcomes[c.agent][s.grade.outcome] += 1
        claim_type[c.agent] = c.claim.type
    for agent, counts in outcomes.items():
        total = sum(counts.values())
        answer, n = min(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        fit.picks[agent] = Pick(answer, n / total)
        fit.n_train[agent] = total
    return fit
