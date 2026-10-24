"""Per-agent track record from grades (README 11b stretch). Pure Python, no LLM, no I/O.

Point-in-time: at `as_of` only grades whose resolution_date <= as_of count, so the record a
quarter sees never includes an outcome that was not yet filed. `unresolvable` grades are counted
but kept out of accuracy, Brier and the calibration bins (README 6.2).

calibration bins: equal-width confidence bands over [0, 1] (the last includes 1.0). A
well-calibrated agent is right about as often as it says it is in every band.
overconfidence_gap = mean confidence - accuracy; above 0 the agent claims more than it delivers.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from schemas import AgentCall, Grade

from .scoring import accuracy


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def known_at(pairs: list[tuple[AgentCall, Grade]], as_of: date | None) -> list[tuple[AgentCall, Grade]]:
    """Graded pairs whose outcome was knowable by `as_of` (None = everything)."""
    return [(c, g) for c, g in pairs
            if as_of is None or (g.resolution_date is not None and g.resolution_date <= as_of)]


def bins(pairs: list[tuple[AgentCall, Grade]], n_bins: int = 5) -> list[dict]:
    if n_bins < 1:
        raise ValueError("n_bins must be at least 1")
    groups: list[list[tuple[AgentCall, Grade]]] = [[] for _ in range(n_bins)]
    for c, g in pairs:
        if g.correct is not None:
            groups[min(int(c.confidence * n_bins), n_bins - 1)].append((c, g))
    return [{"lo": i / n_bins, "hi": (i + 1) / n_bins, "n": len(b),
             "mean_confidence": _mean([c.confidence for c, _ in b]),
             "accuracy": accuracy([g for _, g in b])} for i, b in enumerate(groups)]


def record(pairs: list[tuple[AgentCall, Grade]], n_bins: int = 5) -> dict:
    """One agent's numbers from its (call, grade) pairs."""
    done = [(c, g) for c, g in pairs if g.correct is not None]
    acc, conf = accuracy([g for _, g in done]), _mean([c.confidence for c, _ in done])
    return {"calls_graded": len(done), "unresolvable": len(pairs) - len(done), "accuracy": acc,
            "brier": _mean([g.brier for _, g in done if g.brier is not None]),
            "mean_confidence": conf,
            "overconfidence_gap": None if acc is None or conf is None else conf - acc,
            "bins": bins(done, n_bins)}


def track_record(pairs: list[tuple[AgentCall, Grade]], as_of: date | None = None,
                 n_bins: int = 5) -> dict[str, dict]:
    """{agent: record} over the grades known at `as_of`. Agents with nothing known are left out."""
    by_agent: dict[str, list[tuple[AgentCall, Grade]]] = defaultdict(list)
    for c, g in known_at(pairs, as_of):
        by_agent[c.agent].append((c, g))
    return {a: record(ps, n_bins) for a, ps in sorted(by_agent.items())}
