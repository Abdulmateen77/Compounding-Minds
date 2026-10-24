"""The four read-only tools an agent may call while it reasons (README 5, BRIEF_HERMES H1).

Why it is shaped this way (this is what keeps the tools leak-proof):

  * One `Tools` object per agent run, with `as_of` fixed when it is built. No tool takes a
    date, so the model can never choose one.
  * A metric series is rebuilt by asking `metrics_fn` at each earlier quarter-end, each at its
    own date. Every point is what an analyst could have known on that day, not a later
    restatement.
  * Outputs carry only relative labels (Q0, Q-1, quarters_ago) and numbers. No filed_date,
    accession, text_ref, ticker, name or calendar year ever leaves this module.
  * Every call spends from one shared budget (about 5 calls per run), because
    `AgentCall.tool_calls` is capped at 5 and a runaway agent must be stopped here.
"""
from __future__ import annotations

import calendar
import functools
import math
import statistics
from dataclasses import dataclass
from datetime import date
from typing import Callable, Sequence

# The locked metric contract (BRIEF_HERMES section 2). It tells get_metric_series and
# peer_compare which agent's bundle a metric lives in.
AGENT_METRICS: dict[str, tuple[str, ...]] = {
    "fundamentals": ("fcf_margin_ttm", "fcf_margin_qoq_change", "operating_margin", "roic",
                     "debt_to_ebitda", "fcf_slope_8q", "capex_to_revenue"),
    "risk": ("interest_coverage", "current_ratio", "cash_runway_quarters", "dividend_cut_history_5y",
             "auditor_changes_5y", "going_concern_hits", "leverage_trend_8q"),
    "scenarios": ("revenue_growth_yoy", "revenue_growth_mean_5y", "revenue_growth_std_5y",
                  "revenue_macro_beta", "gdp_growth_yoy", "unemployment_rate",
                  "yield_curve_10y_2y", "credit_spread_baa"),
}
METRIC_OWNER: dict[str, str] = {m: a for a, names in AGENT_METRICS.items() for m in names}
MACRO_METRICS = ("gdp_growth_yoy", "unemployment_rate", "yield_curve_10y_2y", "credit_spread_baa")

MIN_PEERS = 3        # below this a peer median or percentile would point at one or two named firms
MAX_QUARTERS = 20    # each quarter is a full metrics computation, so a model cannot ask for 1000
MAX_EVENTS = 20


class ToolError(Exception):
    """The model asked for something the tool cannot give. The message says what is valid."""


class ToolBudgetExceeded(ToolError):
    """The run has used all of its tool calls."""


@dataclass
class ToolBudget:
    """Counts calls across all four tools. The runner writes `used` into AgentCall.tool_calls."""

    max_calls: int = 5
    used: int = 0

    def charge(self) -> None:
        # Check before counting, so `used` never passes max_calls (the schema rejects > 5).
        if self.used >= self.max_calls:
            raise ToolBudgetExceeded(
                f"tool budget of {self.max_calls} calls is used up; answer with what you have")
        self.used += 1


def _metered(fn):
    """Charge the budget on every attempt, including a call that then fails validation.

    A typo costs a call, as a metered API would. It also means nothing can loop on bad
    input for free."""
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        self.budget.charge()
        return fn(self, *args, **kwargs)
    return wrapper


# ---- quarter arithmetic -------------------------------------------------------------------

def _quarter_end(year: int, quarter_index: int) -> date:
    month = 3 * (quarter_index + 1)
    return date(year, month, calendar.monthrange(year, month)[1])


def _latest_quarter_end(d: date) -> date:
    """The last calendar quarter-end on or before `d` (d itself when d is a quarter-end)."""
    this = _quarter_end(d.year, (d.month - 1) // 3)
    return this if this <= d else _quarters_back(this, 1)


def _quarters_back(end: date, k: int) -> date:
    """`end` is a quarter-end; return the quarter-end k quarters earlier."""
    year, qi = divmod(end.year * 4 + (end.month // 3 - 1) - k, 4)
    return _quarter_end(year, qi)


def _qindex(d: date) -> int:
    return d.year * 4 + (d.month - 1) // 3


def _label(quarters_back: int) -> str:
    return "Q0" if quarters_back == 0 else f"Q-{quarters_back}"


# ---- small helpers ------------------------------------------------------------------------

def _owner(metric: str) -> str:
    if metric not in METRIC_OWNER:
        raise ToolError(f"unknown metric {metric!r}; valid metrics: {', '.join(sorted(METRIC_OWNER))}")
    return METRIC_OWNER[metric]


def _bounded_int(value, name: str, lo: int, hi: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise ToolError(f"{name} must be a whole number from {lo} to {hi}")
    return value


def _metric_value(bundle: dict, name: str) -> float | None:
    """The metric's value, or None when the bundle does not have it. Never a guess, never NaN."""
    for m in bundle.get("metrics", []):
        if m["name"] == name:
            v = m.get("value")
            if v is None or (isinstance(v, float) and math.isnan(v)):
                return None
            return float(v)
    return None


def _default_sector_lookup() -> tuple[Callable[[str], str], list[str]]:
    from ingest.universe import load_universe  # reads universe.json only, no database
    companies = load_universe()
    sectors = {c["company_id"]: c["sector"] for c in companies}
    return sectors.__getitem__, [c["company_id"] for c in companies]


class Tools:
    """Read-only tools for ONE agent run. Build a fresh one per (agent, company, as_of).

    metrics_fn(company_id, agent, as_of) -> bundle   default: store.stubs.get_metrics_stub.
        Pass the real `metrics.engine.get_metrics` once it lands.
    events_fn(company_id, as_of, forms) -> [Event]   default: store.queries.get_events (the date gate).
    sector_of(company_id) -> str, universe_ids       default: ingest/universe.json.
    """

    def __init__(self, company_id: str, as_of: date,
                 metrics_fn: Callable[[str, str, date], dict] | None = None,
                 events_fn: Callable[[str, date, list[str] | None], Sequence] | None = None,
                 sector_of: Callable[[str], str] | None = None,
                 universe_ids: Sequence[str] | None = None,
                 budget: ToolBudget | None = None):
        if metrics_fn is None:
            from store.stubs import get_metrics_stub as metrics_fn
        if events_fn is None:
            from store.queries import get_events as events_fn
        if sector_of is None or universe_ids is None:
            default_sector, default_ids = _default_sector_lookup()
            sector_of = sector_of or default_sector
            universe_ids = default_ids if universe_ids is None else universe_ids
        self.company_id = company_id
        self.as_of = as_of
        self.budget = budget if budget is not None else ToolBudget()
        self._metrics_fn = metrics_fn
        self._events_fn = events_fn
        self._sector_of = sector_of
        self._universe_ids = tuple(universe_ids)

    @_metered
    def get_metric_series(self, metric: str, n_quarters: int = 8) -> list[dict]:
        """One metric at each of the last `n_quarters` quarter-ends, oldest first (Q-7 ... Q0).

        Q0 is the latest quarter-end on or before `as_of`. A quarter where the metric could
        not be computed has value None."""
        agent = _owner(metric)
        n = _bounded_int(n_quarters, "n_quarters", 1, MAX_QUARTERS)
        latest = _latest_quarter_end(self.as_of)
        series = []
        for back in range(n - 1, -1, -1):
            at = _quarters_back(latest, back)  # each point is asked for at its own date
            series.append({"quarter": _label(back),
                           "value": _metric_value(self._metrics_fn(self.company_id, agent, at), metric)})
        return series

    @_metered
    def get_recent_events(self, forms: list[str] | None = None, n: int = 5) -> list[dict]:
        """The `n` most recent filing events, newest first, as form, item codes and quarters ago.

        quarters_ago counts calendar quarters back from the quarter `as_of` falls in, so for a
        quarter-end as_of, 0 means filed during Q0. filed_date, accession and text_ref are
        left out on purpose: an accession number contains its year."""
        n = _bounded_int(n, "n", 1, MAX_EVENTS)
        if isinstance(forms, str):
            forms = [forms]
        events = self._events_fn(self.company_id, self.as_of, forms)
        newest_first = sorted(events, key=lambda e: e.filed_date, reverse=True)[:n]
        here = _qindex(self.as_of)
        return [{"form": e.form, "items": list(e.items), "quarters_ago": here - _qindex(e.filed_date)}
                for e in newest_first]

    @_metered
    def get_macro_snapshot(self) -> dict:
        """Four macro readings at `as_of`, taken from the scenarios bundle. None when absent."""
        bundle = self._metrics_fn(self.company_id, "scenarios", self.as_of)
        return {name: _metric_value(bundle, name) for name in MACRO_METRICS}

    @_metered
    def peer_compare(self, metric: str) -> dict:
        """Where this company's metric sits among same-sector peers at `as_of`.

        Peers with no value are skipped. With fewer than MIN_PEERS peers the median and
        percentile are None, because with one or two peers they would reveal a named firm.
        The company's own value is not a peer statistic and is always returned.
        percentile is mid-rank, 0 to 100: 50 is the peer median, and higher means a higher
        value, not a better one."""
        agent = _owner(metric)
        own = _metric_value(self._metrics_fn(self.company_id, agent, self.as_of), metric)
        sector = self._sector_of(self.company_id)
        peer_values = []
        for pid in self._universe_ids:
            if pid == self.company_id or self._sector_of(pid) != sector:
                continue
            v = _metric_value(self._metrics_fn(pid, agent, self.as_of), metric)
            if v is not None:
                peer_values.append(v)
        count = len(peer_values)
        if count < MIN_PEERS:
            return {"value": own, "peer_median": None, "peer_count": count, "percentile": None}
        percentile = None
        if own is not None:
            below = sum(v < own for v in peer_values)
            equal = sum(v == own for v in peer_values)
            percentile = round(100 * (below + 0.5 * equal) / count, 1)
        return {"value": own, "peer_median": round(statistics.median(peer_values), 6),
                "peer_count": count, "percentile": percentile}
