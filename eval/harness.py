"""Held-out harness (README 9): frozen twin vs learned agent vs baselines.

Per agent:
  1. TRAIN: replay the train quarters over the train companies with the learning agent.
     A graded wrong call becomes a correction only once its outcome is visible
     (resolution date <= the quarter being replayed), and only if it resolves inside the
     train window. Calls that resolve later are thrown away, never learned from.
  2. FREEZE: learning stops. Held-out companies were never touched.
  3. HELD-OUT: replay the held-out quarters over every company with both the frozen twin
     and the learned agent, on identical metrics. Grade both.
  4. SCORE: only cells where both arms produced a resolved grade count (paired), so the
     comparison is like for like. Baselines are scored on the same cells using
     train-window outcomes only.

Nothing here tunes against held-out results: there is no loop that reads them.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from agents.frozen import FrozenUpdater
from agents.gateway import LLMGateway, ModelUpdater
from agents.reflection import GradedCall, make_corrections
from agents.runner import run_agent
from agents.specs import SPECS
from grader.grade import OutcomeFn, grade
from schemas import AgentCall, Grade

from .baselines import score, score_baselines
from .split import HORIZON_QUARTERS, Split, add_quarters

log = logging.getLogger("eval.harness")

MetricsFn = Callable[[str, str, date], dict]
SEGMENTS = ("all_companies", "seen_companies", "unseen_companies")


def resolve_by(call: AgentCall, g: Grade) -> date:
    """When the outcome became visible: the grader's resolution date, else the horizon."""
    return g.resolution_date or add_quarters(call.as_of, HORIZON_QUARTERS[call.horizon])


@dataclass
class Cell:
    arm: str                     # frozen | learned
    company_id: str
    as_of: date
    seen_company: bool           # was this company in the train set?
    call: AgentCall | None
    grade: Grade | None

    @property
    def resolved(self) -> bool:
        return self.call is not None and self.grade is not None and self.grade.correct is not None


@dataclass
class AgentEval:
    agent: str
    claim_type: str
    frozen_version: str
    learned_version_start: str
    learned_version_end: str = ""
    corrections_applied: int = 0
    train_calls: int = 0
    train_dropped: int = 0
    held_out_dropped: dict[str, int] = field(default_factory=lambda: {"frozen": 0, "learned": 0})
    train_outcomes: list[str] = field(default_factory=list)   # resolved inside the train window
    cells: list[Cell] = field(default_factory=list)


def _train(ev: AgentEval, split: Split, gateway: LLMGateway, learned: ModelUpdater,
           metrics_fn: MetricsFn, outcome_fn: OutcomeFn | None) -> None:
    agent = ev.agent
    grade_fn = (lambda c: grade(c, outcome_fn)) if outcome_fn else grade
    pending: list[tuple[date, GradedCall]] = []

    def apply(ready: list[tuple[date, GradedCall]]) -> None:
        items = [it for _, it in ready]
        corrections = make_corrections(items, gateway) if items else []
        if corrections:
            learned.submit_corrections(agent, corrections)
            ev.corrections_applied += len(corrections)

    for q in split.train_quarters:
        ready = [p for p in pending if p[0] <= q]
        pending = [p for p in pending if p[0] > q]
        apply(ready)
        for company in split.train_companies:
            m = metrics_fn(company, agent, q)
            call = run_agent(agent, company, q, m, gateway, learned)
            ev.train_calls += 1
            if call is None:
                ev.train_dropped += 1
                continue
            g = grade_fn(call)
            if g.correct is None:
                continue
            due = resolve_by(call, g)
            if due <= split.train_end:
                ev.train_outcomes.append(g.outcome)
            pending.append((due, GradedCall(call, g, m)))

    # Learning stops at the end of the train window. Later-resolving calls are discarded.
    apply([p for p in pending if p[0] <= split.train_end])


def _held_out(ev: AgentEval, split: Split, gateway: LLMGateway, frozen: ModelUpdater, learned: ModelUpdater,
              metrics_fn: MetricsFn, outcome_fn: OutcomeFn | None) -> None:
    agent = ev.agent
    grade_fn = (lambda c: grade(c, outcome_fn)) if outcome_fn else grade
    seen = set(split.train_companies)
    for q in split.held_out_quarters:
        for company in split.all_companies:
            m = metrics_fn(company, agent, q)
            for arm, upd in (("frozen", frozen), ("learned", learned)):
                call = run_agent(agent, company, q, m, gateway, upd)
                if call is None:
                    ev.held_out_dropped[arm] += 1
                ev.cells.append(Cell(arm, company, q, company in seen, call,
                                     grade_fn(call) if call is not None else None))


def evaluate_agent(agent: str, split: Split, gateway: LLMGateway, learned: ModelUpdater,
                   frozen: ModelUpdater | None = None, metrics_fn: MetricsFn | None = None,
                   outcome_fn: OutcomeFn | None = None) -> AgentEval:
    if metrics_fn is None:
        from store.stubs import get_metrics_stub as metrics_fn  # type: ignore[assignment]
    frozen = frozen or FrozenUpdater(getattr(gateway, "model", None))
    if getattr(learned, "lessons", lambda a: [])(agent):
        raise RuntimeError(f"learned updater already has lessons for {agent!r}; start from an empty memory "
                           "so the held-out comparison is clean")
    ev = AgentEval(agent, SPECS[agent].claim_type, frozen.get_model_version(agent), learned.get_model_version(agent))
    _train(ev, split, gateway, learned, metrics_fn, outcome_fn)
    ev.learned_version_end = learned.get_model_version(agent)
    _held_out(ev, split, gateway, frozen, learned, metrics_fn, outcome_fn)
    return ev


def _paired(ev: AgentEval, segment: str) -> list[tuple[Cell, Cell]]:
    by_key: dict[tuple[str, date], dict[str, Cell]] = {}
    for c in ev.cells:
        by_key.setdefault((c.company_id, c.as_of), {})[c.arm] = c
    pairs = []
    for arms in by_key.values():
        f, l = arms.get("frozen"), arms.get("learned")
        if not (f and l and f.resolved and l.resolved):
            continue
        if segment == "seen_companies" and not f.seen_company:
            continue
        if segment == "unseen_companies" and f.seen_company:
            continue
        pairs.append((f, l))
    return pairs


def _delta(learned: dict, frozen: dict) -> dict:
    if not frozen["n"]:
        return {"accuracy": None, "brier": None}
    return {"accuracy": learned["accuracy"] - frozen["accuracy"], "brier": learned["brier"] - frozen["brier"]}


def summarise(ev: AgentEval) -> dict:
    """Plain-dict result for one agent. Negative Brier delta means the learned agent is better."""
    segments = {}
    for seg in SEGMENTS:
        pairs = _paired(ev, seg)
        rows = {arm: [(c.call.claim.answer, c.call.claim.probability, c.grade.outcome) for c in cells]
                for arm, cells in (("frozen", [p[0] for p in pairs]), ("learned", [p[1] for p in pairs]))}
        frozen, learned = score(ev.claim_type, rows["frozen"]), score(ev.claim_type, rows["learned"])
        segments[seg] = {
            "n": len(pairs),
            "frozen": frozen,
            "learned": learned,
            "baselines": score_baselines(ev.claim_type, [f.grade.outcome for f, _ in pairs], ev.train_outcomes),
            "learned_minus_frozen": _delta(learned, frozen),
        }
    return {
        "claim_type": ev.claim_type,
        "frozen_version": ev.frozen_version,
        "learned_version_start": ev.learned_version_start,
        "learned_version_end": ev.learned_version_end,
        "corrections_applied": ev.corrections_applied,
        "train_calls": ev.train_calls,
        "train_dropped": ev.train_dropped,
        "train_resolved_outcomes": len(ev.train_outcomes),
        "held_out_dropped": ev.held_out_dropped,
        "segments": segments,
    }


def planned_calls(split: Split, n_agents: int) -> dict:
    """Upper bound on analyst calls (reflection calls come on top, one per correction)."""
    train = len(split.train_companies) * len(split.train_quarters)
    held = 2 * len(split.all_companies) * len(split.held_out_quarters)
    return {"per_agent_train": train, "per_agent_held_out": held,
            "total_analyst_calls": n_agents * (train + held)}
