"""Pure functions over `list[Scored]` (BRIEF_HERMES H2). No I/O, no database.

`unresolvable` grades are left out of accuracy and Brier everywhere. They are counted
separately so a missing filing never hides in a number.
A function returns None, never NaN, when there is nothing to measure.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Mapping, Sequence

from schemas import AgentCall, Grade

EVIDENCE_TOLERANCE = 1e-9  # the runner's own tolerance when it checks evidence at parse time


@dataclass(frozen=True)
class Scored:
    call: AgentCall
    grade: Grade            # outcome in yes|no|bull|base|bear|unresolvable
    variant: str            # "learned" | "frozen"


def is_resolved(s: Scored) -> bool:
    return s.grade.outcome != "unresolvable" and s.grade.correct is not None


def resolved(scored: Sequence[Scored]) -> list[Scored]:
    return [s for s in scored if is_resolved(s)]


def n_unresolvable(scored: Sequence[Scored]) -> int:
    return sum(1 for s in scored if s.grade.outcome == "unresolvable")


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def accuracy(scored: Sequence[Scored]) -> float | None:
    rs = resolved(scored)
    return _mean([1.0 if s.grade.correct else 0.0 for s in rs])


def mean_brier(scored: Sequence[Scored]) -> float | None:
    return _mean([s.grade.brier for s in resolved(scored) if s.grade.brier is not None])


def mean_confidence(scored: Sequence[Scored]) -> float | None:
    return _mean([s.call.confidence for s in resolved(scored)])


def overconfidence_gap(scored: Sequence[Scored]) -> float | None:
    """Mean confidence minus accuracy. Above 0 the agent claims to be right more often than it is."""
    conf, acc = mean_confidence(scored), accuracy(scored)
    return None if conf is None or acc is None else conf - acc


def calibration_bins(scored: Sequence[Scored], n_bins: int = 5) -> list[dict]:
    """Equal-width confidence bins over [0, 1]; the last one includes 1.0.

    Each bin reports how many resolved calls fell in it, their mean confidence and how often
    they were right. A well-calibrated agent has accuracy close to mean_confidence in every bin."""
    if n_bins < 1:
        raise ValueError("n_bins must be at least 1")
    buckets: list[list[Scored]] = [[] for _ in range(n_bins)]
    for s in resolved(scored):
        buckets[min(int(s.call.confidence * n_bins), n_bins - 1)].append(s)
    return [{"lo": round(i / n_bins, 6), "hi": round((i + 1) / n_bins, 6), "n": len(b),
             "mean_confidence": mean_confidence(b), "accuracy": accuracy(b)}
            for i, b in enumerate(buckets)]


def valid_json_rate(calls: Sequence[AgentCall], attempted: int) -> float | None:
    """Calls produced divided by attempts. The runner drops invalid replies, so the attempts
    are passed in: they cannot be recovered from the calls that survived."""
    if attempted <= 0:
        return None
    if len(calls) > attempted:
        raise ValueError(f"{len(calls)} calls but only {attempted} attempts")
    return len(calls) / attempted


Bundles = Mapping[tuple[str, str, date], dict] | Callable[[str, str, date], dict | None]


def evidence_match_rate(calls: Sequence[AgentCall], bundles: Bundles) -> float | None:
    """Share of calls whose evidence values equal the metric bundle they were given.

    `bundles` maps (agent, company_id, as_of) to a bundle, or is a function doing the same.
    A call whose bundle is not available cannot be checked and is left out of the rate. A call
    with no evidence items has nothing that disagrees, so it counts as a match."""
    lookup = bundles.get if isinstance(bundles, Mapping) else bundles
    checked = matched = 0
    for c in calls:
        bundle = lookup((c.agent, c.company_id, c.as_of)) if isinstance(bundles, Mapping) \
            else lookup(c.agent, c.company_id, c.as_of)
        if bundle is None:
            continue
        known = {m["name"]: m["value"] for m in bundle["metrics"]}
        checked += 1
        if all(e.metric in known and abs(known[e.metric] - e.value) <= EVIDENCE_TOLERANCE
               for e in c.evidence):
            matched += 1
    return matched / checked if checked else None
