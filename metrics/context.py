"""Everything a metric needs about one company at one `as_of`, read through the date gate only.

A `Context` is built per (company, as_of). It caches each concept's quarters and exposes:

  * the QUARTER TIMELINE: the company's revenue quarter ends, oldest first. Q0 is the last one.
    Every other series (cash flow, balance sheet) is read at those same dates.
  * `ttm`, `quarter`, `balance`: values at a timeline date, each returned as a `Result` that
    carries the filing accessions it was computed from (so every metric can be traced).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from schemas import Event, Fact
from store import queries
from store.concepts import CONCEPTS

from .quarters import Q, discrete_quarters, instants

# Consecutive quarter ends are about 91 days apart (52/53 week calendars vary a little).
MIN_GAP, MAX_GAP = 75, 110


@dataclass(frozen=True)
class Result:
    value: float
    inputs: frozenset[str] = field(default_factory=frozenset)

    def __add__(self, other: "Result") -> "Result":
        return Result(self.value + other.value, self.inputs | other.inputs)


def combine(value: float, *parts: "Result | None") -> Result:
    """A new value that depends on several Results: its inputs are theirs together."""
    inputs: frozenset[str] = frozenset()
    for p in parts:
        if p is not None:
            inputs |= p.inputs
    return Result(value, inputs)


class Context:
    def __init__(self, company_id: str, as_of: date):
        self.company_id = company_id
        self.as_of = as_of
        self._facts: dict[str, list[Fact]] = {}
        self._quarters: dict[str, dict[date, Q]] = {}
        self._timeline: list[date] | None = None
        self._macro: dict[str, dict[date, float]] = {}
        self._events: list[Event] | None = None

    # ---- raw access (always through the gate)
    def facts(self, concept: str) -> list[Fact]:
        if concept not in self._facts:
            self._facts[concept] = queries.get_facts(self.company_id, concept, self.as_of)
        return self._facts[concept]

    def has(self, concept: str) -> bool:
        """True if the company has EVER reported this concept (visible at as_of)."""
        return bool(self.facts(concept))

    def quarters(self, concept: str) -> dict[date, Q]:
        if concept not in self._quarters:
            fs = self.facts(concept)
            self._quarters[concept] = (instants(fs) if CONCEPTS[concept].kind == "instant"
                                       else discrete_quarters(fs))
        return self._quarters[concept]

    def events(self) -> list[Event]:
        if self._events is None:
            self._events = queries.get_events(self.company_id, self.as_of)
        return self._events

    def macro(self, series_id: str) -> dict[date, float]:
        """obs_date -> value, as known at as_of (the latest vintage per observation)."""
        if series_id not in self._macro:
            self._macro[series_id] = {p.obs_date: p.value for p in queries.get_macro(series_id, self.as_of)}
        return self._macro[series_id]

    # ---- the timeline
    @property
    def timeline(self) -> list[date]:
        """Revenue quarter ends, oldest first. Empty if the company has no usable revenue."""
        if self._timeline is None:
            self._timeline = sorted(self.quarters("revenue"))
        return self._timeline

    @property
    def q0(self) -> date | None:
        return self.timeline[-1] if self.timeline else None

    def back(self, end: date, n: int) -> date | None:
        """The quarter end n quarters before `end` on the timeline, if the chain is unbroken."""
        tl = self.timeline
        if end not in tl:
            return None
        i = tl.index(end)
        if i - n < 0:
            return None
        for a, b in zip(tl[i - n:i], tl[i - n + 1:i + 1]):
            if not MIN_GAP <= (b - a).days <= MAX_GAP:
                return None
        return tl[i - n]

    def window(self, end: date, n: int) -> list[date] | None:
        """The n quarter ends ending at `end` (oldest first), or None if there are not n in a row."""
        first = self.back(end, n - 1)
        if first is None:
            return None
        tl = self.timeline
        return tl[tl.index(first):tl.index(end) + 1]

    # ---- values at timeline dates
    def quarter(self, concept: str, end: date) -> Result | None:
        q = self.quarters(concept).get(end)
        return Result(q.value, q.accessions) if q else None

    def balance(self, concept: str, end: date) -> Result | None:
        return self.quarter(concept, end)

    def ttm(self, concept: str, end: date) -> Result | None:
        w = self.window(end, 4)
        if w is None:
            return None
        parts = [self.quarter(concept, e) for e in w]
        if any(p is None for p in parts):
            return None
        total = parts[0]
        for p in parts[1:]:
            total = total + p
        return total

    def zero_if_never_reported(self, concept: str) -> Result | None:
        """For concepts a company may legitimately not have (dividends, interest, debt): a company
        that has NEVER reported the concept is treated as zero. A company that has reported it but
        not at this date is missing data, not zero (returns None)."""
        return Result(0.0) if not self.has(concept) else None
