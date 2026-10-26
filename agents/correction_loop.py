"""End-to-end correction loop: the judging moment (README 10, 15 step 5).

    run agent -> grade -> reflect into a Correction -> submit to the updater
    -> new model version -> re-run the agent a quarter later

Usage (offline, stub metrics, scripted LLM, fallback updater):
    python -m agents.correction_loop
    python -m agents.correction_loop --company anon_001 --as-of 2019-06-30 --next 2019-09-30 --json data/loop.json
    python -m agents.correction_loop --live      # real Mubit gateway (agents.gateway.MubitGateway; needs MUBIT_API_KEY)
"""
from __future__ import annotations

import argparse
import json
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from grader.grade import OutcomeFn, grade
from schemas import AgentCall, Correction, Grade
from store.stubs import get_metrics_stub

from .gateway import FakeModelUpdater, LLMGateway, ModelUpdater, UpdateRef
from .reflection import GradedCall, make_corrections
from .run_store import RunStore, open_store
from .runner import run_agent

MetricsFn = Callable[[str, str, date], dict]


@dataclass
class LoopResult:
    agent: str
    company_id: str
    version_before: str
    before: AgentCall | None
    before_grade: Grade | None
    corrections: list[Correction] = field(default_factory=list)
    update_ref: UpdateRef | None = None
    update_state: str | None = None
    version_after: str | None = None
    after: AgentCall | None = None
    after_grade: Grade | None = None

    @property
    def learned(self) -> bool:
        return bool(self.corrections) and self.version_after != self.version_before

    def to_dict(self) -> dict:
        dump = lambda x: x.model_dump(mode="json") if x is not None else None  # noqa: E731
        return {
            "agent": self.agent, "company_id": self.company_id,
            "version_before": self.version_before, "version_after": self.version_after,
            "before": dump(self.before), "before_grade": dump(self.before_grade),
            "corrections": [dump(c) for c in self.corrections],
            "update_ref": vars(self.update_ref) if self.update_ref else None,
            "update_state": self.update_state,
            "after": dump(self.after), "after_grade": dump(self.after_grade),
        }


def run_correction_loop(agent: str, company_id: str, as_of: date, next_as_of: date,
                        gateway: LLMGateway, updater: ModelUpdater,
                        metrics_fn: MetricsFn = get_metrics_stub,
                        outcome_fn: OutcomeFn | None = None, store: RunStore | None = None) -> LoopResult:
    grade_fn = (lambda c: grade(c, outcome_fn)) if outcome_fn else grade
    res = LoopResult(agent, company_id, updater.get_model_version(agent), None, None)
    run_id = str(uuid.uuid4())
    if store:
        store.start_run(run_id, "train", {"kind": "correction_loop", "agent": agent, "company_id": company_id})

    def save(call: AgentCall, g: Grade) -> None:
        if store:
            store.write_call(call)
            store.write_grade(g)

    m1 = metrics_fn(company_id, agent, as_of)
    res.before = run_agent(agent, company_id, as_of, m1, gateway, updater, run_id=run_id)
    if res.before is None:
        return res
    res.before_grade = grade_fn(res.before)
    save(res.before, res.before_grade)

    res.corrections = make_corrections([GradedCall(res.before, res.before_grade, m1)], gateway)
    if res.corrections:
        res.update_ref = updater.submit_corrections(agent, res.corrections)
        res.update_state = updater.status(res.update_ref).state
        if store:
            for c in res.corrections:
                store.write_correction(c, mubit_ref=res.update_ref.ref, applied=res.update_state == "applied")
    res.version_after = updater.get_model_version(agent)

    m2 = metrics_fn(company_id, agent, next_as_of)
    res.after = run_agent(agent, company_id, next_as_of, m2, gateway, updater, run_id=run_id)
    if res.after is not None:
        res.after_grade = grade_fn(res.after)
        save(res.after, res.after_grade)
    return res


def _verdict(g: Grade | None) -> str:
    if g is None:
        return "not graded"
    if g.correct is None:
        return f"UNRESOLVABLE ({g.outcome})"
    return f"{'RIGHT' if g.correct else 'WRONG'} (actual: {g.outcome}, brier {g.brier:.3f})"


def _show_call(label: str, call: AgentCall | None, g: Grade | None) -> None:
    if call is None:
        print(f"{label}: call DROPPED (invalid output after one repair)")
        return
    print(f"{label}  [{call.model}]  as_of {call.as_of}")
    print(f"  call:      {call.claim.answer} @ {call.claim.probability:.0%}")
    for r in call.reasoning:
        print(f"  reasoning: {r}")
    print(f"  graded:    {_verdict(g)}")


def print_report(res: LoopResult, fallback_note: str = "") -> None:
    print(f"\n=== Correction loop: {res.agent} agent on {res.company_id} ===")
    if fallback_note:
        print(fallback_note)
    print()
    _show_call("1) FIRST CALL", res.before, res.before_grade)
    print()
    if not res.corrections:
        print("2) No correction: the first call was right (or was dropped / unresolvable).")
    for c in res.corrections:
        print(f"2) CORRECTION  ({c.error_type})")
        print(f"  lesson:    {c.lesson}")
        print(f"  refines:   {', '.join(c.principle_refs) or '-'}")
    if res.update_ref:
        print(f"\n3) MODEL UPDATE  ref {res.update_ref.ref}  state {res.update_state}")
    print(f"   version:  {res.version_before}  ->  {res.version_after}")
    print()
    _show_call("4) NEXT QUARTER", res.after, res.after_grade)
    print()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent", default="fundamentals")
    ap.add_argument("--company", default="anon_001")
    ap.add_argument("--as-of", default="2019-06-30", type=date.fromisoformat)
    ap.add_argument("--next", default="2019-09-30", type=date.fromisoformat, dest="next_as_of")
    ap.add_argument("--live", action="store_true", help="use MubitGateway + MubitUpdater instead of the offline pieces")
    ap.add_argument("--no-cache", action="store_true", help="with --live: skip the reply cache and always call Mubit")
    ap.add_argument("--memory-dir", help="fallback updater memory (default: a fresh temp dir, so every run starts at v0)")
    ap.add_argument("--save", help="'postgres' (DATABASE_URL) or a directory for JSONL tables")
    ap.add_argument("--json", help="also write the full loop result as JSON (e.g. for the dashboard)")
    args = ap.parse_args(argv)

    from .offline import demo_reality
    if args.live:
        from dotenv import find_dotenv, load_dotenv
        from .gateway import MubitGateway, MubitUpdater
        load_dotenv(find_dotenv(usecwd=True))
        gateway = MubitGateway()
        if not args.no_cache:
            from .cache import CachingGateway
            gateway = CachingGateway(gateway)  # same prompt twice = free, and replays are identical
        updater = MubitUpdater(args.memory_dir or tempfile.mkdtemp(prefix="cm-mubit-memory-"), model=gateway.model)
        outcome_fn = demo_reality  # swap for the real grader once Person A's rules land
        note = (f"LIVE LLM via Mubit ({gateway.model}). Metrics and the outcome rule are STUBS, "
                "so the grades are not real results.")
    else:
        from .gateway import ScriptedGateway
        from .offline import scripted_llm
        gateway, outcome_fn = ScriptedGateway(scripted_llm), demo_reality
        updater = FakeModelUpdater(args.memory_dir or tempfile.mkdtemp(prefix="cm-memory-"))
        note = ("OFFLINE DEMO: stub metrics, scripted LLM, stub outcome rule, FALLBACK updater "
                "(not Mubit). Not real results.")

    store = open_store(args.save)
    res = run_correction_loop(args.agent, args.company, args.as_of, args.next_as_of, gateway, updater,
                              outcome_fn=outcome_fn, store=store)
    if store:
        store.close()
    print_report(res, note)
    for r in getattr(gateway, "requests", []):
        print(f"   mubit {r.request_id}  {r.purpose:<10} {r.agent}")
    if args.json:
        from pathlib import Path
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        reqs = [vars(r) for r in getattr(gateway, "requests", [])]
        Path(args.json).write_text(json.dumps({"offline_demo": not args.live, **res.to_dict(),
                                               "mubit_requests": reqs}, indent=2))
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
