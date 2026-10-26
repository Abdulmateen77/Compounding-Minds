"""Baselines (README 8.4, 9) and the scoring used to compare them with the agents.

* always-yes (binary) / always-base (bucket): the same fixed answer every time, fully confident
* base rate: the most common train-window outcome, at its train-window frequency

Baselines see only train-window outcomes, so they cannot peek at held-out results.
"""
from __future__ import annotations

from collections import Counter

from grader.scoring import brier_binary, brier_multiclass, p_yes

NAIVE_ANSWER = {"binary": "yes", "bucket": "base"}
NAIVE_NAME = {"binary": "always_yes", "bucket": "always_base"}


def brier_for(claim_type: str, answer: str, probability: float, outcome: str) -> float:
    if claim_type == "bucket":
        return brier_multiclass(answer, probability, outcome)
    return brier_binary(p_yes(answer, probability), outcome == "yes")


def naive_prediction(claim_type: str) -> tuple[str, float]:
    return NAIVE_ANSWER[claim_type], 1.0


def base_rate_prediction(train_outcomes: list[str]) -> tuple[str, float] | None:
    """Most common train outcome and how often it happened. None if there is no train data."""
    if not train_outcomes:
        return None
    answer, n = Counter(train_outcomes).most_common(1)[0]
    return answer, n / len(train_outcomes)


def score(claim_type: str, rows: list[tuple[str, float, str]]) -> dict:
    """rows are (answer, probability, outcome). Accuracy and mean Brier; None when empty."""
    if not rows:
        return {"n": 0, "accuracy": None, "brier": None}
    n = len(rows)
    return {
        "n": n,
        "accuracy": sum(a == o for a, _, o in rows) / n,
        "brier": sum(brier_for(claim_type, a, p, o) for a, p, o in rows) / n,
    }


def score_baselines(claim_type: str, outcomes: list[str], train_outcomes: list[str]) -> dict:
    """Score both baselines against the same held-out outcomes the agents were scored on."""
    out = {}
    ans, p = naive_prediction(claim_type)
    out[NAIVE_NAME[claim_type]] = score(claim_type, [(ans, p, o) for o in outcomes])
    br = base_rate_prediction(train_outcomes)
    out["base_rate"] = (score(claim_type, [(br[0], br[1], o) for o in outcomes]) | {"answer": br[0], "probability": br[1]}
                        if br else {"n": 0, "accuracy": None, "brier": None})
    return out
