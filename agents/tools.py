"""Read-only drill-down tools for agents (README 5 "MCP tools"), capped at MAX_TOOL_CALLS a run.

The agent asks for a tool by replying {"tool": "<name>", "args": {...}} and gets the result in
the next user message. `MetricsToolbox` answers from the same point-in-time sources the agents
already use, so nothing here can see past `as_of`:

    get_metric_series(metric, n_quarters)   the metric at earlier quarters, named <metric>@Q-k
    get_recent_events(forms)                filings visible at as_of, dated only as Q-k
    get_macro_snapshot()                    latest visible vintage per macro series

Person A's MCP servers (tools/) can replace this class later behind the same `Toolbox` API.
Every number a tool returns is Python's, so an agent may cite it as evidence.
"""
from __future__ import annotations

import calendar
from datetime import date
from typing import Callable

MAX_TOOL_CALLS = 5
MAX_SERIES_QUARTERS = 8
MACRO_SERIES = ("GDP", "UNRATE", "T10Y2Y", "BAA10Y")

MetricsFn = Callable[[str, str, date], dict]


def quarters_back(d: date, k: int) -> date:
    idx = d.year * 4 + (d.month - 1) // 3 - k
    year, q = divmod(idx, 4)
    month = q * 3 + 3
    return date(year, month, calendar.monthrange(year, month)[1])


def _quarters_ago(as_of: date, d: date) -> int:
    return (as_of.year * 4 + (as_of.month - 1) // 3) - (d.year * 4 + (d.month - 1) // 3)


class ToolError(ValueError):
    pass


class Toolbox:
    def specs(self) -> list[str]:
        """One line per tool for the prompt: name(args): what it returns."""
        raise NotImplementedError

    def call(self, name: str, args: dict, company_id: str, agent: str, as_of: date) -> list[dict]:
        """Rows: {"name", "value", "unit"} for numbers, or {"text"} for non-numeric facts."""
        raise NotImplementedError


class MetricsToolbox(Toolbox):
    def __init__(self, metrics_fn: MetricsFn, use_store: bool = True):
        self.metrics_fn, self.use_store = metrics_fn, use_store

    def specs(self) -> list[str]:
        out = [f"get_metric_series(metric, n_quarters<={MAX_SERIES_QUARTERS}): that metric at earlier quarters, named <metric>@Q-k"]
        if self.use_store:
            out += ["get_recent_events(forms): filings visible now, e.g. forms=[\"8-K\"]",
                    "get_macro_snapshot(): latest visible value of GDP, UNRATE, T10Y2Y, BAA10Y"]
        return out

    def call(self, name, args, company_id, agent, as_of):
        args = args or {}
        if name == "get_metric_series":
            metric = str(args.get("metric", ""))
            n = int(args.get("n_quarters", 4))
            if not 1 <= n <= MAX_SERIES_QUARTERS:
                raise ToolError(f"n_quarters must be 1..{MAX_SERIES_QUARTERS}")
            rows = []
            for k in range(1, n + 1):
                bundle = self.metrics_fn(company_id, agent, quarters_back(as_of, k))
                hit = next((m for m in bundle["metrics"] if m["name"] == metric), None)
                if hit is None:
                    raise ToolError(f"unknown metric {metric!r}")
                rows.append({"name": f"{metric}@Q-{k}", "value": hit["value"], "unit": hit["unit"]})
            return rows
        if self.use_store and name == "get_recent_events":
            from store.queries import get_events
            forms = args.get("forms") or None
            evs = get_events(company_id, as_of, forms=forms)[-10:]
            return [{"text": f"{e.form} items {','.join(e.items) or '-'} filed Q-{_quarters_ago(as_of, e.filed_date)}"}
                    for e in evs]
        if self.use_store and name == "get_macro_snapshot":
            from store.queries import get_macro
            rows = []
            for sid in MACRO_SERIES:
                pts = get_macro(sid, as_of)
                if pts:
                    latest = max(pts, key=lambda p: p.obs_date)
                    rows.append({"name": f"macro_{sid}", "value": latest.value, "unit": ""})
            return rows
        raise ToolError(f"unknown tool {name!r}")


def format_rows(name: str, rows: list[dict]) -> str:
    if not rows:
        return f"TOOL RESULT {name}: (no data)"
    lines = [f"- {r['name']} = {r['value']} {r.get('unit', '')}".rstrip() if "name" in r else f"- {r['text']}" for r in rows]
    return f"TOOL RESULT {name}:\n" + "\n".join(lines)
