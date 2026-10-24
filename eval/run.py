"""Run the held-out evaluation.

    python -m eval.run                    # offline preview: stub metrics, scripted LLM, NOT results
    python -m eval.run --live             # dry run: prints how many LLM calls it would make
    python -m eval.run --live --yes       # real Mubit calls (cached in data/llm_cache)

Until Person A's real metrics and grader rules land, every run uses STUB inputs. Stub runs
write to data/eval_preview/ and are stamped NOT RESULTS. The official report goes to
eval/reports/ and is only written for runs on real inputs; it will not be overwritten
without --force.
"""
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from agents.frozen import FrozenUpdater
from agents.specs import SPECS
from store.stubs import list_stub_cases

from .harness import evaluate_agent, planned_calls, summarise
from .report import build_report, render_markdown, write_report
from .split import make_split

ROOT = Path(__file__).resolve().parent.parent
OFFICIAL_DIR = ROOT / "eval" / "reports"
PREVIEW_DIR = ROOT / "data" / "eval_preview"
MVP_AGENTS = ("fundamentals", "risk", "scenarios")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agents", default=",".join(MVP_AGENTS))
    ap.add_argument("--companies", help="comma list of anon ids (default: the stub store's companies)")
    ap.add_argument("--held-out", type=int, help="companies to hold out (default 10, or 1 for the 5 stub companies)")
    ap.add_argument("--live", action="store_true", help="use MubitGateway + MubitUpdater instead of the offline pieces")
    ap.add_argument("--yes", action="store_true", help="with --live: actually spend LLM calls")
    ap.add_argument("--memory-dir", help="learned-agent lesson memory (default: a fresh temp dir)")
    ap.add_argument("--out", help="output directory (default: preview dir for stub runs, eval/reports otherwise)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing official report")
    args = ap.parse_args(argv)

    agents = [a for a in args.agents.split(",") if a]
    for a in agents:
        if a not in SPECS:
            ap.error(f"unknown agent {a!r}")
    companies = (args.companies.split(",") if args.companies
                 else sorted({c for a in agents for c, _ in list_stub_cases(a)}))
    n_held = args.held_out or (10 if len(companies) >= 30 else 1)
    split = make_split(companies, n_held)

    plan = planned_calls(split, len(agents))
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
    memory_root = Path(args.memory_dir) if args.memory_dir else Path(tempfile.mkdtemp(prefix="cm-eval-"))
    if args.live:
        from dotenv import find_dotenv, load_dotenv
        from agents.cache import CachingGateway
        from agents.gateway import MubitGateway, MubitUpdater
        load_dotenv(find_dotenv(usecwd=True))
        gateway = CachingGateway(MubitGateway())
        make_learned = lambda a: MubitUpdater(memory_root / a, model=gateway.model)  # noqa: E731
    else:
        from agents.gateway import FakeModelUpdater, ScriptedGateway
        from agents.offline import demo_reality, scripted_llm
        gateway, outcome_fn = ScriptedGateway(scripted_llm), demo_reality
        make_learned = lambda a: FakeModelUpdater(memory_root / a)  # noqa: E731

    results = {}
    for a in agents:
        print(f"evaluating {a} ...")
        ev = evaluate_agent(a, split, gateway, make_learned(a), FrozenUpdater(getattr(gateway, "model", None)),
                            metrics_fn=metrics_fn, outcome_fn=outcome_fn)
        results[a] = summarise(ev)

    real = real_inputs() and args.live
    provenance = {"real_results": real, "offline_demo": not args.live, "metrics": "stub" if not real_inputs() else "store",
                  "outcome_rule": "grader.rules" if real else "stub", "llm": "mubit" if args.live else "scripted"}
    report = build_report(split, results, provenance)
    out_dir = Path(args.out) if args.out else (OFFICIAL_DIR if real else PREVIEW_DIR)
    js, md = write_report(report, out_dir, force=args.force or out_dir == PREVIEW_DIR)
    print(render_markdown(report))
    print(f"wrote {js} and {md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
