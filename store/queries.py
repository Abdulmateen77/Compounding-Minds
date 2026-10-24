"""The ONLY place point-in-time visibility is decided (README 4.4).

No agent, metric or tool reads tables directly. Rules:
  * a row is visible at `as_of` iff filed_date (vintage_date for macro) <= as_of
  * a restated fact is a new row; we return the latest visible row per
    (concept, period_end)
  * never filter or order by period_end to decide visibility

The backend only supplies candidate rows; `_visible_*` below decide visibility, so
an in-memory backend (tests, stubs) and a Postgres backend share the same rule.
Postgres backend: TODO (owner A). Its job is `candidate rows -> list[dict]`.
"""
from __future__ import annotations

from datetime import date
from typing import Protocol

from schemas import Event, Fact, Point


class Backend(Protocol):
    def facts(self, company_id: str, concept: str) -> list[dict]: ...
    def events(self, company_id: str) -> list[dict]: ...
    def macro(self, series_id: str) -> list[dict]: ...


class InMemoryBackend:
    def __init__(self, facts=(), events=(), macro=()):
        self._facts, self._events, self._macro = list(facts), list(events), list(macro)

    def facts(self, company_id, concept):
        return [r for r in self._facts if r["company_id"] == company_id and r["concept"] == concept]

    def events(self, company_id):
        return [r for r in self._events if r["company_id"] == company_id]

    def macro(self, series_id):
        return [r for r in self._macro if r["series_id"] == series_id]


_backend: Backend = InMemoryBackend()


def set_backend(backend: Backend) -> None:
    global _backend
    _backend = backend


def _latest_per_key(rows: list[dict], key_fields: tuple[str, ...], date_field: str, as_of: date) -> list[dict]:
    best: dict[tuple, dict] = {}
    for r in rows:
        if r[date_field] > as_of:  # the gate
            continue
        k = tuple(r[f] for f in key_fields)
        if k not in best or r[date_field] > best[k][date_field]:
            best[k] = r
    return list(best.values())


def get_facts(company_id: str, concept: str, as_of: date) -> list[Fact]:
    rows = _latest_per_key(_backend.facts(company_id, concept), ("concept", "period_end"), "filed_date", as_of)
    rows.sort(key=lambda r: (r["filed_date"], r["period_end"]))  # order by filing, not period
    return [Fact(**r) for r in rows]


def get_events(company_id: str, as_of: date, forms: list[str] | None = None) -> list[Event]:
    rows = [r for r in _backend.events(company_id) if r["filed_date"] <= as_of]  # the gate
    if forms:
        rows = [r for r in rows if r["form"] in forms]
    rows.sort(key=lambda r: r["filed_date"])
    return [Event(**r) for r in rows]


def get_macro(series_id: str, as_of: date) -> list[Point]:
    rows = _latest_per_key(_backend.macro(series_id), ("series_id", "obs_date"), "vintage_date", as_of)
    rows.sort(key=lambda r: r["obs_date"])
    return [Point(**r) for r in rows]
