"""Run the held-out evaluation.

    python -m eval.run                    # offline preview: stub metrics, scripted LLM, NOT results
    python -m eval.run --live             # dry run: prints how many LLM calls it would make
    python -m eval.run --live --yes       # real Mubit calls (cached in data/llm_cache)

Options:
    --agents valuation,moat               # any agents (default: the three MVP agents)
    --frontier-model claude-opus-5-5      # add a larger no-learning model to the comparison
    --curves                              # also run the frozen twin over the train window
    --save postgres | --save data/runs    # save runs, calls, grades, corrections, snapshots

Until Person A's real metrics and grader rules land, every run uses STUB inputs. Stub runs
write to data/eval_preview/ and are stamped NOT RESULTS. The official report goes to
eval/reports/ and is only written for runs on real inputs; it will not be overwritten
without --force.
"""
from __future__ import annotations

import argparse
import tempfile
import uuid
from pathlib import Path

from agents.frozen import FrozenUpdater
from agents.run_store import open_store
from agents.specs import MVP_AGENTS, SPECS
from store.stubs import list_stub_cases

from .harness import Arm, evaluate_agent, planned_calls, snapshots, summarise
from .report import build_report, render_markdown, write_report
from .split import make_split

ROOT = Path(__file__).resolve().parent.parent
OFFICIAL_DIR = ROOT / "eval" / "reports"
PREVIEW_DIR = ROOT / "data" / "eval_preview"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agents", default=",".join(MVP_AGENTS))
    ap.add_argument("--companies", help="comma list of anon ids (default: the stub store's companies)")
    ap.add_argument("--held-out", type=int, help="companies to hold out (default 10, or 1 for the 5 stub companies)")
    ap.add_argument("--live", action="store_true", help="use MubitGateway + MubitUpdater instead of the offline pieces")
    ap.add_argument("--yes", action="store_true", help="with --live: actually spend LLM calls")
    ap.add_argument("--frontier-model", help="also score this model with no learning (held-out only)")
    ap.add_argument("--curves", action="store_true", help="run the frozen twin over the train window too")
    ap.add_argument("--save", help="'postgres' (DATABASE_URL) or a directory for JSONL tables")
    ap.add_argument("--memory-dir", help="learned-agent lesson memory (default: a fresh temp dir)")
    ap.add_argument("--out", help="output directory (default: preview dir for stub runs, eval/reports otherwise)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing official report")
    ap.add_argument("--from-replay", metavar="DIR", help="score a finished grader.replay run directory (no LLM calls)")
    ap.add_argument("--tag", default="final", help="with --from-replay: the replay's --tag")
    args = ap.parse_args(argv)

    agents = [a for a in args.agents.split(",") if a]
    for a in agents:
        if a not in SPECS:
            ap.error(f"unknown agent {a!r}")
    if args.from_replay:
        return _from_replay(args, agents)
    from .metrics_source import real_inputs
    if args.companies:
        companies = args.companies.split(",")
    elif real_inputs():  # the real universe, not the five stub companies
        from ingest.universe import load_universe
        companies = sorted(c["company_id"] for c in load_universe())
    else:
        companies = sorted({c for a in agents for c, _ in list_stub_cases(a)})
    n_held = args.held_out or (10 if len(companies) >= 30 else 1)
    split = make_split(companies, n_held)

    plan = planned_calls(split, len(agents), args.curves, bool(args.frontier_model))
    print(f"split: {len(split.train_companies)} train + {len(split.held_out_companies)} held-out companies, "
          f"{len(split.train_quarters)} train + {len(split.held_out_quarters)} held-out quarters")
    print(f"analyst calls (upper bound, before cache): {plan['total_analyst_calls']} "
          f"plus one reflection call per correction")
    if args.live and not args.yes:
        print("DRY RUN: nothing sent. Add --yes to spend live calls.")
        return 0

    from grader.grade import stub_outcome
    from .metrics_source import metrics_fn, real_inputs
    outcome_fn = stub_outcome
    if args.live and real_inputs():  # real metrics are graded by the real rules, never the hash stub
        from grader.rules import rules_outcome
        outcome_fn = rules_outcome
    memory_root = Path(args.memory_dir) if args.memory_dir else Path(tempfile.mkdtemp(prefix="cm-eval-"))
    frontier_gw = None
    if args.live:
        from dotenv import find_dotenv, load_dotenv
        from agents.cache import CachingGateway
        from agents.gateway import MubitGateway, MubitUpdater
        load_dotenv(find_dotenv(usecwd=True))
        gateway = CachingGateway(MubitGateway())
        if args.frontier_model:
            frontier_gw = CachingGateway(MubitGateway(model=args.frontier_model))
        make_learned = lambda a: MubitUpdater(memory_root / a, model=gateway.model)  # noqa: E731
    else:
        from agents.gateway import FakeModelUpdater, ScriptedGateway
        from agents.offline import demo_reality, scripted_llm
        gateway, outcome_fn = ScriptedGateway(scripted_llm), demo_reality
        if args.frontier_model:
            frontier_gw = ScriptedGateway(scripted_llm)  # offline: same script, so no real comparison
        make_learned = lambda a: FakeModelUpdater(memory_root / a)  # noqa: E731

    real = real_inputs() and args.live
    provenance = {"real_results": real, "offline_demo": not args.live, "metrics": "store" if real_inputs() else "stub",
                  "outcome_rule": "grader.rules" if real else "stub", "llm": "mubit" if args.live else "scripted",
                  "frontier_model": args.frontier_model}
    store = open_store(args.save)
    train_run, heldout_run = str(uuid.uuid4()), str(uuid.uuid4())
    if store:
        config = {"agents": agents, "split": split.to_dict(), "provenance": provenance}
        store.start_run(train_run, "train", config)
        store.start_run(heldout_run, "heldout", {**config, "train_run_id": train_run})

    results = {}
    for a in agents:
        print(f"evaluating {a} ...")
        frontier = (Arm("frontier", frontier_gw, FrozenUpdater(args.frontier_model)) if frontier_gw else None)
        ev = evaluate_agent(a, split, gateway, make_learned(a), FrozenUpdater(getattr(gateway, "model", None)),
                            metrics_fn=metrics_fn, outcome_fn=outcome_fn, frontier=frontier, store=store,
                            train_run_id=train_run, heldout_run_id=heldout_run, frozen_in_train=args.curves)
        results[a] = summarise(ev)
        if store:
            for s in snapshots(ev):
                n_correct = round(s["accuracy"] * s["n"]) if s["accuracy"] is not None else 0
                store.write_snapshot(train_run if s["phase"] == "train" else heldout_run, s["agent"], s["arm"],
                                     s["as_of"], s["n"], n_correct, s["accuracy"], s["brier"], s["model"])

    report = build_report(split, results, provenance)
    out_dir = Path(args.out) if args.out else (OFFICIAL_DIR if real else PREVIEW_DIR)
    js, md = write_report(report, out_dir, force=args.force or out_dir == PREVIEW_DIR)
    if store:
        store.write_eval_result(heldout_run, report)
        store.close()
    print(render_markdown(report))
    print(f"wrote {js} and {md}" + (f"; saved runs {train_run} and {heldout_run} to {args.save}" if store else ""))
    return 0


def _from_replay(args, agents: list[str]) -> int:
    from .from_replay import build
    split, results = build(args.from_replay, args.tag, agents)
    provenance = {"real_results": True, "offline_demo": False, "metrics": "store", "outcome_rule": "grader.rules",
                  "llm": "mubit", "frontier_model": None, "source": f"grader.replay {args.from_replay} tag {args.tag}"}
    report = build_report(split, results, provenance)
    js, md = write_report(report, Path(args.out) if args.out else OFFICIAL_DIR, force=args.force)
    print(render_markdown(report))
    print(f"wrote {js} and {md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
