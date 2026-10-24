"""Replay orchestrator (TASKS B3): advance one quarter at a time, 2018Q1 to 2024Q4.

Per quarter T (as_of = T):
  1. every agent calls every company, for three arms: learned, frozen, baseline
  2. a call is graded only when its outcome is visible at T (point-in-time); the grader's
     own resolution date is checked too, and a grade that needs data after T is discarded
  3. LEARNED arm only: wrong graded calls from the TRAIN window become corrections, go to the
     ModelUpdater, and change that agent's model version for quarter T+1
  4. one snapshot per agent and arm (calls graded in T, how many were right, mean Brier)

Learning rules (README 9): corrections come only from calls made in 2018-2022 that resolved by
2022-12-31, on non-held-out companies. From 2023 the learned arm keeps calling but its updater is
never fed again, so any gap to the frozen arm in 2023-2024 comes from train-window lessons.

Arms
  learned   the agent plus the ModelUpdater (MubitUpdater live, FakeModelUpdater offline: FALLBACK)
  frozen    same prompts and model, FrozenUpdater: never learns
  baseline  no LLM: always-yes (binary) / always-base (bucket), fully confident

`runs` rows: one per (arm, kind), run_id "<tag>-<arm>-<train|heldout>".

Determinism: the Anthropic API stopped accepting `temperature` (400 on every model from
2026-10-21), so replay cannot pin temperature 0. Determinism comes from the reply cache instead:
CachingGateway keys on prompt hash + gateway model + the agent's model version. Run once with
live calls, then re-run with --replay-only and get identical output with zero API calls.

Run (resumable; re-run the same command after a crash):
    python -m grader.replay --offline --companies 5 --quarters 2019Q1:2019Q4
    python -m grader.replay --offline --companies 50 --quarters 2018Q1:2024Q4 --settle 4

THE ONE SWAP POINT for Person A's runner is `resolve_runner()` below. By default it uses
agents.runner.run_agent with stub metrics (eval.metrics_source.metrics_fn).
"""
from __future__ import annotations

import argparse
import importlib
import inspect
import json
import logging
import re
import sys
import tempfile
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

from agents.cache import CachingGateway
from agents.frozen import FrozenUpdater
from agents.gateway import FakeModelUpdater, LLMGateway, ModelUpdater
from agents.reflection import GradedCall
from agents.reflection import make_corrections as default_make_corrections
from agents.run_store import RunStore, open_store
from agents.specs import SPECS
from eval.baselines import naive_prediction
from eval.split import HORIZON_QUARTERS, TRAIN_YEARS, add_quarters, pick_held_out, quarter_ends
from grader.grade import OutcomeFn, grade
from schemas import AgentCall, Claim, Correction, Grade

log = logging.getLogger("grader.replay")

ARMS = ("learned", "frozen", "baseline")
DEFAULT_AGENTS = ("fundamentals", "risk", "scenarios")
TRAIN_END = date(TRAIN_YEARS[1], 12, 31)
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "data" / "runs"

MetricsFn = Callable[[str, str, date], dict]
# (agent, company_id, as_of, *, metrics, gateway, updater, run_id) -> AgentCall | None
Runner = Callable[..., "AgentCall | None"]


# ---------------------------------------------------------------- swap point for Person A

def stub_backed_runner(agent, company_id, as_of, *, metrics, gateway, updater, run_id):
    from agents.runner import run_agent
    return run_agent(agent, company_id, as_of, metrics, gateway, updater, run_id=run_id)


def resolve_runner(spec: str | None = None) -> Runner:
    """`spec` is "package.module:function" for Person A's runner; None -> the stub-backed one.

    A swapped-in function must accept the keyword signature of `stub_backed_runner`. If A's
    `run_agent(company_id, as_of)` has a different shape, wrap it in a function of that shape.
    """
    if not spec:
        return stub_backed_runner
    mod, _, fn = spec.partition(":")
    return getattr(importlib.import_module(mod), fn)


def resolve_make_corrections() -> Callable:
    """Returns make(items: list[GradedCall], gateway) -> list[Correction].

    Preferred: grader.corrections (pure-Python selection, cap and error_type), with the lesson text
    written by the reflection LLM (agents.reflection.reflect, through the gateway) and the
    template lesson as fallback. If grader.corrections is absent: agents.reflection.make_corrections.
    """
    try:
        from grader import corrections as gc
        from grader.corrections import default_lesson
        from agents.reflection import reflect
    except ImportError:
        return default_make_corrections

    def make(items: list[GradedCall], gateway) -> list[Correction]:
        by_id = {i.call.call_id: i for i in items}

        def lesson_fn(call, g, error_type):
            r = reflect(by_id[call.call_id], gateway)
            return r.lesson if r is not None else default_lesson(call, g, error_type)

        return gc.make_corrections([(i.call, i.grade) for i in items],
                                   metrics={i.call.call_id: i.metrics for i in items}, lesson_fn=lesson_fn)
    return make


# ---------------------------------------------------------------- helpers

def parse_quarters(spec: str) -> list[date]:
    """'2018Q1:2024Q4' (inclusive range) or '2019Q1,2019Q2' (list)."""
    def one(tok: str) -> date:
        m = re.fullmatch(r"(\d{4})Q([1-4])", tok.strip().upper())
        if not m:
            raise ValueError(f"bad quarter {tok!r}, expected like 2019Q3")
        return add_quarters(date(int(m.group(1)), 3, 31), int(m.group(2)) - 1)
    if ":" in spec:
        a, b = (one(t) for t in spec.split(":"))
        out, d = [], a
        while d <= b:
            out.append(d)
            d = add_quarters(d, 1)
        return out
    return [one(t) for t in spec.split(",")]


def kind_for(as_of: date) -> str:
    return "train" if as_of <= TRAIN_END else "heldout"


def resolve_by(call: AgentCall, g: Grade | None = None) -> date:
    """When the outcome can first be known: horizon end, or the grader's own resolution date."""
    h = add_quarters(call.as_of, HORIZON_QUARTERS[call.horizon])
    return max(h, g.resolution_date) if g is not None and g.resolution_date else h


def baseline_call(agent: str, company_id: str, as_of: date, run_id: str) -> AgentCall:
    spec = SPECS[agent]
    ans, p = naive_prediction(spec.claim_type)
    return AgentCall(call_id=str(uuid.uuid4()), run_id=run_id, agent=agent, company_id=company_id, as_of=as_of,
                     horizon=spec.horizon,
                     claim=Claim(type=spec.claim_type, question_id=spec.question_id, answer=ans, probability=p),
                     confidence=p, reasoning=[], evidence=[], tool_calls=0, model="baseline:naive")


def write_snapshot_compat(store: RunStore, run_id, agent, variant, as_of, n_calls, n_correct, accuracy, brier, model):
    """Call run_store.write_snapshot with its NEW signature, or the old (arm, n) one if not landed yet."""
    params = inspect.signature(store.write_snapshot).parameters
    if "n_correct" in params:
        store.write_snapshot(run_id, agent, variant, as_of, n_calls, n_correct, accuracy, brier, model)
    else:
        store.write_snapshot(run_id, agent, variant, as_of, n_calls, accuracy, brier, model)


@dataclass
class Pending:
    call: AgentCall
    metrics: dict


@dataclass
class Arm:
    variant: str
    gateway: LLMGateway | None
    updater: ModelUpdater | None
    pending: dict[str, Pending] = field(default_factory=dict)  # call_id -> not yet graded
    calls: dict[tuple, AgentCall] = field(default_factory=dict)  # (agent, company, as_of) -> call

    @property
    def model_label(self) -> Callable[[str], str]:
        return (lambda a: self.updater.get_model_version(a)) if self.updater else (lambda a: "baseline:naive")


@dataclass
class ReplayResult:
    quarters_done: list[date] = field(default_factory=list)
    n_calls: int = 0
    n_graded: int = 0
    n_corrections: int = 0
    dropped: int = 0
    versions: dict[str, dict[str, str]] = field(default_factory=dict)  # arm -> agent -> final version


# ---------------------------------------------------------------- the replay

class Replay:
    def __init__(self, companies: list[str], agents: list[str], store: RunStore, *, tag: str,
                 gateways: dict[str, LLMGateway], updaters: dict[str, ModelUpdater],
                 outcome_fn: OutcomeFn, metrics_fn: MetricsFn, runner: Runner | None = None,
                 held_out_companies: list[str] | None = None, state_path: Path | None = None,
                 make_corrections: Callable | None = None, fallback: bool = False):
        self.companies, self.agents, self.store, self.tag = companies, agents, store, tag
        self.outcome_fn, self.metrics_fn = outcome_fn, metrics_fn
        self.runner = runner or resolve_runner()
        self.make_corrections = make_corrections or resolve_make_corrections()
        self.held_out = set(held_out_companies or [])
        self.state_path, self.fallback = state_path, fallback
        self.arms = {"learned": Arm("learned", gateways["learned"], updaters["learned"]),
                     "frozen": Arm("frozen", gateways["frozen"], updaters["frozen"]),
                     "baseline": Arm("baseline", None, None)}
        self.done: set[str] = set()
        self._run_to_arm: dict[str, str] = {}
        self._resume()

    # run ids -------------------------------------------------------------
    def run_id(self, arm: str, kind: str) -> str:
        return f"{self.tag}-{arm}-{kind}"

    def _start_runs(self, kinds: set[str]) -> None:
        for arm in ARMS:
            for kind in kinds:
                rid = self.run_id(arm, kind)
                self._run_to_arm[rid] = arm
                self.store.start_run(rid, kind, {
                    "tag": self.tag, "variant": arm, "companies": len(self.companies), "agents": self.agents,
                    "held_out_companies": sorted(self.held_out), "train_end": TRAIN_END.isoformat(),
                    "learning": "train-window corrections only" if arm == "learned" else "none",
                    "updater_fallback": bool(self.fallback and arm == "learned"),
                    "determinism": "reply cache keyed by prompt hash + model version (no temperature param)"})

    # resume --------------------------------------------------------------
    def _resume(self) -> None:
        if self.state_path and self.state_path.exists():
            self.done = set(json.loads(self.state_path.read_text()).get("done_quarters", []))
        rows = getattr(self.store, "rows", None)
        if rows is None:
            return
        for kind in ("train", "heldout"):
            for arm in ARMS:
                self._run_to_arm[self.run_id(arm, kind)] = arm
        graded = {r["call_id"] for r in rows("grades")}
        for r in rows("calls"):
            arm = self._run_to_arm.get(r["run_id"])
            if arm is None:
                continue
            call = AgentCall.model_validate(r["payload"])
            self.arms[arm].calls[(call.agent, call.company_id, call.as_of)] = call
            if call.call_id not in graded:
                a = self.arms[arm]
                a.pending[call.call_id] = Pending(call, self.metrics_fn(call.company_id, call.agent, call.as_of))

    def _checkpoint(self, as_of: date) -> None:
        self.done.add(as_of.isoformat())
        self.store.flush() if hasattr(self.store, "flush") else None
        if self.state_path:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps({"tag": self.tag, "done_quarters": sorted(self.done)}))

    # one quarter ---------------------------------------------------------
    def step(self, as_of: date, make_calls: bool = True, res: ReplayResult | None = None) -> None:
        res = res if res is not None else ReplayResult()
        if as_of.isoformat() in self.done:
            return
        kind = kind_for(as_of)
        self._start_runs({kind})
        for arm in self.arms.values():
            if make_calls:
                self._make_calls(arm, as_of, kind, res)
            graded = self._grade(arm, as_of, res)
            if arm.variant == "learned":
                self._learn(arm, graded, res)
            self._snapshot(arm, as_of, kind, graded)
        self._checkpoint(as_of)
        res.quarters_done.append(as_of)

    def _make_calls(self, arm: Arm, as_of: date, kind: str, res: ReplayResult) -> None:
        rid = self.run_id(arm.variant, kind)
        for agent in self.agents:
            for company in self.companies:
                key = (agent, company, as_of)
                if key in arm.calls:  # resumed mid-quarter: reuse the stored call
                    continue
                metrics = self.metrics_fn(company, agent, as_of)
                if arm.variant == "baseline":
                    call = baseline_call(agent, company, as_of, rid)
                else:
                    call = self.runner(agent, company, as_of, metrics=metrics, gateway=arm.gateway,
                                       updater=arm.updater, run_id=rid)
                if call is None:
                    res.dropped += 1
                    continue
                arm.calls[key] = call
                self.store.write_call(call)
                arm.pending[call.call_id] = Pending(call, metrics)
                res.n_calls += 1

    def _grade(self, arm: Arm, as_of: date, res: ReplayResult) -> list[tuple[Pending, Grade]]:
        out = []
        for cid, p in list(arm.pending.items()):
            if resolve_by(p.call) > as_of:  # outcome not visible yet
                continue
            g = grade(p.call, self.outcome_fn)
            if g.resolution_date and g.resolution_date > as_of:  # grader needed a later filing: leak guard
                continue
            self.store.write_grade(g)
            del arm.pending[cid]
            out.append((p, g))
            res.n_graded += 1
        return out

    def _learn(self, arm: Arm, graded: list[tuple[Pending, Grade]], res: ReplayResult) -> None:
        by_agent: dict[str, list[GradedCall]] = defaultdict(list)
        for p, g in graded:
            c = p.call
            if (g.correct is False and c.as_of <= TRAIN_END and resolve_by(c, g) <= TRAIN_END
                    and c.company_id not in self.held_out):
                by_agent[c.agent].append(GradedCall(c, g, p.metrics))
        seen = {r["call_id"] for r in getattr(self.store, "rows", lambda t: [])("corrections")}
        for agent, items in by_agent.items():
            items = [i for i in items if i.call.call_id not in seen]
            corrs: list[Correction] = self.make_corrections(items, arm.gateway) if items else []
            if not corrs:
                continue
            ref = arm.updater.submit_corrections(agent, corrs)
            applied = arm.updater.status(ref).state == "applied"
            for c in corrs:
                self.store.write_correction(c, mubit_ref=ref.ref, applied=applied)
            res.n_corrections += len(corrs)

    def _snapshot(self, arm: Arm, as_of: date, kind: str, graded: list[tuple[Pending, Grade]]) -> None:
        rid = self.run_id(arm.variant, kind)
        for agent in self.agents:
            gs = [g for p, g in graded if p.call.agent == agent and g.correct is not None]
            n = len(gs)
            k = sum(bool(g.correct) for g in gs)
            write_snapshot_compat(self.store, rid, agent, arm.variant, as_of, n, k,
                                  k / n if n else None, sum(g.brier for g in gs) / n if n else None,
                                  arm.model_label(agent))

    # whole run -----------------------------------------------------------
    def run(self, quarters: list[date], settle: int = 0) -> ReplayResult:
        res = ReplayResult()
        for q in quarters:
            self.step(q, True, res)
            log.info("quarter %s done (calls %d graded %d corrections %d)", q, res.n_calls, res.n_graded,
                     res.n_corrections)
        last = quarters[-1]
        for i in range(1, settle + 1):  # grade-only quarters: no new calls, lets late horizons resolve
            self.step(add_quarters(last, i), False, res)
        res.versions = {a.variant: {ag: a.model_label(ag) for ag in self.agents} for a in self.arms.values()}
        return res


# ---------------------------------------------------------------- CLI

def build_offline(memory_root: Path, cache_dir: Path | None = None):
    from agents.gateway import ScriptedGateway
    from agents.offline import demo_reality, scripted_llm
    learned_u = FakeModelUpdater(memory_root / "learned")
    frozen_u = FrozenUpdater()
    inner = ScriptedGateway(scripted_llm)
    gws = {"learned": CachingGateway(inner, cache_dir, version_fn=learned_u.get_model_version) if cache_dir else inner,
           "frozen": CachingGateway(inner, cache_dir, version_fn=frozen_u.get_model_version) if cache_dir else inner}
    return gws, {"learned": learned_u, "frozen": frozen_u}, demo_reality


def build_live(memory_root: Path, replay_only: bool):
    from dotenv import find_dotenv, load_dotenv
    from agents.gateway import MubitGateway, MubitUpdater
    from grader.rules import rules_outcome
    load_dotenv(find_dotenv(usecwd=True))
    inner = MubitGateway()
    learned_u = MubitUpdater(memory_root / "learned", model=inner.model)
    frozen_u = FrozenUpdater(inner.model)
    gws = {"learned": CachingGateway(inner, replay_only=replay_only, version_fn=learned_u.get_model_version),
           "frozen": CachingGateway(inner, replay_only=replay_only, version_fn=frozen_u.get_model_version)}
    return gws, {"learned": learned_u, "frozen": frozen_u}, rules_outcome


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="stub metrics, scripted LLM, FALLBACK updater, stub rules")
    ap.add_argument("--replay-only", action="store_true", help="live mode: a cache miss is an error, no API calls")
    ap.add_argument("--companies", type=int, default=5, help="anon_001 .. anon_N")
    ap.add_argument("--agents", default=",".join(DEFAULT_AGENTS))
    ap.add_argument("--quarters", default="2018Q1:2024Q4")
    ap.add_argument("--held-out", type=int, default=None, help="companies never learned from (default N//5, max 10)")
    ap.add_argument("--settle", type=int, default=0, help="extra grade-only quarters after the last one")
    ap.add_argument("--tag", default="replay")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="run_store target: a directory, or 'postgres'")
    ap.add_argument("--runner", help="module:function replacing the stub-backed runner (Person A's)")
    ap.add_argument("--fresh", action="store_true", help="ignore saved progress and lessons for this tag")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(message)s")

    companies = [f"anon_{i:03d}" for i in range(1, a.companies + 1)]
    agents = [x for x in a.agents.split(",") if x]
    quarters = parse_quarters(a.quarters)
    n_held = a.held_out if a.held_out is not None else min(10, len(companies) // 5)
    held = pick_held_out(companies, n_held) if n_held else []

    out = Path(a.out) if a.out != "postgres" else DEFAULT_OUT
    root = out / f"replay_{a.tag}"
    if a.fresh and root.exists():
        import shutil
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    if a.offline:
        gws, ups, outcome_fn = build_offline(root / "memory", root / "cache")
        metrics_fn = __import__("store.stubs", fromlist=["get_metrics_stub"]).get_metrics_stub
    else:
        gws, ups, outcome_fn = build_live(root / "memory", a.replay_only)
        from eval.metrics_source import metrics_fn
    store = open_store(a.out)
    rp = Replay(companies, agents, store, tag=a.tag, gateways=gws, updaters=ups, outcome_fn=outcome_fn,
                metrics_fn=metrics_fn, runner=resolve_runner(a.runner), held_out_companies=held,
                state_path=root / "state.json", fallback=a.offline)
    if a.offline:
        print("OFFLINE: stub metrics, scripted LLM, stub outcome rule, FALLBACK updater (not Mubit). Not real results.")
    res = rp.run(quarters, a.settle)
    store.close()
    print(f"quarters run this time: {len(res.quarters_done)}  calls: {res.n_calls}  graded: {res.n_graded}  "
          f"corrections: {res.n_corrections}  dropped: {res.dropped}")
    for arm, vs in res.versions.items():
        print(f"  {arm:<9} " + "  ".join(f"{ag}={v}" for ag, v in vs.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
