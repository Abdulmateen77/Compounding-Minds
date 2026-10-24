"""Held-out harness (README 9): frozen twin vs learned agent vs baselines (vs a frontier model).

Per agent:
  1. TRAIN: replay the train quarters over the train companies with the learning agent.
     A graded wrong call becomes a correction only once its outcome is visible
     (resolution date <= the quarter being replayed), and only if it resolves inside the
     train window. Calls that resolve later are thrown away, never learned from.
  2. FREEZE: learning stops. Held-out companies were never touched.
  3. HELD-OUT: replay the held-out quarters over every company with the frozen twin, the
     learned agent and (optional) a frontier model with no learning, on identical metrics.
  4. SCORE: only cells where every arm produced a resolved grade count (paired), so the
     comparison is like for like. Baselines are scored on the same cells using
     train-window outcomes only.

Nothing here tunes against held-out results: there is no loop that reads them.
Pass a RunStore to save every call, grade and correction (the dashboard reads those).
"""
from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from agents.frozen import FrozenUpdater
from agents.gateway import LLMGateway, ModelUpdater
from agents.reflection import GradedCall, make_corrections
from agents.run_store import RunStore
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


@dataclass(frozen=True)
class Arm:
    """One way of answering: a gateway plus an updater (learned, frozen or frontier)."""
    name: str
    gateway: LLMGateway
    updater: ModelUpdater


@dataclass
class Cell:
    arm: str                     # learned | frozen | frontier
    company_id: str
    as_of: date
    seen_company: bool           # was this company in the train set?
    call: AgentCall | None
    grade: Grade | None
    phase: str = "heldout"       # train | heldout

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
    frontier_version: str | None = None
    corrections_applied: int = 0
    train_calls: int = 0
    train_dropped: int = 0
    held_out_dropped: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    train_outcomes: list[str] = field(default_factory=list)   # resolved inside the train window
    train_cells: list[Cell] = field(default_factory=list)
    cells: list[Cell] = field(default_factory=list)


class _Runner:
    """Runs and grades one call, and saves it if there is a store."""

    def __init__(self, agent: str, metrics_fn: MetricsFn, outcome_fn: OutcomeFn | None, store: RunStore | None):
        self.agent, self.metrics_fn, self.store = agent, metrics_fn, store
        self.grade_fn = (lambda c: grade(c, outcome_fn)) if outcome_fn else grade

    def run(self, arm: Arm, company: str, q: date, m: dict, run_id: str) -> tuple[AgentCall | None, Grade | None]:
        call = run_agent(self.agent, company, q, m, arm.gateway, arm.updater, run_id=run_id)
        if call is None:
            return None, None
        g = self.grade_fn(call)
        if self.store:
            self.store.write_call(call)
            self.store.write_grade(g)
        return call, g


def _train(ev: AgentEval, split: Split, r: _Runner, learned: Arm, frozen: Arm | None, run_id: str) -> None:
    pending: list[tuple[date, GradedCall]] = []

    def apply(ready: list[tuple[date, GradedCall]]) -> None:
        items = [it for _, it in ready]
        corrections = make_corrections(items, learned.gateway) if items else []
        if not corrections:
            return
        ref = learned.updater.submit_corrections(ev.agent, corrections)
        ev.corrections_applied += len(corrections)
        if r.store:
            for c in corrections:
                r.store.write_correction(c, mubit_ref=ref.ref, applied=True)

    for q in split.train_quarters:
        ready = [p for p in pending if p[0] <= q]
        pending = [p for p in pending if p[0] > q]
        apply(ready)
        for company in split.train_companies:
            m = r.metrics_fn(company, ev.agent, q)
            call, g = r.run(learned, company, q, m, run_id)
            ev.train_calls += 1
            ev.train_cells.append(Cell("learned", company, q, True, call, g, phase="train"))
            if frozen is not None:  # only for the accuracy curves; never feeds learning
                fc, fg = r.run(frozen, company, q, m, run_id)
                ev.train_cells.append(Cell("frozen", company, q, True, fc, fg, phase="train"))
            if call is None:
                ev.train_dropped += 1
                continue
            if g.correct is None:
                continue
            due = resolve_by(call, g)
            if due <= split.train_end:
                ev.train_outcomes.append(g.outcome)
            pending.append((due, GradedCall(call, g, m)))

    # Learning stops at the end of the train window. Later-resolving calls are discarded.
    apply([p for p in pending if p[0] <= split.train_end])


def _held_out(ev: AgentEval, split: Split, r: _Runner, arms: list[Arm], run_id: str) -> None:
    seen = set(split.train_companies)
    for q in split.held_out_quarters:
        for company in split.all_companies:
            m = r.metrics_fn(company, ev.agent, q)
            for arm in arms:
                call, g = r.run(arm, company, q, m, run_id)
                if call is None:
                    ev.held_out_dropped[arm.name] += 1
                ev.cells.append(Cell(arm.name, company, q, company in seen, call, g))


def evaluate_agent(agent: str, split: Split, gateway: LLMGateway, learned: ModelUpdater,
                   frozen: ModelUpdater | None = None, metrics_fn: MetricsFn | None = None,
                   outcome_fn: OutcomeFn | None = None, frontier: Arm | None = None,
                   store: RunStore | None = None, train_run_id: str | None = None,
                   heldout_run_id: str | None = None, frozen_in_train: bool = False) -> AgentEval:
    """`frontier`: a larger model with no learning (README 9 stretch), held-out phase only.
    `frozen_in_train`: also run the frozen twin over the train window, for accuracy curves."""
    if metrics_fn is None:
        from store.stubs import get_metrics_stub as metrics_fn  # type: ignore[assignment]
    frozen = frozen or FrozenUpdater(getattr(gateway, "model", None))
    if getattr(learned, "lessons", lambda a: [])(agent):
        raise RuntimeError(f"learned updater already has lessons for {agent!r}; start from an empty memory "
                           "so the held-out comparison is clean")
    train_run_id = train_run_id or str(uuid.uuid4())
    heldout_run_id = heldout_run_id or str(uuid.uuid4())
    learned_arm, frozen_arm = Arm("learned", gateway, learned), Arm("frozen", gateway, frozen)

    ev = AgentEval(agent, SPECS[agent].claim_type, frozen.get_model_version(agent), learned.get_model_version(agent),
                   frontier_version=frontier.updater.get_model_version(agent) if frontier else None)
    r = _Runner(agent, metrics_fn, outcome_fn, store)
    _train(ev, split, r, learned_arm, frozen_arm if frozen_in_train else None, train_run_id)
    ev.learned_version_end = learned.get_model_version(agent)
    _held_out(ev, split, r, [frozen_arm, learned_arm] + ([frontier] if frontier else []), heldout_run_id)
    return ev


def _arms(ev: AgentEval) -> list[str]:
    return [a for a in ("frozen", "learned", "frontier") if any(c.arm == a for c in ev.cells)]


def _paired(ev: AgentEval, segment: str) -> list[dict[str, Cell]]:
    arms = _arms(ev)
    by_key: dict[tuple[str, date], dict[str, Cell]] = {}
    for c in ev.cells:
        by_key.setdefault((c.company_id, c.as_of), {})[c.arm] = c
    out = []
    for cells in by_key.values():
        if not all(a in cells and cells[a].resolved for a in arms):
            continue
        seen = cells["frozen"].seen_company
        if (segment == "seen_companies" and not seen) or (segment == "unseen_companies" and seen):
            continue
        out.append(cells)
    return out


def _delta(learned: dict, frozen: dict) -> dict:
    if not frozen["n"]:
        return {"accuracy": None, "brier": None}
    return {"accuracy": learned["accuracy"] - frozen["accuracy"], "brier": learned["brier"] - frozen["brier"]}


def _rows(cells: list[Cell]) -> list[tuple[str, float, str]]:
    return [(c.call.claim.answer, c.call.claim.probability, c.grade.outcome) for c in cells]


def summarise(ev: AgentEval) -> dict:
    """Plain-dict result for one agent. Negative Brier delta means the learned agent is better."""
    segments = {}
    for seg in SEGMENTS:
        pairs = _paired(ev, seg)
        scored = {a: score(ev.claim_type, _rows([p[a] for p in pairs])) for a in _arms(ev)}
        segments[seg] = {
            "n": len(pairs),
            **scored,
            "baselines": score_baselines(ev.claim_type, [p["frozen"].grade.outcome for p in pairs], ev.train_outcomes),
            "learned_minus_frozen": _delta(scored["learned"], scored["frozen"]),
        }
    return {
        "claim_type": ev.claim_type,
        "frozen_version": ev.frozen_version,
        "learned_version_start": ev.learned_version_start,
        "learned_version_end": ev.learned_version_end,
        "frontier_version": ev.frontier_version,
        "corrections_applied": ev.corrections_applied,
        "train_calls": ev.train_calls,
        "train_dropped": ev.train_dropped,
        "train_resolved_outcomes": len(ev.train_outcomes),
        "held_out_dropped": dict(ev.held_out_dropped),
        "segments": segments,
    }


def snapshots(ev: AgentEval) -> list[dict]:
    """Accuracy and Brier per (phase, arm, quarter) over resolved calls: the dashboard's curves.

    These describe what was eventually graded for each quarter's calls. They are for display
    only; nothing in training reads them.
    """
    groups: dict[tuple[str, str, date], list[Cell]] = defaultdict(list)
    for c in ev.train_cells + ev.cells:
        if c.resolved:
            groups[(c.phase, c.arm, c.as_of)].append(c)
    out = []
    for (phase, arm, q), cells in sorted(groups.items()):
        s = score(ev.claim_type, _rows(cells))
        out.append({"agent": ev.agent, "phase": phase, "arm": arm, "as_of": q, "n": s["n"],
                    "accuracy": s["accuracy"], "brier": s["brier"], "model": cells[-1].call.model})
    return out


def planned_calls(split: Split, n_agents: int, frozen_in_train: bool = False, frontier: bool = False) -> dict:
    """Upper bound on analyst calls (reflection calls come on top, one per correction)."""
    train = len(split.train_companies) * len(split.train_quarters) * (2 if frozen_in_train else 1)
    held = (3 if frontier else 2) * len(split.all_companies) * len(split.held_out_quarters)
    return {"per_agent_train": train, "per_agent_held_out": held,
            "total_analyst_calls": n_agents * (train + held)}
