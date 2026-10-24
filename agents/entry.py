"""The entry point the replay calls: one agent, one company, one quarter (TASKS handoff 7).

    entry = Entry(gateway, updater)                         # real metrics from Postgres through the gate
    attempt = entry.attempt("fundamentals", "anon_007", date(2019, 6, 30), run_id=run_id)
    attempt.status    # "ok" | "skipped" | "dropped"
    attempt.call      # the AgentCall when status == "ok"

Four outcomes, kept apart on purpose because they mean different things:
  * ok       a valid, evidence-checked call
  * skipped  the metric bundle was not usable (3 or more metrics missing for this company and
             quarter): the agent was never asked. Normal for a recent filer in its early quarters
  * dropped  the model answered but its reply was invalid twice (runner.run_agent logs why).
             Counts against the agent's valid-reply rate
  * blocked  the prompt contained a company name, ticker, year or accession number (agents/leakcheck.py),
             so it was never sent. This should never happen; if it does, a lesson or a metric name
             leaked and must be fixed, not retried

Metrics come from `metrics.get_metrics`, which reads only through the date gate. Set USE_STUBS=1
to use the hand-written stub bundles instead (development before real data is loaded).
"""
from __future__ import annotations

import logging
import os
import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from schemas import AgentCall

from .gateway import LLMGateway, ModelUpdater
from .leakcheck import find_leaks
from .runner import build_messages, run_agent

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
    status: str                         # ok | skipped | dropped | blocked
    call: AgentCall | None = None
    missing: list[str] = field(default_factory=list)
    leaks: list[str] = field(default_factory=list)   # what blocked the prompt, when status == blocked


def attempt_bundle(agent: str, company_id: str, as_of: date, bundle: dict, gateway: LLMGateway,
                   updater: ModelUpdater, run_id: str | None = None, lessons: list[str] | None = None) -> Attempt:
    """The shared core: given a metric bundle, skip it, block it, or ask the model."""
    missing = list(bundle.get("missing", []))
    if not bundle.get("usable", True):          # stub bundles carry no `usable` flag
        log.info("skip %s %s %s: missing %s", agent, company_id, as_of, missing)
        return Attempt(agent, company_id, as_of, "skipped", missing=missing)
    # Check the exact message the model would see, with the lessons it would be given.
    if lessons is None:
        lessons = getattr(updater, "lessons", lambda a: [])(agent)
    leaks = find_leaks(build_messages(agent, company_id, as_of, bundle, lessons)[1]["content"])
    if leaks:
        log.error("BLOCKED %s %s %s: prompt would leak %s", agent, company_id, as_of, leaks)
        return Attempt(agent, company_id, as_of, "blocked", leaks=leaks)
    call = run_agent(agent, company_id, as_of, bundle, gateway, updater, run_id=run_id, lessons=lessons)
    return Attempt(agent, company_id, as_of, "ok" if call else "dropped", call, missing)


# How often each outcome has happened through `replay_runner` in this process. The replay can print
# it at the end: a high "dropped" or any "blocked" is worth looking at before trusting the run.
OUTCOMES: Counter = Counter()
_lock = threading.Lock()   # the replay may call replay_runner from several threads


def replay_runner(agent: str, company_id: str, as_of: date, *, metrics: dict, gateway: LLMGateway,
                  updater: ModelUpdater, run_id: str | None) -> AgentCall | None:
    """The runner for B's replay (`python -m grader.replay --runner agents.entry:replay_runner`).

    Same keyword signature as grader.replay.stub_backed_runner, plus the two safeguards: a bundle
    with too much missing is skipped, and a prompt that would leak a name, ticker or year is blocked.
    Lessons come from the updater, so a learned arm (lessons) and a frozen arm (none) really differ.
    """
    a = attempt_bundle(agent, company_id, as_of, metrics, gateway, updater, run_id=run_id)
    with _lock:
        OUTCOMES[a.status] += 1
    return a.call


class Entry:
    def __init__(self, gateway: LLMGateway, updater: ModelUpdater, metrics_fn: MetricsFn | None = None):
        self.gateway, self.updater = gateway, updater
        self.metrics_fn = metrics_fn or default_metrics_fn()

    def attempt(self, agent: str, company_id: str, as_of: date, run_id: str | None = None,
                lessons: list[str] | None = None) -> Attempt:
        bundle = self.metrics_fn(company_id, agent, as_of)
        return attempt_bundle(agent, company_id, as_of, bundle, self.gateway, self.updater, run_id, lessons)

    def run(self, agent: str, company_id: str, as_of: date, run_id: str | None = None,
            lessons: list[str] | None = None) -> AgentCall | None:
        """The call, or None if the agent was skipped or dropped. Use `attempt` to tell which."""
        return self.attempt(agent, company_id, as_of, run_id, lessons).call
