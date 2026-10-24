"""Pure scoring maths (no LLM, no I/O). README 8.2."""
from __future__ import annotations

from .config import BUCKET_ORDER, BUCKETS


def bucket_for_growth(growth: float) -> str:
    for name, (lo, hi) in BUCKETS.items():
        if lo <= growth < hi:
            return name
    raise ValueError(growth)


def brier_binary(prob_answer_correct_is_yes: float, outcome_yes: bool) -> float:
    """Brier for a binary question; `p` is the probability assigned to 'yes'."""
    return (prob_answer_correct_is_yes - (1.0 if outcome_yes else 0.0)) ** 2


def p_yes(answer: str, probability: float) -> float:
    """AgentCall.probability is P(stated answer is correct); convert to P(yes)."""
    return probability if answer == "yes" else 1.0 - probability


def brier_multiclass(answer: str, probability: float, outcome: str) -> float:
    """Remaining mass is spread evenly over the other buckets (agents emit one probability)."""
    others = (1.0 - probability) / (len(BUCKET_ORDER) - 1)
    return sum(
        ((probability if b == answer else others) - (1.0 if b == outcome else 0.0)) ** 2
        for b in BUCKET_ORDER
    )


def accuracy(grades) -> float | None:
    """Share correct among resolvable grades; `unresolvable` (correct is None) is excluded."""
    done = [g for g in grades if g.correct is not None]
    return sum(g.correct for g in done) / len(done) if done else None
