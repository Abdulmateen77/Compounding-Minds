"""The entry point the replay calls: one agent, one company, one quarter (TASKS handoff 7).

    entry = Entry(gateway, updater)                         # real metrics from Postgres through the gate
    attempt = entry.attempt("fundamentals", "anon_007", date(2019, 6, 30), run_id=run_id)
    attempt.status    # "ok" | "skipped" | "dropped"
    attempt.call      # the AgentCall when status == "ok"

Three outcomes, kept apart on purpose because they mean different things:
  * ok       a valid, evidence-checked call
  * skipped  the metric bundle was not usable (3 or more metrics missing for this company and
             quarter): the agent was never asked. Normal for a recent filer in its early quarters
  * dropped  the model answered but its reply was invalid twice (runner.run_agent logs why).
             Counts against the agent's valid-reply rate

Metrics come from `metrics.get_metrics`, which reads only through the date gate. Set USE_STUBS=1
to use the hand-written stub bundles instead (development before real data is loaded).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from schemas import AgentCall

from .gateway import LLMGateway, ModelUpdater
from .runner import run_agent

log = logging.getLogger("agents.entry")
MetricsFn = Callable[[str, str, date], dict]


def default_metrics_fn() -> MetricsFn:
    if os.environ.get("USE_STUBS") == "1":
        from store.stubs import get_metrics_stub
        return get_metrics_stub
    from metrics import get_metrics
    return get_metrics


@dataclass
class Attempt:
    agent: str
    company_id: str
    as_of: date
    status: str                         # ok | skipped | dropped
    call: AgentCall | None = None
    missing: list[str] = field(default_factory=list)


class Entry:
    def __init__(self, gateway: LLMGateway, updater: ModelUpdater, metrics_fn: MetricsFn | None = None):
        self.gateway, self.updater = gateway, updater
        self.metrics_fn = metrics_fn or default_metrics_fn()

    def attempt(self, agent: str, company_id: str, as_of: date, run_id: str | None = None,
                lessons: list[str] | None = None) -> Attempt:
        bundle = self.metrics_fn(company_id, agent, as_of)
        if not bundle.get("usable", True):      # stub bundles carry no `usable` flag
            log.info("skip %s %s %s: missing %s", agent, company_id, as_of, bundle.get("missing"))
            return Attempt(agent, company_id, as_of, "skipped", missing=list(bundle.get("missing", [])))
        call = run_agent(agent, company_id, as_of, bundle, self.gateway, self.updater, run_id=run_id, lessons=lessons)
        if call is None:
            return Attempt(agent, company_id, as_of, "dropped", missing=list(bundle.get("missing", [])))
        return Attempt(agent, company_id, as_of, "ok", call, list(bundle.get("missing", [])))

    def run(self, agent: str, company_id: str, as_of: date, run_id: str | None = None,
            lessons: list[str] | None = None) -> AgentCall | None:
        """The call, or None if the agent was skipped or dropped. Use `attempt` to tell which."""
        return self.attempt(agent, company_id, as_of, run_id, lessons).call
